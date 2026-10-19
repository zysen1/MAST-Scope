# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Deterministic scores on the seeded incidents.

These numbers are not MAST-Data and not MCP-Bench. They measure whether the
detectors, the earliest-root blame, and the local repair recover the labels
of the incidents in ``mast_scope.cases``.
"""

from __future__ import annotations

from mast_scope.cases import all_cases
from mast_scope.pipeline import diagnose, repair


def run_offline() -> dict:
    rows = []
    mode_hits = 0
    blame_hits = 0
    category_hits = 0
    root_cleared = 0
    fully_clean = 0
    failures = 0
    healthy_findings = 0
    for case in all_cases():
        diagnosis = diagnose(case.trace)
        repaired = repair(case.trace)
        predicted = diagnosis.blame.mode if diagnosis.blame else None
        predicted_span = diagnosis.blame.span_id if diagnosis.blame else None
        predicted_category = diagnosis.blame.category if diagnosis.blame else None
        expected_category = None
        if case.gold_mode:
            # FM-1.1 -> FC1, FM-2.4 -> FC2, FM-3.3 -> FC3
            expected_category = "FC" + case.gold_mode.split("-")[1].split(".")[0]
        mode_ok = predicted == case.gold_mode
        span_ok = predicted_span == case.gold_span_id
        category_ok = predicted_category == expected_category
        mode_hits += int(mode_ok)
        blame_hits += int(span_ok)
        category_hits += int(category_ok)
        if case.gold_mode is None:
            healthy_findings += len(diagnosis.findings)
        else:
            failures += 1
            root_cleared += int(repaired.root_cleared)
            fully_clean += int(repaired.fully_clean)
        rows.append(
            {
                "id": case.id,
                "gold_mode": case.gold_mode,
                "predicted_mode": predicted,
                "gold_span": case.gold_span_id,
                "predicted_span": predicted_span,
                "mode_ok": mode_ok,
                "span_ok": span_ok,
                "root_cleared": repaired.root_cleared,
                "fully_clean": repaired.fully_clean,
                "finding_modes": [finding.mode for finding in diagnosis.findings],
                "after_modes": [finding.mode for finding in repaired.diagnosis_after.findings],
            }
        )
    total = len(rows)
    return {
        "n": total,
        "n_failures": failures,
        "n_healthy": total - failures,
        "mode_accuracy": mode_hits / total,
        "blame_span_accuracy": blame_hits / total,
        "category_accuracy": category_hits / total,
        "repair_root_cleared": root_cleared / failures if failures else None,
        "repair_fully_clean": fully_clean / failures if failures else None,
        "healthy_false_findings": healthy_findings,
        "judge_backend": "rubric-offline",
        "rows": rows,
    }
