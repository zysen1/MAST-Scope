# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Heuristic detectors, one per MAST failure mode.

Each detector returns grounded findings: the evidence string is copied from the
step that is blamed, so the judge can reject an ungrounded proposal. Thresholds
are documented next to the rule they implement.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from mast_scope.model import Constraint, Finding, Step, Trace
from mast_scope.taxonomy import MODES

_STOP = frozenset(
    """
    a an the of to for in on and or do not when may whether is are was were be
    this that with from by at as if then than into over under after before about
    only once their your our will would should can could must into per
    """.split()
)
_RESET = re.compile(
    r"(how can i help you|let's start over|let us start over|starting from scratch|"
    r"^hello\b|^hi\b|^hey\b)",
    re.IGNORECASE,
)
_EITHER = re.compile(r"\beither\b.+\bor\b", re.IGNORECASE)
_CALL = re.compile(r"\bcall(?:ing)?\s+([A-Za-z_][\w-]*)", re.IGNORECASE)
_CONTENT_KINDS = {"agent", "llm", "message", "tool"}


def _ordered(trace: Trace) -> list[Step]:
    return sorted(trace.steps, key=lambda step: (step.started_at, step.span_id))


def _blob(step: Step) -> str:
    parts = [
        step.span_id,
        step.name,
        step.input_text,
        step.output_text,
        step.reasoning,
        step.tool_name or "",
        json.dumps(step.output_json, default=str, sort_keys=True),
        json.dumps(step.tool_args, default=str, sort_keys=True),
        json.dumps(step.handoff_payload, default=str, sort_keys=True),
        json.dumps(step.facts_known, default=str, sort_keys=True),
        json.dumps(step.verification, default=str, sort_keys=True) if step.verification else "",
    ]
    return "\n".join(parts)


def _quote(step: Step) -> str:
    for candidate in (step.output_text, step.reasoning, step.input_text, step.tool_name, step.name):
        if candidate and str(candidate).strip():
            return str(candidate).strip()[:240]
    return step.span_id


def _finding(
    step: Step,
    code: str,
    confidence: float,
    evidence: str | None = None,
    details: dict | None = None,
) -> Finding:
    spec = MODES[code]
    quote = evidence if evidence is not None else _quote(step)
    return Finding(
        id=f"{code}:{step.span_id}",
        mode=code,
        category=spec.category,
        span_id=step.span_id,
        agent=step.agent,
        step_name=step.name,
        started_at=step.started_at,
        confidence=confidence,
        evidence=quote,
        detector="heuristic",
        details=details or {},
        mode_name_en=spec.name_en,
        mode_name_zh=spec.name_zh,
        category_name_en="",
        category_name_zh="",
    )


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {word for word in words if len(word) > 3 and word not in _STOP}


def _content_steps(trace: Trace) -> list[Step]:
    return [step for step in _ordered(trace) if step.kind in _CONTENT_KINDS]


def violations(trace: Trace) -> list[tuple[Step, Constraint]]:
    """Earliest step that breaks each constraint, if any."""
    steps = _content_steps(trace)
    if not steps:
        return []
    found: list[tuple[Step, Constraint]] = []
    for constraint in trace.constraints:
        hit = _first_violation(steps, constraint)
        if hit is not None:
            found.append(hit)
    return found


def _contains(step: Step, needle: str) -> bool:
    return str(needle).lower() in step.output_text.lower()


def _first_violation(steps: list[Step], constraint: Constraint) -> tuple[Step, Constraint] | None:
    kind = constraint.kind
    if kind == "must_not_include":
        for step in steps:
            if _contains(step, str(constraint.value)):
                return step, constraint
        return None
    if kind == "must_include":
        if any(_contains(step, str(constraint.value)) for step in steps):
            return None
        return steps[-1], constraint
    if kind in {"max_number", "min_number", "equals"}:
        for step in steps:
            if constraint.field not in step.output_json:
                continue
            raw = step.output_json[constraint.field]
            if kind == "equals":
                if str(raw) != str(constraint.value):
                    return step, constraint
                return None
            try:
                number = float(raw)
                bound = float(constraint.value)
            except (TypeError, ValueError):
                continue
            if kind == "max_number" and number > bound:
                return step, constraint
            if kind == "min_number" and number < bound:
                return step, constraint
            return None
        if kind == "equals":
            return steps[-1], constraint
    return None


def _asks(step: Step) -> bool:
    return step.asked_clarification or ("?" in step.output_text)


def detect_task_spec(trace: Trace) -> list[Finding]:
    findings = []
    for step, constraint in violations(trace):
        findings.append(
            _finding(
                step,
                "FM-1.1",
                0.86,
                evidence=_quote(step),
                details={
                    "constraint_kind": constraint.kind,
                    "field": constraint.field,
                    "value": constraint.value,
                },
            )
        )
    return findings


