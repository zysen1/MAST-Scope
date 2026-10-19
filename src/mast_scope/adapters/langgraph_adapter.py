# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Callback handler for LangGraph.

LangGraph is MIT licensed: https://github.com/langchain-ai/langgraph
Attach ``MastScopeLangGraphHandler`` via ``config={"callbacks": [handler]}``.
Node outputs may include a ``mast`` dict with Step fields (kind, facts_known,
handoff_payload, output_text, tool_args, ...). Nodes without that dict are
still recorded from the callback inputs and outputs.

Install with ``pip install mast-scope[langgraph]``.
"""

from __future__ import annotations

import time
from typing import Any

from mast_scope.model import Constraint, Step, Trace

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:  # pragma: no cover
    class BaseCallbackHandler:  # type: ignore[no-redef]
        pass


class MastScopeLangGraphHandler(BaseCallbackHandler):
    def __init__(
        self,
        task: str,
        *,
        task_zh: str = "",
        constraints: list[dict[str, Any]] | None = None,
        critical_facts: list[str] | None = None,
        memory_keys: list[str] | None = None,
        required_subtasks: list[str] | None = None,
        require_verification: bool = False,
        trace_id: str = "langgraph",
    ) -> None:
        super().__init__()
        self.task = task
        self.task_zh = task_zh
        self.constraints = constraints or []
        self.critical_facts = critical_facts or []
        self.memory_keys = memory_keys or []
        self.required_subtasks = required_subtasks or []
        self.require_verification = require_verification
        self.trace_id = trace_id
        self._open: dict[str, dict[str, Any]] = {}
        self._steps: list[Step] = []
        self._seq = 0.0

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any] | Any,
        *,
        run_id: Any,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        node = (metadata or {}).get("langgraph_node")
        if not node:
            return
        self._seq += 1.0
        self._open[str(run_id)] = {
            "node": str(node),
            "parent": str(parent_run_id) if parent_run_id else None,
            "inputs": inputs if isinstance(inputs, dict) else {"input": inputs},
            "started": self._seq,
        }

    def on_chain_end(self, outputs: Any, *, run_id: Any, **kwargs: Any) -> None:
        opened = self._open.pop(str(run_id), None)
        if opened is None:
            return
        mast = {}
        if isinstance(outputs, dict) and isinstance(outputs.get("mast"), dict):
            mast = outputs["mast"]
        text = ""
        if isinstance(outputs, dict):
            text = str(outputs.get("text") or outputs.get("output") or "")
        elif outputs is not None:
            text = str(outputs)
        self._steps.append(self._make(opened, mast, text))

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: Any,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or "tool"
        node = (metadata or {}).get("langgraph_node") or name
        self._seq += 1.0
        self._open[str(run_id)] = {
            "node": str(node),
            "parent": str(parent_run_id) if parent_run_id else None,
            "inputs": inputs or {},
            "started": self._seq,
            "tool_name": name,
            "input_str": input_str,
            "kind": "tool",
        }

    def on_tool_end(self, output: Any, *, run_id: Any, **kwargs: Any) -> None:
        opened = self._open.pop(str(run_id), None)
        if opened is None:
            return
        mast = {"kind": "tool", "tool_name": opened.get("tool_name"), "input_text": opened.get("input_str") or ""}
        if isinstance(opened.get("inputs"), dict):
            mast["tool_args"] = opened["inputs"]
        self._steps.append(self._make(opened, mast, "" if output is None else str(output)))

    def _make(self, opened: dict[str, Any], mast: dict[str, Any], text: str) -> Step:
        started = float(mast.get("started_at", opened["started"]))
        step = Step(
            span_id=str(mast.get("span_id") or f"{self.trace_id}-{opened['node']}-{int(started)}"),
            trace_id=self.trace_id,
            agent=str(mast.get("agent") or opened["node"]),
            kind=mast.get("kind") or opened.get("kind") or "agent",
            name=str(mast.get("name") or opened["node"]),
            started_at=started,
            ended_at=float(mast.get("ended_at", started + 0.5)),
            parent_id=mast.get("parent_id", opened.get("parent")),
            input_text=str(mast.get("input_text") or ""),
            output_text=str(mast.get("output_text") or text),
        )
        for key in ("role", "reasoning", "tool_name", "handoff_to"):
            if mast.get(key) is not None:
                setattr(step, key, mast[key])
        for key in ("output_json", "tool_args", "handoff_payload", "facts_known", "metadata"):
            if isinstance(mast.get(key), dict):
                setattr(step, key, mast[key])
        if isinstance(mast.get("allowed_tools"), list):
            step.allowed_tools = list(mast["allowed_tools"])
        if isinstance(mast.get("completed_subtasks"), list):
            step.completed_subtasks = list(mast["completed_subtasks"])
        if isinstance(mast.get("verification"), dict):
            step.verification = mast["verification"]
        return step

    def build_trace(self) -> Trace:
        return Trace(
            trace_id=self.trace_id,
            task=self.task,
            task_zh=self.task_zh,
            steps=sorted(self._steps, key=lambda step: (step.started_at, step.span_id)),
            constraints=[Constraint.model_validate(item) for item in self.constraints],
            required_subtasks=list(self.required_subtasks),
            require_verification=self.require_verification,
            critical_facts=list(self.critical_facts),
            memory_keys=list(self.memory_keys),
            framework="langgraph",
        )


def handler_clock() -> float:
    return time.time()
