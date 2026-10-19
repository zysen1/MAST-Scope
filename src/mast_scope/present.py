# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""JSON dossier for the flight-recorder UI."""

from __future__ import annotations

import json
from pathlib import Path

from mast_scope.cases import Case, all_cases
from mast_scope.pipeline import diagnose, repair


def _agents(case: Case) -> list[str]:
    ordered: list[str] = []
    for step in sorted(case.trace.steps, key=lambda item: (item.started_at, item.span_id)):
        if step.agent not in ordered:
            ordered.append(step.agent)
    return ordered


def present_case(case: Case) -> dict:
    diagnosis = diagnose(case.trace)
    repaired = repair(case.trace)
    return {
        "id": case.id,
        "title_en": case.title_en,
        "title_zh": case.title_zh,
        "narrative_en": case.narrative_en,
        "narrative_zh": case.narrative_zh,
        "gold_mode": case.gold_mode,
        "gold_span_id": case.gold_span_id,
        "task_en": case.trace.task,
        "task_zh": case.trace.task_zh,
        "framework": case.trace.framework,
        "agents": _agents(case),
        "steps": [step.model_dump() for step in case.trace.steps],
        "findings": [finding.model_dump() for finding in diagnosis.findings],
        "blame": diagnosis.blame.model_dump() if diagnosis.blame else None,
        "healthy": diagnosis.healthy,
        "judge_backend": diagnosis.judge_backend,
        "repair": {
            "plan": repaired.plan.model_dump() if repaired.plan else None,
            "root_cleared": repaired.root_cleared,
            "fully_clean": repaired.fully_clean,
            "steps": [step.model_dump() for step in repaired.repaired.steps],
            "findings": [finding.model_dump() for finding in repaired.diagnosis_after.findings],
            "blame": (
                repaired.diagnosis_after.blame.model_dump()
                if repaired.diagnosis_after.blame
                else None
            ),
            "healthy": repaired.diagnosis_after.healthy,
        },
    }


def export_cases(directory: str | Path) -> list[dict]:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    payloads = [present_case(case) for case in all_cases()]
    index = []
    for payload in payloads:
        path = target / f"{payload['id']}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        index.append(
            {
                "id": payload["id"],
                "title_en": payload["title_en"],
                "title_zh": payload["title_zh"],
                "gold_mode": payload["gold_mode"],
                "healthy": payload["healthy"],
                "file": f"{payload['id']}.json",
            }
        )
    (target / "index.json").write_text(
        json.dumps({"cases": index}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payloads
