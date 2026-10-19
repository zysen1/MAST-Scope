# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Trace, finding, blame, and repair records shared by detectors and the UI."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

StepKind = Literal["agent", "llm", "tool", "handoff", "guardrail", "message", "task"]
TraceStatus = Literal["completed", "incomplete", "error"]


class Constraint(BaseModel):
    kind: Literal["max_number", "min_number", "must_include", "must_not_include", "equals"]
    value: Any
    field: str = ""
    description_en: str = ""
    description_zh: str = ""


class Step(BaseModel):
    span_id: str
    trace_id: str
    agent: str
    kind: StepKind
    name: str
    started_at: float
    ended_at: float
    parent_id: str | None = None
    role: str | None = None
    input_text: str = ""
    output_text: str = ""
    output_json: dict[str, Any] = Field(default_factory=dict)
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    handoff_to: str | None = None
    handoff_payload: dict[str, Any] = Field(default_factory=dict)
    facts_known: dict[str, Any] = Field(default_factory=dict)
    allowed_tools: list[str] | None = None
    completed_subtasks: list[str] = Field(default_factory=list)
    verification: dict[str, Any] | None = None
    asked_clarification: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    trace_id: str
    task: str
    steps: list[Step]
    task_zh: str = ""
    constraints: list[Constraint] = Field(default_factory=list)
    required_subtasks: list[str] = Field(default_factory=list)
    require_verification: bool = False
    critical_facts: list[str] = Field(default_factory=list)
    memory_keys: list[str] = Field(default_factory=list)
    status: TraceStatus = "completed"
    framework: str = "native"


class Finding(BaseModel):
    id: str
    mode: str
    category: str
    span_id: str
    agent: str
    step_name: str
    started_at: float
    confidence: float
    evidence: str
    detector: str = "heuristic"
    judge_note: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    mode_name_en: str = ""
    mode_name_zh: str = ""
    category_name_en: str = ""
    category_name_zh: str = ""


class Blame(BaseModel):
    span_id: str
    agent: str
    role: str | None = None
    mode: str
    category: str
    category_name_en: str
    category_name_zh: str
    mode_name_en: str
    mode_name_zh: str
    step_name: str
    started_at: float
    evidence: str
    confidence: float
    causal_chain: list[str] = Field(default_factory=list)
    symptom_ids: list[str] = Field(default_factory=list)


class Diagnosis(BaseModel):
    trace_id: str
    findings: list[Finding] = Field(default_factory=list)
    blame: Blame | None = None
    healthy: bool = True
    judge_backend: str = "rubric-offline"
    proposed_count: int = 0
    kept_count: int = 0


class RepairPlan(BaseModel):
    mode: str
    failed_span_id: str
    failed_agent: str
    failed_subtask: str
    preserved_span_ids: list[str] = Field(default_factory=list)
    replay_span_ids: list[str] = Field(default_factory=list)
    instruction_en: str
    instruction_zh: str


class RepairResult(BaseModel):
    plan: RepairPlan | None = None
    repaired: Trace
    diagnosis_after: Diagnosis
    root_cleared: bool
    fully_clean: bool
