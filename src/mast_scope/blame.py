# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Earliest-root blame over the trace causal graph.

Parent links and handoff links form the graph. A finding is a symptom when an
earlier finding in ``CAUSAL_PAIRS`` can reach it (or shares its span). The
blame target is the earliest finding that is not a symptom.
"""

from __future__ import annotations

from collections import defaultdict

from mast_scope.model import Blame, Finding, Step, Trace
from mast_scope.taxonomy import CAUSAL_PAIRS, CATEGORIES, MODES


def _steps(trace: Trace) -> dict[str, Step]:
    return {step.span_id: step for step in trace.steps}


def children_of(trace: Trace) -> dict[str, list[str]]:
    index = _steps(trace)
    children: dict[str, list[str]] = defaultdict(list)
    for step in trace.steps:
        if step.parent_id and step.parent_id in index:
            children[step.parent_id].append(step.span_id)
    ordered = sorted(trace.steps, key=lambda step: (step.started_at, step.span_id))
    for step in ordered:
        if not step.handoff_to:
            continue
        for nxt in ordered:
            if nxt.span_id == step.span_id:
                continue
            if nxt.agent == step.handoff_to and nxt.started_at >= step.started_at:
                children[step.span_id].append(nxt.span_id)
                break
    return children


def reachable(trace: Trace, source: str, dest: str) -> bool:
    if source == dest:
        return True
    children = children_of(trace)
    seen = {source}
    stack = [source]
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            if child == dest:
                return True
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return False


def descendants(trace: Trace, source: str) -> set[str]:
    children = children_of(trace)
    seen = set()
    stack = list(children.get(source, []))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(children.get(current, []))
    return seen


def _is_symptom(trace: Trace, finding: Finding, findings: list[Finding]) -> bool:
    for other in findings:
        if other.id == finding.id:
            continue
        if (other.mode, finding.mode) not in CAUSAL_PAIRS:
            continue
        if other.started_at > finding.started_at:
            continue
        if other.span_id == finding.span_id or reachable(trace, other.span_id, finding.span_id):
            return True
    return False


def causal_chain(trace: Trace, root: Finding, findings: list[Finding]) -> list[str]:
    chain = [root.span_id]
    for finding in sorted(findings, key=lambda item: (item.started_at, item.span_id)):
        if finding.span_id in chain:
            continue
        if finding.started_at < root.started_at:
            continue
        if reachable(trace, root.span_id, finding.span_id):
            chain.append(finding.span_id)
    return chain


def attribute(trace: Trace, findings: list[Finding]) -> Blame | None:
    if not findings:
        return None
    symptoms = [finding for finding in findings if _is_symptom(trace, finding, findings)]
    symptom_ids = {finding.id for finding in symptoms}
    roots = [finding for finding in findings if finding.id not in symptom_ids]
    if not roots:
        roots = list(findings)
    root = min(roots, key=lambda finding: (finding.started_at, finding.span_id))
    step = next(item for item in trace.steps if item.span_id == root.span_id)
    spec = MODES[root.mode]
    category = CATEGORIES[spec.category]
    return Blame(
        span_id=root.span_id,
        agent=root.agent,
        role=step.role,
        mode=root.mode,
        category=spec.category,
        category_name_en=category.name_en,
        category_name_zh=category.name_zh,
        mode_name_en=spec.name_en,
        mode_name_zh=spec.name_zh,
        step_name=root.step_name,
        started_at=root.started_at,
        evidence=root.evidence,
        confidence=root.confidence,
        causal_chain=causal_chain(trace, root, findings),
        symptom_ids=sorted(symptom_ids),
    )
