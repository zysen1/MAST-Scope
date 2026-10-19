# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""TracingProcessor for the OpenAI Agents SDK.

The SDK is MIT licensed: https://github.com/openai/openai-agents-python
This module subclasses ``TracingProcessor`` and maps agent, function,
generation, handoff, guardrail, and custom spans into a MAST-Scope trace.
It does not modify the SDK. Install with ``pip install mast-scope[openai]``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from mast_scope.model import Constraint, Step, Trace
from mast_scope.pipeline import Diagnosis, diagnose

try:
    from agents.tracing import TracingProcessor as _TracingProcessor
except ImportError:  # pragma: no cover - exercised when the extra is absent
    class _TracingProcessor:  # type: ignore[no-redef]
        pass


def _epoch(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _text_from_messages(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                content = item.get("content") or item.get("text") or ""
                if isinstance(content, list):
                    parts.extend(str(piece) for piece in content)
                else:
                    parts.append(str(content))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(value)


def _loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class MastScopeProcessor(_TracingProcessor):
    """Collect SDK spans and diagnose the trace when it ends.

    Pass the task spec through ``trace(..., metadata=...)``:

    ``task``, ``task_zh``, ``constraints``, ``critical_facts``,
    ``memory_keys``, ``required_subtasks``, ``require_verification``.

    A custom span may carry the same fields used by :class:`~mast_scope.model.Step`
    (``kind``, ``handoff_payload``, ``facts_known``, ``output_text``, ...).
    Native span types are mapped without that annotation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._steps: dict[str, list[Step]] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._names: dict[str, str] = {}
        self._agents: dict[str, str] = {}
        self._clock: dict[str, float] = {}
        self.traces: dict[str, Trace] = {}
        self.diagnoses: dict[str, Diagnosis] = {}

    def install(self) -> MastScopeProcessor:
        """Receive spans in addition to the SDK's default exporter."""
        from agents.tracing import add_trace_processor

        add_trace_processor(self)
        return self

    def replace_exporters(self) -> MastScopeProcessor:
        """Use this processor instead of the default OpenAI exporter.

        Tests and offline demos call this so finishing a trace does not
        attempt a network export.
        """
        from agents.tracing import set_trace_processors

        set_trace_processors([self])
        return self

    def on_trace_start(self, trace) -> None:
        with self._lock:
            self._meta[trace.trace_id] = dict(getattr(trace, "metadata", None) or {})
            self._names[trace.trace_id] = getattr(trace, "name", "") or ""
            self._steps.setdefault(trace.trace_id, [])

    def on_trace_end(self, trace) -> None:
        with self._lock:
            meta = self._meta.get(trace.trace_id) or dict(getattr(trace, "metadata", None) or {})
            steps = list(self._steps.get(trace.trace_id, []))
            name = self._names.get(trace.trace_id, getattr(trace, "name", "") or "")
        built = _trace_from_parts(trace.trace_id, name, meta, steps)
        self.traces[trace.trace_id] = built
        self.diagnoses[trace.trace_id] = diagnose(built)

    def on_span_start(self, span) -> None:
        return None

    def on_span_end(self, span) -> None:
        step = self._convert(span)
        if step is None:
            return
        with self._lock:
            self._steps.setdefault(span.trace_id, []).append(step)
            self._agents[span.span_id] = step.agent

    def shutdown(self) -> None:
        return None

    def force_flush(self) -> None:
        return None

    def _convert(self, span) -> Step | None:
        data = span.span_data
        kind_name = getattr(data, "type", "") or ""
        custom = dict(getattr(data, "data", None) or {}) if kind_name == "custom" else {}
        if custom.get("skip"):
            return None
        agent = str(custom.get("agent") or self._inherit_agent(span, data) or "unknown")
        trace_id = span.trace_id
        with self._lock:
            self._clock[trace_id] = self._clock.get(trace_id, 0.0) + 1.0
            fallback = self._clock[trace_id]
        started = _epoch(custom.get("started_at"))
        if started is None:
            started = _epoch(getattr(span, "started_at", None))
        if started is None:
            started = fallback
        ended = _epoch(custom.get("ended_at"))
        if ended is None:
            ended = _epoch(getattr(span, "ended_at", None))
        if ended is None:
            ended = started + 0.5
        step = Step(
            span_id=str(custom.get("span_id") or span.span_id),
            trace_id=trace_id,
            agent=agent,
            kind=_kind_for(kind_name, custom),
            name=str(custom.get("name") or getattr(data, "name", None) or kind_name or "span"),
            started_at=started,
            ended_at=ended,
            parent_id=getattr(span, "parent_id", None),
        )
        _fill_native(step, data, kind_name)
        _fill_custom(step, custom)
        with self._lock:
            self._agents[span.span_id] = step.agent
        return step

    def _inherit_agent(self, span, data) -> str:
        if getattr(data, "type", "") == "agent":
            return getattr(data, "name", "") or "unknown"
        if getattr(data, "type", "") == "handoff":
            return getattr(data, "from_agent", None) or "unknown"
        parent = getattr(span, "parent_id", None)
        with self._lock:
            if parent and parent in self._agents:
                return self._agents[parent]
        return "unknown"


def _kind_for(kind_name: str, custom: dict[str, Any]):
    if custom.get("kind"):
        return custom["kind"]
    return {
        "agent": "agent",
        "function": "tool",
        "generation": "llm",
        "response": "llm",
        "handoff": "handoff",
        "guardrail": "guardrail",
        "task": "task",
        "turn": "message",
        "custom": "message",
    }.get(kind_name, "message")


def _fill_native(step: Step, data, kind_name: str) -> None:
    if kind_name == "function":
        step.tool_name = getattr(data, "name", None)
        step.name = step.tool_name or step.name
        step.input_text = getattr(data, "input", None) or ""
        step.tool_args = _loads(step.input_text)
        output = getattr(data, "output", None)
        step.output_text = "" if output is None else str(output)
    elif kind_name == "generation":
        step.input_text = _text_from_messages(getattr(data, "input", None))
        step.output_text = _text_from_messages(getattr(data, "output", None))
        step.name = getattr(data, "model", None) or step.name
    elif kind_name == "response":
        step.input_text = _text_from_messages(getattr(data, "input", None))
        response = getattr(data, "response", None)
        step.output_text = "" if response is None else str(response)
    elif kind_name == "handoff":
        step.agent = getattr(data, "from_agent", None) or step.agent
        step.handoff_to = getattr(data, "to_agent", None)
        step.name = f"handoff:{step.handoff_to or 'unknown'}"
    elif kind_name == "guardrail":
        triggered = bool(getattr(data, "triggered", False))
        step.name = getattr(data, "name", None) or "guardrail"
        step.verification = {"passed": not triggered, "checks": []}
        step.output_text = step.name
        step.output_json = {"passed": not triggered}
    elif kind_name == "agent":
        tools = getattr(data, "tools", None)
        if tools:
            step.allowed_tools = list(tools)
        step.name = getattr(data, "name", None) or step.name


def _fill_custom(step: Step, custom: dict[str, Any]) -> None:
    scalar = (
        "role", "input_text", "output_text", "reasoning", "tool_name", "handoff_to",
    )
    for key in scalar:
        if key in custom and custom[key] is not None:
            setattr(step, key, custom[key])
    for key in ("output_json", "tool_args", "handoff_payload", "facts_known", "metadata"):
        if isinstance(custom.get(key), dict):
            setattr(step, key, custom[key])
    if isinstance(custom.get("allowed_tools"), list):
        step.allowed_tools = list(custom["allowed_tools"])
    if isinstance(custom.get("completed_subtasks"), list):
        step.completed_subtasks = list(custom["completed_subtasks"])
    if isinstance(custom.get("verification"), dict):
        step.verification = custom["verification"]
    if "asked_clarification" in custom:
        step.asked_clarification = bool(custom["asked_clarification"])
    if "parent_id" in custom:
        step.parent_id = custom["parent_id"]


def _trace_from_parts(trace_id: str, name: str, meta: dict[str, Any], steps: list[Step]) -> Trace:
    constraints = [Constraint.model_validate(item) for item in meta.get("constraints") or []]
    ordered = sorted(steps, key=lambda step: (step.started_at, step.span_id))
    return Trace(
        trace_id=trace_id,
        task=str(meta.get("task") or name or ""),
        task_zh=str(meta.get("task_zh") or ""),
        steps=ordered,
        constraints=constraints,
        required_subtasks=list(meta.get("required_subtasks") or []),
        require_verification=bool(meta.get("require_verification", False)),
        critical_facts=list(meta.get("critical_facts") or []),
        memory_keys=list(meta.get("memory_keys") or []),
        status=meta.get("status") or "completed",
        framework="openai-agents",
    )
