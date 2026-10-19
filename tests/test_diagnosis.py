# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0

from mast_scope.cases import all_cases
from mast_scope.eval.offline import run_offline
from mast_scope.judge import LLMJudge
from mast_scope.model import Finding
from mast_scope.pipeline import LiveScope, diagnose, repair
from mast_scope.taxonomy import CATEGORIES, MODES, PAPER_URL


def test_taxonomy_matches_mast_paper():
    assert PAPER_URL == "https://arxiv.org/abs/2503.13657"
    assert len(MODES) == 14
    assert set(CATEGORIES) == {"FC1", "FC2", "FC3"}
    assert sum(1 for mode in MODES.values() if mode.category == "FC1") == 5
    assert sum(1 for mode in MODES.values() if mode.category == "FC2") == 6
    assert sum(1 for mode in MODES.values() if mode.category == "FC3") == 3


def test_seeded_modes_blame_and_repair():
    metrics = run_offline()
    missed = [row for row in metrics["rows"] if not row["mode_ok"] or not row["span_ok"]]
    assert missed == [], missed
    dirty = [row for row in metrics["rows"] if row["gold_mode"] and not row["fully_clean"]]
    assert dirty == [], dirty
    assert metrics["healthy_false_findings"] == 0
    assert metrics["mode_accuracy"] == 1.0
    assert metrics["blame_span_accuracy"] == 1.0
    assert metrics["repair_fully_clean"] == 1.0


def test_flagship_chain_and_frozen_sibling():
    case = next(item for item in all_cases() if item.id == "ops-417")
    diagnosis = diagnose(case.trace)
    assert diagnosis.blame is not None
    assert diagnosis.blame.agent == "weather"
    assert diagnosis.blame.causal_chain[0] == "ops417-handoff"
    assert "ops417-decision" in diagnosis.blame.causal_chain
    assert "ops417-verify" in diagnosis.blame.causal_chain
    assert "FM-1.1" in diagnosis.blame.symptom_ids[0] or any(
        item.startswith("FM-1.1") for item in diagnosis.blame.symptom_ids
    )
    result = repair(case.trace)
    before = {step.span_id: step.output_text for step in case.trace.steps}
    after = {step.span_id: step.output_text for step in result.repaired.steps}
    assert after["ops417-fuel"] == before["ops417-fuel"]
    assert "ops417-fuel" in result.plan.preserved_span_ids
    assert "ops417-decision" in result.plan.replay_span_ids
    assert "CLEARED TO LAND" not in after["ops417-decision"]
    assert "limit_exceeded" in result.repaired.steps[
        next(i for i, step in enumerate(result.repaired.steps) if step.span_id == "ops417-handoff")
    ].handoff_payload


def test_live_repetition_fires_on_the_second_call():
    case = next(item for item in all_cases() if item.id == "ops-208")
    scope = LiveScope(case.trace)
    first = scope.add(case.trace.steps[0])
    assert first.healthy
    second = scope.add(case.trace.steps[1])
    assert second.blame is not None
    assert second.blame.mode == "FM-1.3"
    assert second.blame.span_id == "ops208-2"


def test_rubric_rejects_ungrounded_evidence():
    case = next(item for item in all_cases() if item.id == "ops-110")
    judge = LLMJudge()
    assert judge.backend == "rubric-offline"
    finding = Finding(
        id="fake",
        mode="FM-1.1",
        category="FC1",
        span_id="ops110-decision",
        agent="dispatcher",
        step_name="dispatch",
        started_at=0,
        confidence=0.9,
        evidence="this quote was never written",
    )
    judgment = judge.review(case.trace, finding)
    assert judgment.agree is False


def test_llm_judge_can_veto_a_grounded_proposal():
    case = next(item for item in all_cases() if item.id == "ops-110")

    def disagree(_prompt: str) -> str:
        return '{"agree": false, "confidence": 0.2, "rationale": "not this mode"}'

    diagnosis = diagnose(case.trace, LLMJudge(complete=disagree))
    assert diagnosis.healthy
    assert diagnosis.judge_backend == "llm"
