# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""MAST labels used by the detectors.

The 14 failure modes and 3 categories are the taxonomy defined by Cemri et al.
in "Why Do Multi-Agent LLM Systems Fail?" (NeurIPS 2025).

https://arxiv.org/abs/2503.13657

Descriptions below are short paraphrases for the UI and the judge prompt, not
a reproduction of the paper.
"""

from __future__ import annotations

from dataclasses import dataclass

PAPER_URL = "https://arxiv.org/abs/2503.13657"
PAPER_TITLE = "Why Do Multi-Agent LLM Systems Fail?"
PAPER_AUTHORS = (
    "Mert Cemri, Melissa Z. Pan, Shuyi Yang, Lakshya A. Agrawal, Bhavya Chopra, "
    "Rishabh Tiwari, Kurt Keutzer, Aditya Parameswaran, Dan Klein, "
    "Kannan Ramchandran, Matei Zaharia, Joseph E. Gonzalez, Ion Stoica"
)
HTN_PAPER_URL = "https://arxiv.org/abs/2610.22195"
HTN_PAPER_TITLE = (
    "HTN-Orchestrate: A Hierarchical Task Network Framework for Multi-Agent Orchestration"
)


@dataclass(frozen=True)
class Category:
    code: str
    name_en: str
    name_zh: str
    summary_en: str
    summary_zh: str


@dataclass(frozen=True)
class FailureMode:
    code: str
    category: str
    name_en: str
    name_zh: str
    summary_en: str
    summary_zh: str


CATEGORIES: dict[str, Category] = {
    "FC1": Category(
        code="FC1",
        name_en="System design issues",
        name_zh="系统设计问题",
        summary_en=(
            "Specification and architecture failures: the task or role was "
            "disobeyed, context was dropped, a step was repeated, or the run "
            "did not notice it was already finished. MAST calls this category "
            "system design issues."
        ),
        summary_zh=(
            "规格与架构类失败：违反任务或角色、丢掉上下文、重复步骤，"
            "或没有意识到任务其实已经结束。MAST 将这一类称为系统设计问题。"
        ),
    ),
    "FC2": Category(
        code="FC2",
        name_en="Inter-agent misalignment",
        name_zh="智能体间失配",
        summary_en=(
            "Agents fail to stay aligned: a conversation resets, a needed "
            "question is never asked, the task drifts, a fact is withheld, "
            "a peer's input is ignored, or the action contradicts the reasoning."
        ),
        summary_zh=(
            "智能体之间没有对齐：对话被重置、该问的问题没问、任务跑偏、"
            "关键事实被扣下、同伴的输入被忽略，或行动和推理对不上。"
        ),
    ),
    "FC3": Category(
        code="FC3",
        name_en="Task verification failures",
        name_zh="任务核验失败",
        summary_en=(
            "The run stops too early, skips the check, or a check says pass "
            "when the outcome is still wrong."
        ),
        summary_zh="运行过早结束、跳过核验，或者核验在结果仍然错误时给出了通过。",
    ),
}


def _m(
    code: str,
    category: str,
    name_en: str,
    name_zh: str,
    summary_en: str,
    summary_zh: str,
) -> FailureMode:
    return FailureMode(code, category, name_en, name_zh, summary_en, summary_zh)


MODES: dict[str, FailureMode] = {
    mode.code: mode
    for mode in (
        _m(
            "FM-1.1",
            "FC1",
            "Disobey task specification",
            "违反任务规格",
            "A step breaks an explicit constraint of the task.",
            "某一步打破了任务里写明的约束。",
        ),
        _m(
            "FM-1.2",
            "FC1",
            "Disobey role specification",
            "违反角色规格",
            "An agent calls a tool outside the tools its role is allowed to use.",
            "智能体调用了其角色不允许使用的工具。",
        ),
        _m(
            "FM-1.3",
            "FC1",
            "Step repetition",
            "步骤重复",
            "The same agent repeats a tool call with the same arguments.",
            "同一个智能体用相同参数重复调用了同一个工具。",
        ),
        _m(
            "FM-1.4",
            "FC1",
            "Loss of conversation history",
            "丢失对话历史",
            "A later turn drops a memory value that an earlier turn had established.",
            "后续轮次丢掉了前面已经确定的记忆值。",
        ),
        _m(
            "FM-1.5",
            "FC1",
            "Unaware of termination conditions",
            "未识别终止条件",
            "Work continues after a completion signal.",
            "已经出现完成信号之后仍继续行动。",
        ),
        _m(
            "FM-2.1",
            "FC2",
            "Conversation reset",
            "对话被重置",
            "An agent restarts the dialogue mid-task and abandons progress.",
            "智能体在任务中途把对话重置，丢掉已有进展。",
        ),
        _m(
            "FM-2.2",
            "FC2",
            "Fail to ask for clarification",
            "该澄清时没有提问",
            "The input leaves a choice open, and the agent acts without asking.",
            "输入里有未决的选择，智能体没有提问就行动了。",
        ),
        _m(
            "FM-2.3",
            "FC2",
            "Task derailment",
            "任务偏离",
            "An output leaves the task and does not share its content words.",
            "输出离开了任务，和任务的内容词不再有交集。",
        ),
        _m(
            "FM-2.4",
            "FC2",
            "Information withholding",
            "隐瞒信息",
            "An agent knows a critical fact and leaves it out of the handoff.",
            "智能体已经知道关键事实，但交接时没有交出去。",
        ),
        _m(
            "FM-2.5",
            "FC2",
            "Ignored other agent's input",
            "忽视其他智能体的输入",
            "A later action contradicts a value a peer already passed over.",
            "后续行动否定了同伴已经传来的值。",
        ),
        _m(
            "FM-2.6",
            "FC2",
            "Reasoning-action mismatch",
            "推理与行动不一致",
            "The reasoning names one tool and the step calls another.",
            "推理里写的是一个工具，实际调用的是另一个。",
        ),
        _m(
            "FM-3.1",
            "FC3",
            "Premature termination",
            "过早终止",
            "The run is marked complete while a required sub-task is still open.",
            "仍有必需子任务未完成，运行却被标成结束。",
        ),
        _m(
            "FM-3.2",
            "FC3",
            "No or incomplete verification",
            "缺少或未完成核验",
            "The task requires a check, and no verifier step runs.",
            "任务要求核验，但没有任何核验步骤。",
        ),
        _m(
            "FM-3.3",
            "FC3",
            "Incorrect verification",
            "核验结论错误",
            "A verifier reports pass while a check or a constraint still fails.",
            "约束或检查仍然失败，核验却报告通过。",
        ),
    )
}

# A later finding is treated as a symptom when an earlier finding of the
# cause mode can reach it in the causal graph. Same-span pairs count.
CAUSAL_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("FM-2.4", "FM-1.1"),
        ("FM-2.4", "FM-2.5"),
        ("FM-2.4", "FM-3.3"),
        ("FM-2.5", "FM-1.1"),
        ("FM-2.5", "FM-3.3"),
        ("FM-2.6", "FM-1.1"),
        ("FM-1.2", "FM-1.1"),
        ("FM-1.4", "FM-1.1"),
        ("FM-2.3", "FM-1.1"),
        ("FM-2.2", "FM-1.1"),
        ("FM-2.1", "FM-1.4"),
        ("FM-1.3", "FM-1.5"),
        ("FM-1.1", "FM-3.3"),
        ("FM-3.1", "FM-3.2"),
    }
)


def mode(code: str) -> FailureMode:
    return MODES[code]


def category_of(code: str) -> Category:
    return CATEGORIES[MODES[code].category]
