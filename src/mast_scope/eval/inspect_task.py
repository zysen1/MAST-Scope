# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Inspect AI task for the seeded MAST-Scope incidents.

The solver does not call a model. It runs the offline diagnoser and stores
the predicted mode and span. Scorers compare those fields with the gold label.
Run with a local mock model so no API key is required:

    inspect eval src/mast_scope/eval/inspect_task.py --model mockllm/model
"""

from __future__ import annotations

import json

from mast_scope.cases import all_cases
from mast_scope.model import Trace
from mast_scope.pipeline import diagnose

try:
    from inspect_ai import Task, task
    from inspect_ai.dataset import MemoryDataset, Sample
    from inspect_ai.model import ModelOutput
    from inspect_ai.scorer import Score, Target, accuracy, scorer
    from inspect_ai.solver import Generate, TaskState, solver
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Inspect AI is not installed. Install it with pip install 'mast-scope[eval]'."
    ) from exc


def _samples() -> list[Sample]:
    samples = []
    for case in all_cases():
        samples.append(
            Sample(
                id=case.id,
                input=case.trace.model_dump_json(),
                target=f"{case.gold_mode or 'NONE'}|{case.gold_span_id or 'NONE'}",
            )
        )
    return samples


@solver
def diagnose_solver():
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        del generate
        trace = Trace.model_validate_json(state.input_text)
        diagnosis = diagnose(trace)
        payload = {
            "mode": diagnosis.blame.mode if diagnosis.blame else "NONE",
            "span_id": diagnosis.blame.span_id if diagnosis.blame else "NONE",
            "category": diagnosis.blame.category if diagnosis.blame else "NONE",
        }
        state.output = ModelOutput.from_content(model="mast-scope", content=json.dumps(payload))
        return state

    return solve


def _predicted(state: TaskState) -> dict:
    return json.loads(state.output.completion)


@scorer(metrics=[accuracy()])
def mode_accuracy():
    async def score(state: TaskState, target: Target) -> Score:
        gold_mode = target.text.split("|", 1)[0]
        predicted = _predicted(state)["mode"]
        ok = predicted == gold_mode
        return Score(
            value=1.0 if ok else 0.0,
            answer=predicted,
            explanation=f"gold={gold_mode} predicted={predicted}",
        )

    return score


@scorer(metrics=[accuracy()])
def blame_span_accuracy():
    async def score(state: TaskState, target: Target) -> Score:
        gold_span = target.text.split("|", 1)[1]
        predicted = _predicted(state)["span_id"]
        ok = predicted == gold_span
        return Score(
            value=1.0 if ok else 0.0,
            answer=predicted,
            explanation=f"gold={gold_span} predicted={predicted}",
        )

    return score


@task
def mast_failure_diagnosis() -> Task:
    """Classify seeded multi-agent failures and name the earliest faulty span."""
    return Task(
        dataset=MemoryDataset(_samples(), name="mast-scope-seeded"),
        solver=diagnose_solver(),
        scorer=[mode_accuracy(), blame_span_accuracy()],
    )
