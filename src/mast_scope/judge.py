# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Agreement layer over heuristic proposals.

The offline judge is a grounding rubric: a proposal stands only when its
evidence quote actually appears in the step. ``LLMJudge`` asks a model the
same question and falls back to the rubric when no API key is configured.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Callable, Protocol

from mast_scope.detectors import span_blob
from mast_scope.model import Finding, Trace
from mast_scope.taxonomy import MODES

CompleteFn = Callable[[str], str]


@dataclass
class Judgment:
    agree: bool
    confidence: float
    rationale: str
    backend: str


class Judge(Protocol):
    backend: str

    def review(self, trace: Trace, finding: Finding) -> Judgment: ...


class RubricJudge:
    """Keep a proposal only when its evidence is a quote from the blamed step."""

    backend = "rubric-offline"

    def review(self, trace: Trace, finding: Finding) -> Judgment:
        step = next((item for item in trace.steps if item.span_id == finding.span_id), None)
        if step is None or not finding.evidence.strip():
            return Judgment(False, 0.0, "The blamed step or the evidence quote is missing.", self.backend)
        if finding.evidence not in span_blob(step):
            return Judgment(
                False,
                0.15,
                "The evidence quote does not appear in the step, so the proposal is ungrounded.",
                self.backend,
            )
        return Judgment(
            True,
            0.74,
            "The evidence quote is present on the blamed step.",
            self.backend,
        )


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _prompt(trace: Trace, finding: Finding) -> str:
    spec = MODES[finding.mode]
    step = next(item for item in trace.steps if item.span_id == finding.span_id)
    return (
        "You are a careful annotator for the MAST multi-agent failure taxonomy "
        "(Cemri et al., arXiv:2503.13657). A heuristic proposed one failure mode. "
        "Agree only if the quoted evidence supports that mode. Reply with one JSON "
        'object: {"agree": true or false, "confidence": 0 to 1, "rationale": "short"}.\n\n'
        f"Task: {trace.task}\n"
        f"Mode: {spec.code} {spec.name_en}. {spec.summary_en}\n"
        f"Agent: {finding.agent}\n"
        f"Step name: {finding.step_name}\n"
        f"Evidence quote: {finding.evidence}\n"
        f"Step input: {step.input_text[:800]}\n"
        f"Step output: {step.output_text[:800]}\n"
        f"Reasoning: {step.reasoning[:400]}\n"
    )


def _parse_judgment(raw: str, backend: str) -> Judgment | None:
    match = _JSON_OBJECT.search(raw or "")
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if "agree" not in payload:
        return None
    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    rationale = str(payload.get("rationale") or "")
    return Judgment(bool(payload["agree"]), confidence, rationale, backend)


def openai_complete(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model=os.environ.get("MAST_SCOPE_JUDGE_MODEL", "gpt-4o-mini"),
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You annotate multi-agent failures. Reply with JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content or ""


class LLMJudge:
    """LLM agreement, with the grounding rubric as the offline backend."""

    def __init__(self, complete: CompleteFn | None = None) -> None:
        self._rubric = RubricJudge()
        if complete is not None:
            self.backend = "llm"
            self._complete: CompleteFn | None = complete
        elif os.environ.get("OPENAI_API_KEY"):
            self.backend = "openai"
            self._complete = openai_complete
        else:
            self.backend = "rubric-offline"
            self._complete = None

    def review(self, trace: Trace, finding: Finding) -> Judgment:
        if self._complete is None:
            return self._rubric.review(trace, finding)
        try:
            raw = self._complete(_prompt(trace, finding))
        except Exception as exc:  # network, auth, or SDK errors stay offline
            fallback = self._rubric.review(trace, finding)
            fallback.rationale = f"LLM judge failed ({type(exc).__name__}); {fallback.rationale}"
            fallback.backend = "rubric-offline"
            return fallback
        parsed = _parse_judgment(raw, self.backend)
        if parsed is None:
            fallback = self._rubric.review(trace, finding)
            fallback.rationale = f"Unparseable judge output; {fallback.rationale}"
            return fallback
        if parsed.agree:
            grounded = self._rubric.review(trace, finding)
            if not grounded.agree:
                return Judgment(
                    False,
                    parsed.confidence,
                    "The model agreed, but the evidence quote is not in the step.",
                    self.backend,
                )
        return parsed
