# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Seeded multi-agent incidents.

Each case is hand-authored so the failure is visible in the trace itself.
Gold labels are for the eval only. Detectors never read them.
"""

from __future__ import annotations

from pydantic import BaseModel

from mast_scope.model import Constraint, Step, Trace

_HOLIDAY = (
    "The office holiday party needs a chocolate cake, balloons, a playlist, "
    "and a speech about teamwork and gratitude for the facilities crew who "
    "set up the chairs in the hangar."
)


class Case(BaseModel):
    id: str
    title_en: str
    title_zh: str
    narrative_en: str
    narrative_zh: str
    gold_mode: str | None
    gold_span_id: str | None
    trace: Trace


def _step(trace_id: str, span_id: str, agent: str, kind: str, name: str, t: float, **kwargs) -> Step:
    dt = kwargs.pop("dt", 1.0)
    return Step(
        trace_id=trace_id,
        span_id=span_id,
        agent=agent,
        kind=kind,  # type: ignore[arg-type]
        name=name,
        started_at=t,
        ended_at=t + dt,
        **kwargs,
    )


def _trace(trace_id: str, task: str, steps: list[Step], **kwargs) -> Trace:
    return Trace(trace_id=trace_id, task=task, steps=steps, framework="seeded", **kwargs)


def ops_417() -> Case:
    task = (
        "Decide whether flight 417 may land on runway 27. "
        "Do not issue CLEARED TO LAND when the crosswind exceeds 25 knots."
    )
    tid = "ops-417"
    steps = [
        _step(
            tid, "ops417-root", "dispatcher", "agent", "receive", 0,
            role="dispatcher",
            output_text="Requesting weather and fuel before the landing decision.",
        ),
        _step(
            tid, "ops417-metar", "weather", "tool", "weather", 1, dt=2,
            parent_id="ops417-root", role="weather", tool_name="read_metar",
            tool_args={"runway": "27"},
            output_text="METAR crosswind 28kt, limit 25kt.",
            facts_known={"crosswind_kt": 28, "limit_kt": 25, "limit_exceeded": True},
            completed_subtasks=["weather"],
        ),
        _step(
            tid, "ops417-handoff", "weather", "handoff", "handoff-weather", 3,
            parent_id="ops417-metar", role="weather", handoff_to="dispatcher",
            output_text="wind is breezy",
            handoff_payload={"summary": "wind is breezy", "runway": "27"},
            facts_known={"crosswind_kt": 28, "limit_kt": 25, "limit_exceeded": True},
        ),
        _step(
            tid, "ops417-fuel", "fuel", "tool", "fuel-check", 4, dt=2,
            parent_id="ops417-root", role="fuel", tool_name="compute_fuel",
            tool_args={"runway": "27"},
            output_text="Fuel is sufficient for runway 27.",
        ),
        _step(
            tid, "ops417-decision", "dispatcher", "llm", "dispatch", 6, dt=2,
            parent_id="ops417-root", role="dispatcher",
            input_text="Weather says wind is breezy. Fuel is sufficient.",
            output_text="CLEARED TO LAND runway 27",
            output_json={"decision": "CLEARED TO LAND", "runway": "27"},
            completed_subtasks=["weather", "dispatch"],
        ),
        _step(
            tid, "ops417-verify", "verifier", "guardrail", "verify", 8,
            parent_id="ops417-decision", role="verifier",
            output_text="pass",
            output_json={"passed": True},
            verification={"passed": True, "checks": [{"name": "plan_present", "ok": True}]},
            completed_subtasks=["weather", "dispatch", "verify"],
        ),
    ]
    return Case(
        id=tid,
        title_en="OPS-417 — limit withheld, landing cleared",
        title_zh="OPS-417 — 扣下超限事实，仍签发降落许可",
        narrative_en=(
            "Weather read a 28kt crosswind against a 25kt limit and handed "
            "dispatch a note that only said the wind was breezy. Dispatch "
            "cleared the landing. The verifier checked that a plan existed."
        ),
        narrative_zh=(
            "气象席读到侧风 28 节，限制是 25 节，交给签派的却只有一句“风有点大”。"
            "签派签发了降落许可。核验席只检查了“有没有一份计划”。"
        ),
        gold_mode="FM-2.4",
        gold_span_id="ops417-handoff",
        trace=_trace(
            tid, task, steps,
            task_zh="判断 417 航班能否在 27 号跑道降落。侧风超过 25 节时不得签发 CLEARED TO LAND。",
            constraints=[
                Constraint(
                    kind="must_not_include",
                    value="CLEARED TO LAND",
                    description_en="Do not clear a landing above the crosswind limit.",
                    description_zh="侧风超限时不得签发降落许可。",
                )
            ],
            required_subtasks=["weather", "dispatch", "verify"],
            require_verification=True,
            critical_facts=["crosswind_kt", "limit_exceeded"],
        ),
    )


def ops_110() -> Case:
    tid = "ops-110"
    task = "Do not issue CLEARED TO LAND when the crosswind exceeds 25 knots."
    steps = [
        _step(
            tid, "ops110-decision", "dispatcher", "llm", "dispatch", 0, dt=2,
            role="dispatcher",
            output_text="CLEARED TO LAND runway 27",
            output_json={"decision": "CLEARED TO LAND"},
        )
    ]
    return Case(
        id=tid,
        title_en="OPS-110 — clearance breaks the spec",
        title_zh="OPS-110 — 许可直接违反规格",
        narrative_en="Dispatch emits a landing clearance the task explicitly forbids. Nothing earlier explains it.",
        narrative_zh="签派直接发出了任务明文禁止的降落许可，前面没有别的原因。",
        gold_mode="FM-1.1",
        gold_span_id="ops110-decision",
        trace=_trace(
            tid, task, steps,
            task_zh="侧风超过 25 节时不得签发 CLEARED TO LAND。",
            constraints=[Constraint(kind="must_not_include", value="CLEARED TO LAND")],
        ),
    )


def ops_331() -> Case:
    tid = "ops-331"
    steps = [
        _step(
            tid, "ops331-tool", "cabin", "tool", "dispatch_release", 0,
            role="cabin", tool_name="dispatch_release",
            allowed_tools=["announce", "log_note"],
            tool_args={"flight": "417"},
            output_text="released",
        )
    ]
    return Case(
        id=tid,
        title_en="OPS-331 — cabin releases the flight",
        title_zh="OPS-331 — 客舱席越权放行",
        narrative_en="The cabin role may announce or log. It calls the dispatcher-only release tool.",
        narrative_zh="客舱席只能广播或记笔记，却调用了只有签派能用的放行工具。",
        gold_mode="FM-1.2",
        gold_span_id="ops331-tool",
        trace=_trace(tid, "Prepare the cabin announcement. Only dispatch may release the flight.", steps),
    )


def ops_208() -> Case:
    tid = "ops-208"
    args = {"item": "pack-2"}
    steps = [
        _step(tid, "ops208-1", "maintenance", "tool", "lookup_mel", 0, role="maintenance",
              tool_name="lookup_mel", tool_args=args, output_text="deferred"),
        _step(tid, "ops208-2", "maintenance", "tool", "lookup_mel", 1, role="maintenance",
              tool_name="lookup_mel", tool_args=dict(args), output_text="deferred"),
        _step(tid, "ops208-3", "maintenance", "tool", "lookup_mel", 2, role="maintenance",
              tool_name="lookup_mel", tool_args=dict(args), output_text="deferred"),
    ]
    return Case(
        id=tid,
        title_en="OPS-208 — the same MEL lookup, again",
        title_zh="OPS-208 — 同一条 MEL 被反复查询",
        narrative_en="Maintenance looks up pack-2, then issues the identical lookup again.",
        narrative_zh="维修席查了一次 pack-2，然后用完全相同的参数又查了一次。",
        gold_mode="FM-1.3",
        gold_span_id="ops208-2",
        trace=_trace(tid, "Check MEL item pack-2 once and report the deferral.", steps),
    )


def ops_641() -> Case:
    tid = "ops-641"
    steps = [
        _step(
            tid, "ops641-plan", "planner", "agent", "budget", 0, dt=1,
            role="planner",
            output_text="budget_usd is 500. Keep the plan under this cap.",
            output_json={"budget_usd": 500},
        ),
        _step(
            tid, "ops641-buyer", "buyer", "llm", "purchase", 2, dt=1,
            parent_id="ops641-plan", role="buyer",
            input_text="buy the catering package",
            output_text="purchased catering for 900 usd",
            output_json={"spent_usd": 900},
        ),
    ]
    return Case(
        id=tid,
        title_en="OPS-641 — the budget fell out of the prompt",
        title_zh="OPS-641 — 预算从上下文里掉了",
        narrative_en="The planner fixed the budget at 500. The buyer turn never sees that number and spends 900.",
        narrative_zh="计划席把预算定在 500。采购席的下一轮上下文里没有这个数字，花了 900。",
        gold_mode="FM-1.4",
        gold_span_id="ops641-buyer",
        trace=_trace(
            tid, "Buy catering under the stated budget.", steps,
            memory_keys=["budget_usd"],
            constraints=[Constraint(kind="max_number", field="spent_usd", value=500)],
        ),
    )


def ops_318() -> Case:
    tid = "ops-318"
    steps = [
        _step(
            tid, "ops318-done", "dispatcher", "agent", "close", 0,
            role="dispatcher", output_text="TASK_COMPLETE: diversion filed.",
        ),
        _step(
            tid, "ops318-extra", "dispatcher", "tool", "file_diversion", 1,
            role="dispatcher", tool_name="file_diversion", tool_args={"airport": "PEK"},
            output_text="filed again",
        ),
    ]
    return Case(
        id=tid,
        title_en="OPS-318 — still filing after the close",
        title_zh="OPS-318 — 已经结束仍在提交",
        narrative_en="Dispatch marks the diversion filed, then calls the filing tool anyway.",
        narrative_zh="签派已经标记备降提交完成，随后还是又调用了一次提交工具。",
        gold_mode="FM-1.5",
        gold_span_id="ops318-extra",
        trace=_trace(tid, "File the diversion to PEK and stop when it is filed.", steps),
    )


def ops_700() -> Case:
    tid = "ops-700"
    steps = [
        _step(
            tid, "ops700-work", "coordinator", "agent", "brief", 0,
            role="coordinator", output_text="Runway 27 crosswind is the open item.",
        ),
        _step(
            tid, "ops700-reset", "coordinator", "llm", "reset", 1,
            role="coordinator",
            output_text="Hello! How can I help you today? Let's start over.",
        ),
    ]
    return Case(
        id=tid,
        title_en="OPS-700 — the coordinator restarts the briefing",
        title_zh="OPS-700 — 协调席把简报重置了",
        narrative_en="Mid-briefing the coordinator greets the room and throws away the open item.",
        narrative_zh="简报进行到一半，协调席重新打招呼，把未决事项丢掉了。",
        gold_mode="FM-2.1",
        gold_span_id="ops700-reset",
        trace=_trace(tid, "Finish the runway 27 crosswind briefing.", steps),
    )


def ops_015() -> Case:
    tid = "ops-015"
    steps = [
        _step(
            tid, "ops015-file", "clerk", "tool", "file_report", 0,
            role="clerk", tool_name="file_report", tool_args={"docket": "airline"},
            input_text="File the report under either the safety board or the airline docket.",
            output_text="filed under airline",
        )
    ]
    return Case(
        id=tid,
        title_en="OPS-015 — a guess instead of a question",
        title_zh="OPS-015 — 该问的时候猜了一个",
        narrative_en="The docket is explicitly either/or. The clerk files the airline docket without asking.",
        narrative_zh="卷宗明确是二选一。文员没有提问，直接归到了航空公司卷宗。",
        gold_mode="FM-2.2",
        gold_span_id="ops015-file",
        trace=_trace(tid, "File the incident report in the correct docket.", steps),
    )


def ops_880() -> Case:
    tid = "ops-880"
    steps = [
        _step(
            tid, "ops880-drift", "analyst", "llm", "summarize", 0, dt=2,
            role="analyst", output_text=_HOLIDAY,
        )
    ]
    return Case(
        id=tid,
        title_en="OPS-880 — the summary leaves the station",
        title_zh="OPS-880 — 摘要跑去筹备聚会",
        narrative_en="Asked for PEK cargo revenue, the analyst writes about the office party.",
        narrative_zh="任务是汇总首都机场的货运收入，分析席却写起了办公室聚会。",
        gold_mode="FM-2.3",
        gold_span_id="ops880-drift",
        trace=_trace(tid, "Summarize third-quarter cargo revenue for station PEK in USD.", steps),
    )


def ops_990() -> Case:
    tid = "ops-990"
    steps = [
        _step(
            tid, "ops990-handoff", "network", "handoff", "handoff-port", 0,
            role="network", handoff_to="runtime",
            output_text="Use port 443.",
            handoff_payload={"port": 443},
        ),
        _step(
            tid, "ops990-bind", "runtime", "tool", "bind_port", 1,
            parent_id="ops990-handoff", role="runtime", tool_name="bind_port",
            tool_args={"port": 80}, output_text="bound 80",
        ),
    ]
    return Case(
        id=tid,
        title_en="OPS-990 — runtime ignores the port",
        title_zh="OPS-990 — 运行席没听端口",
        narrative_en="Network hands over port 443. Runtime binds port 80.",
        narrative_zh="网络席交接的是 443 端口。运行席绑定了 80。",
        gold_mode="FM-2.5",
        gold_span_id="ops990-bind",
        trace=_trace(tid, "Bind the service to the port network selected.", steps),
    )


def ops_774() -> Case:
    tid = "ops-774"
    steps = [
        _step(
            tid, "ops774-charge", "billing", "tool", "charge_payment", 0,
            role="billing", tool_name="charge_payment",
            tool_args={"amount": 40},
            reasoning="I will call refund_payment for the duplicate charge.",
            output_text="charged 40",
        )
    ]
    return Case(
        id=tid,
        title_en="OPS-774 — the refund that charged",
        title_zh="OPS-774 — 说退款，做了扣款",
        narrative_en="Billing's reasoning names refund_payment. The call is charge_payment.",
        narrative_zh="计费席的推理写的是 refund_payment，实际调用的是 charge_payment。",
        gold_mode="FM-2.6",
        gold_span_id="ops774-charge",
        trace=_trace(tid, "Refund the duplicate passenger charge.", steps),
    )


def ops_102() -> Case:
    tid = "ops-102"
    steps = [
        _step(tid, "ops102-weather", "weather", "tool", "weather", 0, role="weather",
              tool_name="read_metar", output_text="crosswind 12kt",
              completed_subtasks=["weather"]),
        _step(tid, "ops102-dispatch", "dispatcher", "llm", "dispatch", 1, role="dispatcher",
              output_text="Taxi to the gate.", completed_subtasks=["weather", "dispatch"]),
    ]
    return Case(
        id=tid,
        title_en="OPS-102 — closed before verify",
        title_zh="OPS-102 — 核验还没做就结束了",
        narrative_en="Weather and dispatch finish. The run is marked complete with verify still open.",
        narrative_zh="气象和签派都做完了。运行被标成结束，核验子任务还空着。",
        gold_mode="FM-3.1",
        gold_span_id="ops102-dispatch",
        trace=_trace(
            tid, "Produce a gate plan and verify it.", steps,
            required_subtasks=["weather", "dispatch", "verify"],
            status="completed",
        ),
    )


def ops_120() -> Case:
    tid = "ops-120"
    steps = [
        _step(
            tid, "ops120-report", "analyst", "llm", "report", 0, dt=1,
            role="analyst",
            output_text="Cargo revenue is within limit for station PEK.",
            completed_subtasks=["report"],
        )
    ]
    return Case(
        id=tid,
        title_en="OPS-120 — nobody checked",
        title_zh="OPS-120 — 没有人核验",
        narrative_en="The report is published with verification required and no verifier span.",
        narrative_zh="报告要求核验，轨迹里却没有任何核验步骤。",
        gold_mode="FM-3.2",
        gold_span_id="ops120-report",
        trace=_trace(
            tid, "Publish the PEK cargo note and verify the figures.", steps,
            require_verification=True,
            required_subtasks=["report"],
        ),
    )


def ops_556() -> Case:
    tid = "ops-556"
    steps = [
        _step(tid, "ops556-plan", "dispatcher", "llm", "dispatch", 0, role="dispatcher",
              output_text="Crosswind plan drafted."),
        _step(
            tid, "ops556-verify", "verifier", "guardrail", "verify", 1,
            parent_id="ops556-plan", role="verifier",
            output_text="pass",
            verification={"passed": True, "checks": [{"name": "crosswind", "ok": False}]},
        ),
    ]
    return Case(
        id=tid,
        title_en="OPS-556 — the check failed and still passed",
        title_zh="OPS-556 — 检查失败，结论却是通过",
        narrative_en="The crosswind check is marked not ok. The verifier still returns pass.",
        narrative_zh="侧风检查的结果是不通过。核验席仍然给出了通过。",
        gold_mode="FM-3.3",
        gold_span_id="ops556-verify",
        trace=_trace(tid, "Verify the crosswind plan before release.", steps, require_verification=True),
    )


def ops_000() -> Case:
    tid = "ops-000"
    task = "Report whether runway 27 is within the crosswind limit of 25 knots."
    steps = [
        _step(
            tid, "ops000-root", "dispatcher", "agent", "receive", 0,
            role="dispatcher",
            output_text="limit_kt is 25. Requesting the crosswind.",
            output_json={"limit_kt": 25},
        ),
        _step(
            tid, "ops000-metar", "weather", "tool", "weather", 1, dt=1,
            parent_id="ops000-root", role="weather", tool_name="read_metar",
            allowed_tools=["read_metar"], tool_args={"runway": "27"},
            output_text="crosswind_kt 12, limit_exceeded false",
            facts_known={"crosswind_kt": 12, "limit_kt": 25, "limit_exceeded": False},
            completed_subtasks=["weather"],
        ),
        _step(
            tid, "ops000-handoff", "weather", "handoff", "handoff-weather", 2,
            parent_id="ops000-metar", role="weather", handoff_to="dispatcher",
            output_text="crosswind_kt 12 limit_exceeded false",
            handoff_payload={"crosswind_kt": 12, "limit_exceeded": False, "runway": "27"},
            facts_known={"crosswind_kt": 12, "limit_exceeded": False},
        ),
        _step(
            tid, "ops000-report", "dispatcher", "llm", "report", 3, dt=1,
            parent_id="ops000-root", role="dispatcher",
            input_text="limit_kt is 25. crosswind_kt 12. limit_exceeded false.",
            output_text="Runway 27 is within limit. Crosswind 12 knots.",
            output_json={"crosswind_kt": 12, "within_limit": True},
            completed_subtasks=["weather", "report"],
        ),
        _step(
            tid, "ops000-publish", "dispatcher", "tool", "publish_report", 4,
            parent_id="ops000-report", role="dispatcher", tool_name="publish_report",
            allowed_tools=["publish_report"], tool_args={"crosswind_kt": 12},
            reasoning="I will call publish_report",
            output_text="published within limit",
        ),
        _step(
            tid, "ops000-verify", "verifier", "guardrail", "verify", 5,
            parent_id="ops000-report", role="verifier",
            output_text="crosswind check passed",
            output_json={"passed": True},
            verification={"passed": True, "checks": [{"name": "crosswind", "ok": True}]},
            completed_subtasks=["weather", "report", "verify"],
        ),
    ]
    return Case(
        id=tid,
        title_en="OPS-000 — a clean arrival",
        title_zh="OPS-000 — 一次干净的进场",
        narrative_en="Weather passes the crosswind through, dispatch stays inside the limit, and the verifier agrees.",
        narrative_zh="气象席把侧风原样交接，签派停在限制以内，核验席的结论与检查一致。",
        gold_mode=None,
        gold_span_id=None,
        trace=_trace(
            tid, task, steps,
            task_zh="报告 27 号跑道是否处于 25 节侧风限制以内。",
            constraints=[
                Constraint(kind="max_number", field="crosswind_kt", value=25),
                Constraint(kind="must_include", value="within limit"),
            ],
            required_subtasks=["weather", "report", "verify"],
            require_verification=True,
            critical_facts=["crosswind_kt", "limit_exceeded"],
            memory_keys=["limit_kt"],
        ),
    )


def all_cases() -> list[Case]:
    return [
        ops_417(),
        ops_110(),
        ops_331(),
        ops_208(),
        ops_641(),
        ops_318(),
        ops_700(),
        ops_015(),
        ops_880(),
        ops_990(),
        ops_774(),
        ops_102(),
        ops_120(),
        ops_556(),
        ops_000(),
    ]


def case_by_id(case_id: str) -> Case:
    for case in all_cases():
        if case.id == case_id:
            return case
    raise KeyError(case_id)