def detect_role(trace: Trace) -> list[Finding]:
    findings = []
    for step in _ordered(trace):
        if step.kind != "tool" or step.allowed_tools is None or not step.tool_name:
            continue
        if step.tool_name not in step.allowed_tools:
            findings.append(
                _finding(
                    step,
                    "FM-1.2",
                    0.93,
                    evidence=step.tool_name,
                    details={"tool": step.tool_name, "allowed": list(step.allowed_tools)},
                )
            )
    return findings


def tool_signature(step: Step) -> str:
    if step.kind != "tool" or not step.tool_name:
        return ""
    return json.dumps(
        {"agent": step.agent, "tool": step.tool_name, "args": step.tool_args},
        sort_keys=True,
        default=str,
    )


def detect_repetition(trace: Trace) -> list[Finding]:
    """Flag the second identical tool call. One retry is already a repeat."""
    counts: dict[str, int] = defaultdict(int)
    findings = []
    flagged: set[str] = set()
    for step in _ordered(trace):
        if step.kind != "tool" or not step.tool_name:
            continue
        signature = tool_signature(step)
        counts[signature] += 1
        if counts[signature] == 2 and signature not in flagged:
            flagged.add(signature)
            findings.append(
                _finding(
                    step,
                    "FM-1.3",
                    0.9,
                    evidence=step.tool_name,
                    details={"signature": signature},
                )
            )
    return findings


def detect_history_loss(trace: Trace) -> list[Finding]:
    if not trace.memory_keys:
        return []
    established: dict[str, tuple[str, float]] = {}
    findings = []
    flagged: set[str] = set()
    for step in _ordered(trace):
        if step.output_json:
            for key in trace.memory_keys:
                if key in step.output_json and key not in established:
                    established[key] = (str(step.output_json[key]), step.ended_at)
        blob = f"{step.output_text} {json.dumps(step.output_json, default=str)}"
        for key in trace.memory_keys:
            if key in established:
                continue
            match = re.search(rf"{re.escape(key)}\D{{0,16}}(\d+(?:\.\d+)?)", blob)
            if match:
                established[key] = (match.group(1), step.ended_at)
        if step.kind not in {"llm", "agent", "message"}:
            continue
        missing = []
        for key, (value, at) in established.items():
            if step.started_at <= at:
                continue
            if value not in step.input_text and key not in step.input_text:
                missing.append({"key": key, "value": value})
        if missing and step.span_id not in flagged:
            flagged.add(step.span_id)
            findings.append(
                _finding(
                    step,
                    "FM-1.4",
                    0.84,
                    evidence=step.input_text or _quote(step),
                    details={"missing": missing},
                )
            )
    return findings


def detect_termination_unaware(trace: Trace) -> list[Finding]:
    completed_at: float | None = None
    for step in _ordered(trace):
        signaled = "TASK_COMPLETE" in step.output_text or bool(step.metadata.get("completion_signal"))
        if signaled:
            completed_at = step.ended_at
            continue
        if completed_at is not None and step.kind == "tool" and step.started_at >= completed_at:
            return [
                _finding(
                    step,
                    "FM-1.5",
                    0.88,
                    evidence=step.tool_name or _quote(step),
                    details={},
                )
            ]
    return []


def detect_reset(trace: Trace) -> list[Finding]:
    steps = _ordered(trace)
    findings = []
    for index, step in enumerate(steps):
        if index == 0 or step.kind not in {"agent", "llm", "message"}:
            continue
        if step.output_text and _RESET.search(step.output_text.strip()):
            findings.append(_finding(step, "FM-2.1", 0.87, evidence=step.output_text[:240]))
    return findings


def detect_clarification(trace: Trace) -> list[Finding]:
    pending = False
    findings = []
    for step in _ordered(trace):
        if _EITHER.search(step.input_text or ""):
            pending = True
        if _asks(step):
            pending = False
            continue
        if pending and step.kind == "tool":
            findings.append(
                _finding(
                    step,
                    "FM-2.2",
                    0.8,
                    evidence=step.input_text or step.tool_name or _quote(step),
                    details={"tool": step.tool_name},
                )
            )
            pending = False
    return findings


def detect_derailment(trace: Trace) -> list[Finding]:
    task_terms = _terms(trace.task)
    if not task_terms:
        return []
    findings = []
    for step in _ordered(trace):
        if step.kind not in {"agent", "llm", "message"}:
            continue
        output_terms = _terms(step.output_text)
        if len(output_terms) < 12:
            continue
        if task_terms.isdisjoint(output_terms):
            findings.append(_finding(step, "FM-2.3", 0.72, evidence=step.output_text[:240]))
    return findings


def detect_withholding(trace: Trace) -> list[Finding]:
    if not trace.critical_facts:
        return []
    known: dict[str, dict] = defaultdict(dict)
    findings = []
    for step in _ordered(trace):
        if step.facts_known:
            known[step.agent].update(step.facts_known)
        if step.kind != "handoff" and not step.handoff_to:
            continue
        agent_known = known.get(step.agent, {})
        missing = [
            key
            for key in trace.critical_facts
            if key in agent_known and key not in step.handoff_payload
        ]
        if missing:
            findings.append(
                _finding(
                    step,
                    "FM-2.4",
                    0.9,
                    evidence=step.output_text or _quote(step),
                    details={
                        "missing": missing,
                        "known": {key: agent_known[key] for key in missing},
                    },
                )
            )
    return findings


