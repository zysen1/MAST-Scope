# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0

import asyncio

import pytest

from mast_scope.pipeline import LiveScope, diagnose


def test_openai_native_spans_and_custom_annotation():
    agents = pytest.importorskip("agents")
    from agents import custom_span, function_span, guardrail_span, set_trace_processors, trace

    from mast_scope.adapters.openai_agents import MastScopeProcessor

    processor = MastScopeProcessor().replace_exporters()
    metadata = {
        "task": "Do not issue CLEARED TO LAND when the crosswind exceeds 25 knots.",
        "critical_facts": ["crosswind_kt", "limit_exceeded"],
        "require_verification": True,
        "constraints": [{"kind": "must_not_include", "value": "CLEARED TO LAND"}],
        "required_subtasks": ["weather", "dispatch", "verify"],
    }
    with trace("ops-417-sdk", metadata=metadata) as handle:
        with custom_span(
            "weather-read",
            {
                "span_id": "sdk-metar",
                "agent": "weather",
                "kind": "tool",
                "name": "weather",
                "tool_name": "read_metar",
                "started_at": 1,
                "ended_at": 2,
                "output_text": "METAR crosswind 28kt",
                "facts_known": {"crosswind_kt": 28, "limit_exceeded": True},
                "completed_subtasks": ["weather"],
            },
        ):
            pass
        with custom_span(
            "weather-handoff",
            {
                "span_id": "sdk-handoff",
                "agent": "weather",
                "kind": "handoff",
                "name": "handoff-weather",
                "handoff_to": "dispatcher",
                "parent_id": "sdk-metar",
                "started_at": 2,
                "ended_at": 3,
                "output_text": "wind is breezy",
                "handoff_payload": {"summary": "wind is breezy"},
                "facts_known": {"crosswind_kt": 28, "limit_exceeded": True},
            },
        ):
            pass
        with custom_span(
            "decision",
            {
                "span_id": "sdk-decision",
                "agent": "dispatcher",
                "kind": "llm",
                "name": "dispatch",
                "parent_id": "sdk-handoff",
                "started_at": 3,
                "ended_at": 4,
                "output_text": "CLEARED TO LAND runway 27",
                "completed_subtasks": ["weather", "dispatch"],
            },
        ):
            pass
        with guardrail_span("verify", triggered=False):
            pass
        with function_span("compute_fuel", input='{"runway": "27"}', output="fuel ok"):
            pass
    diagnosis = processor.diagnoses[handle.trace_id]
    assert diagnosis.blame is not None
    assert diagnosis.blame.mode == "FM-2.4"
    assert diagnosis.blame.span_id == "sdk-handoff"
    built = processor.traces[handle.trace_id]
    assert built.framework == "openai-agents"
    assert any(step.kind == "tool" and step.tool_name == "compute_fuel" for step in built.steps)
    assert any(step.kind == "guardrail" for step in built.steps)
    set_trace_processors([])
    assert agents.__name__ == "agents"


