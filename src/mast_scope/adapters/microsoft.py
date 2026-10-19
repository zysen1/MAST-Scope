# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Microsoft Agent Framework adapter.

The framework is MIT licensed: https://github.com/microsoft/agent-framework
Its supported observability surface is OpenTelemetry using the GenAI semantic
conventions (``gen_ai.agent.name``, ``gen_ai.tool.name``, and the related
``OtelAttr`` constants). ``MastScopeSpanProcessor`` consumes those spans.

Applications that already call ``configure_otel_providers()`` can add this
processor to the active ``TracerProvider``. A function middleware is also
provided for runs that want a step recorded even when OTel export is off.

Install with ``pip install mast-scope[microsoft]``.
"""

from __future__ import annotations

import json
from typing import Any

from mast_scope.model import Constraint, Step, Trace
from mast_scope.pipeline import LiveScope

# Strings match agent_framework.observability.OtelAttr. Tests assert equality
# against the installed library so the adapter cannot drift silently.
GEN_AI_OPERATION = "gen_ai.operation.name"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_ARGUMENTS = "gen_ai.tool.call.arguments"
GEN_AI_TOOL_RESULT = "gen_ai.tool.call.result"

try:
    from opentelemetry.sdk.trace import SpanProcessor as _SpanProcessor
except ImportError:  # pragma: no cover
    class _SpanProcessor:  # type: ignore[no-redef]
        def on_start(self, span, parent_context=None):
            return None

        def on_end(self, span):
            return None

        def shutdown(self):
            return None

        def force_flush(self, timeout_millis: int = 30000):
            return True


def _attr(span, key: str) -> Any:
    attributes = getattr(span, "attributes", None) or {}
    return attributes.get(key)


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


def _span_id(span) -> str:
    context = span.get_span_context() if hasattr(span, "get_span_context") else span.context
    raw = context.span_id
    if isinstance(raw, str):
        return raw
    return format(raw, "016x")


def _trace_id(span) -> str:
    context = span.get_span_context() if hasattr(span, "get_span_context") else span.context
    raw = context.trace_id
    if isinstance(raw, str):
        return raw
    return format(raw, "032x")


def _parent_id(span) -> str | None:
    parent = getattr(span, "parent", None)
    if parent is None:
        return None
    raw = getattr(parent, "span_id", None)
    if not raw:
        return None
    if isinstance(raw, str):
        return raw
    return format(raw, "016x")


def step_from_otel(span, *, ordinal: float) -> Step:
    """Map one finished OTel span into a Step."""
    attributes = dict(getattr(span, "attributes", None) or {})
    mast = _loads(attributes.get("mast.step"))
    operation = str(attributes.get(GEN_AI_OPERATION) or span.name or "span")
    tool_name = attributes.get(GEN_AI_TOOL_NAME)
    if mast.get("kind"):
        kind = mast["kind"]
    elif tool_name or "tool" in operation:
        kind = "tool"
    elif "agent" in operation:
        kind = "agent"
    else:
        kind = "message"
    start_ns = getattr(span, "start_time", None) or 0
    end_ns = getattr(span, "end_time", None) or start_ns
    started = float(mast.get("started_at", start_ns / 1e9 if start_ns else ordinal))
    ended = float(mast.get("ended_at", end_ns / 1e9 if end_ns else started + 0.1))
    agent = str(mast.get("agent") or attributes.get(GEN_AI_AGENT_NAME) or "unknown")
    step = Step(
        span_id=str(mast.get("span_id") or _span_id(span)),
        trace_id=_trace_id(span),
        agent=agent,
        kind=kind,
        name=str(mast.get("name") or tool_name or span.name or operation),
        started_at=started,
        ended_at=max(ended, started),
        parent_id=mast.get("parent_id") or _parent_id(span),
        tool_name=mast.get("tool_name") or (str(tool_name) if tool_name else None),
        tool_args=mast.get("tool_args") or _loads(attributes.get(GEN_AI_TOOL_ARGUMENTS)),
        output_text=str(mast.get("output_text") or attributes.get(GEN_AI_TOOL_RESULT) or ""),
        input_text=str(mast.get("input_text") or ""),
        reasoning=str(mast.get("reasoning") or ""),
    )
    for key in ("output_json", "handoff_payload", "facts_known"):
        if isinstance(mast.get(key), dict):
            setattr(step, key, mast[key])
    if mast.get("handoff_to"):
        step.handoff_to = str(mast["handoff_to"])
        step.kind = mast.get("kind") or "handoff"
    if isinstance(mast.get("allowed_tools"), list):
        step.allowed_tools = list(mast["allowed_tools"])
    if isinstance(mast.get("verification"), dict):
        step.verification = mast["verification"]
        step.kind = "guardrail"
    if isinstance(mast.get("completed_subtasks"), list):
        step.completed_subtasks = list(mast["completed_subtasks"])
    return step


class MastScopeSpanProcessor(_SpanProcessor):
    """OpenTelemetry span processor for Agent Framework traces."""

    def __init__(
        self,
        task: str = "",
        *,
        constraints: list[dict[str, Any]] | None = None,
        critical_facts: list[str] | None = None,
        memory_keys: list[str] | None = None,
        required_subtasks: list[str] | None = None,
        require_verification: bool = False,
    ) -> None:
        self.task = task
        self.constraints = constraints or []
        self.critical_facts = critical_facts or []
        self.memory_keys = memory_keys or []
        self.required_subtasks = required_subtasks or []
        self.require_verification = require_verification
        self.steps: list[Step] = []
        self._ordinal = 0.0

    def on_start(self, span, parent_context=None) -> None:
        return None

    def on_end(self, span) -> None:
        self._ordinal += 1.0
        self.steps.append(step_from_otel(span, ordinal=self._ordinal))

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def build_trace(self, trace_id: str | None = None) -> Trace:
        steps = list(self.steps)
        if trace_id is None and steps:
            trace_id = steps[0].trace_id
        chosen = [step for step in steps if trace_id is None or step.trace_id == trace_id]
        return Trace(
            trace_id=trace_id or "microsoft-agent-framework",
            task=self.task,
            steps=sorted(chosen, key=lambda step: (step.started_at, step.span_id)),
            constraints=[Constraint.model_validate(item) for item in self.constraints],
            critical_facts=list(self.critical_facts),
            memory_keys=list(self.memory_keys),
            required_subtasks=list(self.required_subtasks),
            require_verification=self.require_verification,
            framework="microsoft-agent-framework",
        )


def attach_to_provider(processor: MastScopeSpanProcessor, provider=None) -> MastScopeSpanProcessor:
    """Add ``processor`` to an SDK TracerProvider, creating one if needed."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    current = provider or trace.get_tracer_provider()
    if not isinstance(current, TracerProvider):
        current = TracerProvider()
        trace.set_tracer_provider(current)
    current.add_span_processor(processor)
    return processor


def mast_function_middleware(scope: LiveScope, agent: str):
    """Function middleware that appends each tool call to a live scope.

    The class subclasses ``agent_framework.FunctionMiddleware``. The tool
    still runs; the middleware only observes the arguments and result.
    """
    from agent_framework import FunctionMiddleware

    class MastFunctionMiddleware(FunctionMiddleware):
        async def process(self, context, call_next):
            await call_next()
            result = context.result
            scope.add(
                Step(
                    span_id=f"{agent}-{context.function.name}-{len(scope.trace.steps) + 1}",
                    trace_id=scope.trace.trace_id,
                    agent=agent,
                    kind="tool",
                    name=context.function.name,
                    started_at=float(len(scope.trace.steps)),
                    ended_at=float(len(scope.trace.steps) + 1),
                    tool_name=context.function.name,
                    tool_args=dict(context.arguments) if isinstance(context.arguments, dict) else {},
                    output_text="" if result is None else str(result),
                )
            )

    return MastFunctionMiddleware()
