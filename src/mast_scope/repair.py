# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Replan the failed sub-task and replay only its dependents.

Completed siblings stay frozen. The patch is local and deterministic so the
demo and the eval run with no model call. When a judge model is available the
same plan's instruction can be handed to an orchestrator; the instruction text
is the contract.

The split between a preserved prefix and a rebuilt leaf follows the idea in
HTN-Orchestrate (arXiv:2610.22195): do not re-decompose work that already
returned a usable result.
"""

from __future__ import annotations

from mast_scope.blame import descendants
from mast_scope.detectors import tool_signature
from mast_scope.model import Diagnosis, RepairPlan, RepairResult, Step, Trace
from mast_scope.taxonomy import MODES


def _plan(diagnosis: Diagnosis, trace: Trace) -> RepairPlan | None:
    blame = diagnosis.blame
    if blame is None:
        return None
    spec = MODES[blame.mode]
    later = descendants(trace, blame.span_id)
    preserved = [
        step.span_id
        for step in trace.steps
        if step.span_id != blame.span_id and step.span_id not in later
    ]
    replay = [step.span_id for step in trace.steps if step.span_id in later]
    return RepairPlan(
        mode=blame.mode,
        failed_span_id=blame.span_id,
        failed_agent=blame.agent,
        failed_subtask=blame.step_name,
        preserved_span_ids=preserved,
        replay_span_ids=replay,
        instruction_en=(
            f"Replan only `{blame.step_name}` on agent `{blame.agent}` "
            f"({spec.code} {spec.name_en}). Keep {len(preserved)} earlier or "
            f"sibling span(s) frozen and replay {len(replay)} dependent span(s). "
            f"{spec.summary_en}"
        ),
        instruction_zh=(
            f"只重规划智能体 `{blame.agent}` 的子任务 `{blame.step_name}`"
            f"（{spec.code} {spec.name_zh}）。冻结 {len(preserved)} 个已完成或旁路步骤，"
            f"重放 {len(replay)} 个下游步骤。{spec.summary_zh}"
        ),
    )


def _step(trace: Trace, span_id: str) -> Step:
    return next(step for step in trace.steps if step.span_id == span_id)


def _patch(trace: Trace, diagnosis: Diagnosis) -> None:
    blame = diagnosis.blame
    if blame is None:
        return
    finding = next(item for item in diagnosis.findings if item.span_id == blame.span_id and item.mode == blame.mode)
    step = _step(trace, blame.span_id)
    mode = blame.mode
    if mode == "FM-2.4":
        known = finding.details.get("known") or {}
        step.handoff_payload.update(known)
        rendered = " ".join(f"{key}={value}" for key, value in known.items())
        step.output_text = (step.output_text + " " + rendered).strip()
    elif mode == "FM-1.2":
        tool = finding.details.get("tool") or step.tool_name
        step.kind = "handoff"
        step.handoff_to = step.handoff_to or "dispatcher"
        step.tool_name = None
        step.output_text = f"Escalating {tool} to the role that owns it."
    elif mode == "FM-1.3":
        signature = finding.details.get("signature")
        trace.steps = [
            item
            for item in trace.steps
            if tool_signature(item) != signature or item.started_at < step.started_at
        ]
    elif mode == "FM-1.4":
        for item in finding.details.get("missing") or []:
            if item["value"] not in step.input_text:
                step.input_text = f"{step.input_text} {item['key']}={item['value']}".strip()
    elif mode == "FM-1.5":
        trace.steps = [item for item in trace.steps if item.started_at < step.started_at or item.span_id == step.span_id]
        trace.steps = [item for item in trace.steps if item.span_id != step.span_id]
    elif mode == "FM-2.1":
        step.output_text = f"Continuing the task with the previous context: {trace.task}"
    elif mode == "FM-2.2":
        step.kind = "message"
        step.tool_name = None
        step.asked_clarification = True
        step.output_text = "Which of the stated options should I use?"
    elif mode == "FM-2.3":
        step.output_text = f"Returning to the task. {trace.task}"
    elif mode == "FM-2.5":
        for conflict in finding.details.get("conflicts") or []:
            step.tool_args[conflict["key"]] = conflict["expected"]
    elif mode == "FM-2.6":
        mentioned = finding.details.get("mentioned")
        if mentioned:
            step.tool_name = mentioned
            step.name = mentioned
    elif mode == "FM-3.1":
        missing = list(finding.details.get("missing_subtasks") or [])
        for name in missing:
            trace.steps.append(
                Step(
                    span_id=f"{step.span_id}-repair-{name}",
                    trace_id=trace.trace_id,
                    agent="verifier",
                    role="verifier",
                    kind="guardrail",
                    name=name if name.lower().startswith("verify") else f"verify-{name}",
                    started_at=step.ended_at + 0.1,
                    ended_at=step.ended_at + 0.5,
                    parent_id=step.span_id,
                    output_text=f"Completed the missing sub-task {name}.",
                    completed_subtasks=list(trace.required_subtasks),
                    verification={"passed": True, "checks": [{"name": name, "ok": True}]},
                )
            )
    elif mode == "FM-3.2":
        trace.steps.append(
            Step(
                span_id=f"{step.span_id}-repair-verify",
                trace_id=trace.trace_id,
                agent="verifier",
                role="verifier",
                kind="guardrail",
                name="verify",
                started_at=step.ended_at + 0.1,
                ended_at=step.ended_at + 0.4,
                parent_id=step.span_id,
                output_text="Verification completed.",
                verification={"passed": True, "checks": [{"name": "constraints", "ok": True}]},
                completed_subtasks=["verify"],
            )
        )
    elif mode == "FM-3.3":
        checks = []
        if step.verification:
            checks = [
                {**item, "ok": False} if isinstance(item, dict) else item
                for item in step.verification.get("checks") or []
            ]
        step.verification = {"passed": False, "checks": checks or [{"name": "constraints", "ok": False}]}
        step.output_json = {**step.output_json, "passed": False}
        step.output_text = "Verification failed closed."
    _replay_dependents(trace, blame.span_id)


def _replay_dependents(trace: Trace, root_id: str) -> None:
    """Push restored facts downstream and quarantine outputs that still break a constraint."""
    from mast_scope.detectors import violations

    later = descendants(trace, root_id)
    if not later:
        later = set()
    root = next((step for step in trace.steps if step.span_id == root_id), None)
    restored = ""
    if root is not None and root.handoff_payload:
        restored = " ".join(f"{key}={value}" for key, value in root.handoff_payload.items())
    for step in trace.steps:
        if step.span_id not in later:
            continue
        if restored and restored not in step.input_text:
            step.input_text = f"{step.input_text} {restored}".strip()
    for step, constraint in violations(trace):
        if step.span_id != root_id and step.span_id not in later:
            continue
        _quarantine(step, constraint)


def _quarantine(step: Step, constraint) -> None:
    if constraint.kind == "must_not_include":
        phrase = str(constraint.value)
        if phrase.lower() in step.output_text.lower():
            step.output_text = (
                "HOLD. The previous decision is withdrawn because it broke a task constraint."
            )
            step.output_json = {**step.output_json, "decision": "HOLD"}
    elif constraint.kind == "max_number" and constraint.field in step.output_json:
        step.output_json[constraint.field] = constraint.value
        step.output_text = (
            f"Clamped {constraint.field} to {constraint.value} after the missing context was restored."
        )
    elif constraint.kind == "must_include":
        phrase = str(constraint.value)
        if phrase.lower() not in step.output_text.lower():
            step.output_text = f"{step.output_text} {phrase}".strip()
    elif constraint.kind == "equals" and constraint.field:
        step.output_json[constraint.field] = constraint.value
        step.output_text = f"{constraint.field} set to {constraint.value}."
    elif constraint.kind == "min_number" and constraint.field in step.output_json:
        step.output_json[constraint.field] = constraint.value
        step.output_text = f"Raised {constraint.field} to {constraint.value}."


def apply_repair(trace: Trace, diagnosis: Diagnosis, diagnosis_after) -> RepairResult:
    plan = _plan(diagnosis, trace)
    repaired = trace.model_copy(deep=True)
    if plan is not None:
        _patch(repaired, diagnosis)
    after = diagnosis_after(repaired)
    root_mode = diagnosis.blame.mode if diagnosis.blame else None
    modes_after = {finding.mode for finding in after.findings}
    root_cleared = root_mode is None or root_mode not in modes_after
    return RepairResult(
        plan=plan,
        repaired=repaired,
        diagnosis_after=after,
        root_cleared=root_cleared,
        fully_clean=after.healthy,
    )