def test_langgraph_handler_on_a_compiled_graph():
    pytest.importorskip("langgraph")
    from typing_extensions import TypedDict

    from langgraph.graph import END, START, StateGraph

    from mast_scope.adapters.langgraph_adapter import MastScopeLangGraphHandler

    class State(TypedDict, total=False):
        text: str
        mast: dict

    def weather(state: State) -> State:
        return {
            "text": "wind is breezy",
            "mast": {
                "span_id": "lg-handoff",
                "agent": "weather",
                "kind": "handoff",
                "name": "handoff-weather",
                "handoff_to": "dispatcher",
                "started_at": 1,
                "output_text": "wind is breezy",
                "handoff_payload": {"summary": "wind is breezy"},
                "facts_known": {"crosswind_kt": 28, "limit_exceeded": True},
                "completed_subtasks": ["weather"],
            },
        }

    def dispatch(state: State) -> State:
        return {
            "text": "CLEARED TO LAND runway 27",
            "mast": {
                "span_id": "lg-decision",
                "agent": "dispatcher",
                "kind": "llm",
                "name": "dispatch",
                "parent_id": "lg-handoff",
                "started_at": 2,
                "output_text": "CLEARED TO LAND runway 27",
                "completed_subtasks": ["weather", "dispatch"],
            },
        }

    graph = StateGraph(State)
    graph.add_node("weather", weather)
    graph.add_node("dispatch", dispatch)
    graph.add_edge(START, "weather")
    graph.add_edge("weather", "dispatch")
    graph.add_edge("dispatch", END)
    handler = MastScopeLangGraphHandler(
        task="Do not issue CLEARED TO LAND when the crosswind exceeds 25 knots.",
        constraints=[{"kind": "must_not_include", "value": "CLEARED TO LAND"}],
        critical_facts=["crosswind_kt", "limit_exceeded"],
        required_subtasks=["weather", "dispatch", "verify"],
        trace_id="ops-417-langgraph",
    )
    graph.compile().invoke({"text": "flight 417"}, config={"callbacks": [handler]})
    trace = handler.build_trace()
    assert {step.agent for step in trace.steps} >= {"weather", "dispatcher"}
    diagnosis = diagnose(trace)
    assert diagnosis.blame is not None
    assert diagnosis.blame.mode == "FM-2.4"
    assert diagnosis.blame.agent == "weather"


def test_microsoft_otel_processor_matches_framework_attributes():
    pytest.importorskip("opentelemetry")
    agent_framework = pytest.importorskip("agent_framework")
    from agent_framework.observability import OtelAttr
    from opentelemetry.sdk.trace import TracerProvider

    from mast_scope.adapters.microsoft import (
        GEN_AI_AGENT_NAME,
        GEN_AI_TOOL_NAME,
        MastScopeSpanProcessor,
    )

    assert OtelAttr.AGENT_NAME == GEN_AI_AGENT_NAME
    assert OtelAttr.TOOL_NAME == GEN_AI_TOOL_NAME
    processor = MastScopeSpanProcessor(
        task="Check MEL item pack-2 once and report the deferral.",
    )
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer("mast-scope-test")
    args = '{"item": "pack-2"}'
    with tracer.start_as_current_span("workflow"):
        for _ in range(2):
            with tracer.start_as_current_span("execute_tool") as span:
                span.set_attribute(OtelAttr.AGENT_NAME, "maintenance")
                span.set_attribute(OtelAttr.TOOL_NAME, "lookup_mel")
                span.set_attribute(OtelAttr.OPERATION, "execute_tool")
                span.set_attribute(OtelAttr.TOOL_ARGUMENTS, args)
                span.set_attribute(OtelAttr.TOOL_RESULT, "deferred")
    trace = processor.build_trace()
    assert trace.framework == "microsoft-agent-framework"
    diagnosis = diagnose(trace)
    assert diagnosis.blame is not None
    assert diagnosis.blame.mode == "FM-1.3"
    assert diagnosis.blame.agent == "maintenance"
    assert agent_framework.__name__ == "agent_framework"


def test_microsoft_function_middleware_records_a_repeat():
    pytest.importorskip("agent_framework")
    from agent_framework import FunctionInvocationContext

    from mast_scope.adapters.microsoft import mast_function_middleware
    from mast_scope.model import Trace

    scope = LiveScope(
        Trace(trace_id="mw", task="Check MEL item pack-2 once and report the deferral.", steps=[])
    )
    middleware = mast_function_middleware(scope, agent="maintenance")

    class Tool:
        name = "lookup_mel"

    async def call_next():
        context.result = "deferred"

    for _ in range(2):
        context = FunctionInvocationContext(function=Tool(), arguments={"item": "pack-2"})
        asyncio.run(middleware.process(context, call_next))
    assert scope.trace.steps[-1].tool_name == "lookup_mel"
    diagnosis = diagnose(scope.trace)
    assert diagnosis.blame is not None
    assert diagnosis.blame.mode == "FM-1.3"
