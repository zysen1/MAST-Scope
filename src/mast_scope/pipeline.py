# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Diagnose a trace and, when it failed, replan the earliest faulty sub-task."""

from __future__ import annotations

from mast_scope.blame import attribute
from mast_scope.detectors import run_heuristics
from mast_scope.judge import Judge, LLMJudge
from mast_scope.model import Diagnosis, RepairResult, Trace
from mast_scope.repair import apply_repair


def diagnose(trace: Trace, judge: Judge | None = None) -> Diagnosis:
    chosen = judge or LLMJudge()
    proposed = run_heuristics(trace)
    kept = []
    for finding in proposed:
        judgment = chosen.review(trace, finding)
        if not judgment.agree:
            continue
        kept.append(
            finding.model_copy(
                update={
                    "confidence": round((finding.confidence + judgment.confidence) / 2, 4),
                    "judge_note": judgment.rationale,
                }
            )
        )
    blame = attribute(trace, kept)
    return Diagnosis(
        trace_id=trace.trace_id,
        findings=kept,
        blame=blame,
        healthy=blame is None,
        judge_backend=getattr(chosen, "backend", "unknown"),
        proposed_count=len(proposed),
        kept_count=len(kept),
    )


def repair(trace: Trace, judge: Judge | None = None) -> RepairResult:
    chosen = judge or LLMJudge()
    diagnosis = diagnose(trace, chosen)
    return apply_repair(trace, diagnosis, lambda repaired: diagnose(repaired, chosen))


class LiveScope:
    """Run the same detectors on a trace as steps arrive."""

    def __init__(self, template: Trace, judge: Judge | None = None) -> None:
        self.trace = template.model_copy(deep=True)
        self.trace.steps = []
        self.judge = judge or LLMJudge()

    def add(self, step) -> Diagnosis:
        self.trace.steps.append(step)
        return diagnose(self.trace, self.judge)