def detect_ignored_input(trace: Trace) -> list[Finding]:
    last_payload: dict | None = None
    last_agent: str | None = None
    findings = []
    for step in _ordered(trace):
        if (
            step.kind == "tool"
            and last_payload
            and step.agent != last_agent
        ):
            conflicts = []
            for key, value in step.tool_args.items():
                if key in last_payload and last_payload[key] != value:
                    conflicts.append(
                        {"key": key, "expected": last_payload[key], "actual": value}
                    )
            if conflicts:
                findings.append(
                    _finding(
                        step,
                        "FM-2.5",
                        0.86,
                        evidence=step.tool_name or _quote(step),
                        details={"conflicts": conflicts},
                    )
                )
        if step.handoff_payload:
            last_payload = dict(step.handoff_payload)
            last_agent = step.agent
    return findings


def detect_mismatch(trace: Trace) -> list[Finding]:
    findings = []
    for step in _ordered(trace):
        if not step.tool_name or not step.reasoning:
            continue
        mentioned = _CALL.findall(step.reasoning)
        if not mentioned:
            continue
        names = {item.lower() for item in mentioned}
        if step.tool_name.lower() in names:
            continue
        findings.append(
            _finding(
                step,
                "FM-2.6",
                0.88,
                evidence=step.reasoning[:240],
                details={"mentioned": mentioned[0], "called": step.tool_name},
            )
        )
    return findings


def _done_subtasks(trace: Trace) -> set[str]:
    done: set[str] = set()
    for step in trace.steps:
        done.update(step.completed_subtasks)
        if step.name in trace.required_subtasks:
            done.add(step.name)
    return done


def detect_premature(trace: Trace) -> list[Finding]:
    if trace.status != "completed" or not trace.required_subtasks:
        return []
    missing = [name for name in trace.required_subtasks if name not in _done_subtasks(trace)]
    if not missing:
        return []
    steps = _ordered(trace)
    if not steps:
        return []
    return [
        _finding(
            steps[-1],
            "FM-3.1",
            0.85,
            evidence=_quote(steps[-1]),
            details={"missing_subtasks": missing},
        )
    ]


def _has_verifier(trace: Trace) -> bool:
    return any(
        step.kind == "guardrail" or step.name.lower().startswith("verify") for step in trace.steps
    )


def detect_no_verification(trace: Trace) -> list[Finding]:
    if not trace.require_verification or _has_verifier(trace):
        return []
    steps = _ordered(trace)
    if not steps:
        return []
    return [_finding(steps[-1], "FM-3.2", 0.83, evidence=_quote(steps[-1]))]


def _passed(step: Step) -> bool | None:
    if step.verification and "passed" in step.verification:
        return bool(step.verification["passed"])
    if "passed" in step.output_json:
        return bool(step.output_json["passed"])
    return None


def detect_incorrect_verification(trace: Trace) -> list[Finding]:
    constraint_failed = bool(violations(trace))
    findings = []
    for step in _ordered(trace):
        if step.kind != "guardrail" and not step.name.lower().startswith("verify"):
            continue
        passed = _passed(step)
        checks = []
        if step.verification:
            checks = step.verification.get("checks") or []
        failed_checks = [item for item in checks if isinstance(item, dict) and item.get("ok") is False]
        if passed is True and (failed_checks or constraint_failed):
            findings.append(
                _finding(
                    step,
                    "FM-3.3",
                    0.87,
                    evidence=step.output_text or _quote(step),
                    details={
                        "failed_checks": failed_checks,
                        "constraint_failed": constraint_failed,
                    },
                )
            )
    return findings


DETECTORS = (
    detect_task_spec,
    detect_role,
    detect_repetition,
    detect_history_loss,
    detect_termination_unaware,
    detect_reset,
    detect_clarification,
    detect_derailment,
    detect_withholding,
    detect_ignored_input,
    detect_mismatch,
    detect_premature,
    detect_no_verification,
    detect_incorrect_verification,
)


def run_heuristics(trace: Trace) -> list[Finding]:
    from mast_scope.taxonomy import CATEGORIES

    findings: list[Finding] = []
    for detector in DETECTORS:
        findings.extend(detector(trace))
    deduped: list[Finding] = []
    seen: set[str] = set()
    for finding in findings:
        category = CATEGORIES[finding.category]
        finding.category_name_en = category.name_en
        finding.category_name_zh = category.name_zh
        if finding.id in seen:
            continue
        seen.add(finding.id)
        deduped.append(finding)
    return deduped


def span_blob(step: Step) -> str:
    return _blob(step)
