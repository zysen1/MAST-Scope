"use client";

import { useEffect, useMemo, useState } from "react";

type Lang = "en" | "zh";

type Step = {
  span_id: string;
  agent: string;
  kind: string;
  name: string;
  started_at: number;
  ended_at: number;
  input_text: string;
  output_text: string;
  reasoning: string;
  tool_name: string | null;
  role: string | null;
};

type Finding = {
  id: string;
  mode: string;
  span_id: string;
  agent: string;
  evidence: string;
  mode_name_en: string;
  mode_name_zh: string;
  category_name_en: string;
  category_name_zh: string;
  category: string;
};

type Blame = {
  span_id: string;
  agent: string;
  mode: string;
  category: string;
  category_name_en: string;
  category_name_zh: string;
  mode_name_en: string;
  mode_name_zh: string;
  step_name: string;
  started_at: number;
  evidence: string;
  confidence: number;
  causal_chain: string[];
};

type Dossier = {
  id: string;
  title_en: string;
  title_zh: string;
  narrative_en: string;
  narrative_zh: string;
  gold_mode: string | null;
  task_en: string;
  task_zh: string;
  agents: string[];
  steps: Step[];
  findings: Finding[];
  blame: Blame | null;
  healthy: boolean;
  judge_backend: string;
  repair: {
    plan: {
      instruction_en: string;
      instruction_zh: string;
      preserved_span_ids: string[];
      replay_span_ids: string[];
      failed_subtask: string;
      failed_agent: string;
    } | null;
    root_cleared: boolean;
    fully_clean: boolean;
    steps: Step[];
  };
};

type IndexCase = { id: string; title_en: string; title_zh: string; gold_mode: string | null; healthy: boolean };

const COPY = {
  en: {
    kicker: "FLIGHT RECORDER  ·  MULTI-AGENT",
    dockets: "INCIDENT DOCKET",
    task: "TASK",
    play: "PLAY",
    pause: "PAUSE",
    fault: "FIRST FAULT",
    repair: "SHOW REPAIR",
    repairOn: "REPAIR ON",
    noFault: "NO FAULT RECORDED",
    evidence: "EVIDENCE",
    chain: "CAUSAL CHAIN",
    preserved: "FROZEN SIBLINGS",
    replay: "REPLAYED",
    before: "BEFORE",
    after: "AFTER",
    cleared: "Root failure cleared. Unrelated branches were not rerun.",
    seed: "Seeded incident. Expected root",
    healthySeed: "Seeded healthy trace. Detectors stay quiet.",
    judge: "Judge",
  },
  zh: {
    kicker: "黑匣子  ·  多智能体",
    dockets: "事故卷宗",
    task: "任务",
    play: "回放",
    pause: "暂停",
    fault: "第一故障点",
    repair: "显示修复",
    repairOn: "修复已叠加",
    noFault: "没有记录到故障",
    evidence: "证据",
    chain: "因果链",
    preserved: "冻结的旁路",
    replay: "重放",
    before: "修复前",
    after: "修复后",
    cleared: "根故障已消除。没有重跑无关分支。",
    seed: "种子事故。预期根因",
    healthySeed: "种子健康轨迹。检测器保持安静。",
    judge: "裁决",
  },
};

function callsign(agent: string): string {
  const known: Record<string, string> = {
    dispatcher: "DISPATCH",
    weather: "WEATHER",
    fuel: "FUEL",
    verifier: "VERIFY",
    maintenance: "MAINT",
    cabin: "CABIN",
    planner: "PLAN",
    buyer: "BUYER",
    coordinator: "COORD",
    clerk: "CLERK",
    analyst: "ANALYST",
    network: "NET",
    runtime: "RUNTIME",
    billing: "BILLING",
  };
  return known[agent] || agent.toUpperCase();
}

export default function Recorder() {
  const [lang, setLang] = useState<Lang>("en");
  const [index, setIndex] = useState<IndexCase[]>([]);
  const [active, setActive] = useState("ops-417");
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [playing, setPlaying] = useState(false);
  const [cursor, setCursor] = useState(1);
  const [picked, setPicked] = useState<string | null>(null);
  const [showRepair, setShowRepair] = useState(false);
  const copy = COPY[lang];

  useEffect(() => {
    fetch("/cases/index.json")
      .then((response) => response.json())
      .then((body: { cases: IndexCase[] }) => setIndex(body.cases))
      .catch(() => setIndex([]));
  }, []);

  useEffect(() => {
    setDossier(null);
    setPlaying(false);
    setCursor(1);
    setShowRepair(false);
    fetch(`/cases/${active}.json`)
      .then((response) => response.json())
      .then((body: Dossier) => {
        setDossier(body);
        setPicked(body.blame?.span_id ?? body.steps[0]?.span_id ?? null);
      })
      .catch(() => setDossier(null));
  }, [active]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setCursor((value) => {
        if (value >= 1) {
          setPlaying(false);
          return 1;
        }
        return Math.min(1, value + 0.02);
      });
    }, 50);
    return () => window.clearInterval(timer);
  }, [playing]);

  const view = useMemo(() => {
    if (!dossier) return null;
    const steps = showRepair ? dossier.repair.steps : dossier.steps;
    const agents = [...dossier.agents];
    for (const step of steps) {
      if (!agents.includes(step.agent)) agents.push(step.agent);
    }
    const min = Math.min(...steps.map((step) => step.started_at));
    const max = Math.max(...steps.map((step) => step.ended_at));
    const dur = Math.max(0.001, max - min);
    return { steps, agents, min, max, dur };
  }, [dossier, showRepair]);

  if (!dossier || !view) {
    return <main className="loading">MAST-SCOPE / loading recorder…</main>;
  }

  const blame = dossier.blame;
  const chain = new Set(blame?.causal_chain ?? []);
  const original = new Map(dossier.steps.map((step) => [step.span_id, step.output_text]));
  const title = lang === "en" ? dossier.title_en : dossier.title_zh;
  const narrative = lang === "en" ? dossier.narrative_en : dossier.narrative_zh;
  const task = lang === "zh" && dossier.task_zh ? dossier.task_zh : dossier.task_en;
  const now = view.min + cursor * view.dur;
  const faultStep = blame ? view.steps.find((step) => step.span_id === blame.span_id) : undefined;
  const pickedStep = view.steps.find((step) => step.span_id === picked) || faultStep || view.steps[0];
  const modeName = blame ? (lang === "en" ? blame.mode_name_en : blame.mode_name_zh) : "";
  const categoryName = blame ? (lang === "en" ? blame.category_name_en : blame.category_name_zh) : "";

  function jumpFault() {
    if (!blame) return;
    const at = (blame.started_at - view!.min) / view!.dur;
    setCursor(Math.min(1, Math.max(0.05, at + 0.04)));
    setPicked(blame.span_id);
    setPlaying(false);
  }

  const points = (blame?.causal_chain ?? [])
    .map((id) => view.steps.find((step) => step.span_id === id))
    .filter((step): step is Step => Boolean(step))
    .map((step) => {
      const lane = view.agents.indexOf(step.agent);
      const x = ((step.started_at + step.ended_at) / 2 - view.min) / view.dur * 100;
      const y = ((lane + 0.5) / view.agents.length) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <main className="app">
      <header className="top">
        <div className={`led ${dossier.healthy ? "ok" : ""}`} />
        <div className="brand">
          <b>MAST-SCOPE</b>
          <span>{copy.kicker}</span>
        </div>
        <div className="lang">
          <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")} type="button">EN</button>
          <button className={lang === "zh" ? "on" : ""} onClick={() => setLang("zh")} type="button">中文</button>
        </div>
        <div className="timecode" data-testid="timecode">
          T+{Math.max(0, now - view.min).toFixed(1)}s
        </div>
      </header>
      <section className="workspace">
        <aside className="cases">
          <h2>{copy.dockets}</h2>
          {index.map((item) => (
            <button
              key={item.id}
              className={item.id === active ? "on" : ""}
              onClick={() => setActive(item.id)}
              type="button"
            >
              <span className={item.healthy ? "tag ok" : "tag"}>{item.healthy ? "CLEAR" : item.gold_mode}</span>
              <small>{lang === "en" ? item.title_en : item.title_zh}</small>
            </button>
          ))}
        </aside>
        <section className="stage">
          <div className="stage-head">
            <div>
              <h2>{dossier.id.toUpperCase()}</h2>
              <p>{narrative}</p>
            </div>
            <div className="controls">
              <button
                type="button"
                onClick={() => {
                  if (cursor >= 1) setCursor(0);
                  setPlaying((value) => !value);
                }}
              >
                {playing ? copy.pause : copy.play}
              </button>
              <button type="button" onClick={jumpFault} disabled={!blame}>{copy.fault}</button>
              <button
                type="button"
                className={showRepair ? "repair-toggle on" : "repair-toggle"}
                onClick={() => setShowRepair((value) => !value)}
                disabled={!blame}
              >
                {showRepair ? copy.repairOn : copy.repair}
              </button>
            </div>
          </div>
          <div className="lanes" data-testid="lanes">
            {view.agents.map((agent) => (
              <div className="lane" key={agent}>
                <div className="lane-name">{callsign(agent)}</div>
                <div className="track" />
              </div>
            ))}
            <svg className="chain" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {points && (
                <polyline
                  points={points}
                  fill="none"
                  stroke="#e2a15a"
                  strokeWidth="1.5"
                  vectorEffect="non-scaling-stroke"
                />
              )}
            </svg>
            {faultStep && !showRepair && (
              <div
                className="fault-flag"
                style={{
                  left: `calc(108px + (100% - 108px) * ${((faultStep.started_at - view.min) / view.dur)})`,
                }}
              >
                FIRST FAULT
              </div>
            )}
            <div className="playhead" style={{ left: `calc(108px + (100% - 108px) * ${cursor})` }} />
            {view.steps.map((step) => {
              const lane = view.agents.indexOf(step.agent);
              const left = ((step.started_at - view.min) / view.dur) * 100;
              const width = Math.max(8, ((step.ended_at - step.started_at) / view.dur) * 100);
              const future = step.started_at > now + 1e-6;
              const isFault = blame?.span_id === step.span_id && !showRepair;
              const changed = showRepair && original.get(step.span_id) !== undefined && original.get(step.span_id) !== step.output_text;
              const classes = [
                "span",
                step.kind,
                future ? "future" : "",
                chain.has(step.span_id) ? "chain" : "",
                isFault ? "fault" : "",
                changed ? "changed" : "",
              ].filter(Boolean).join(" ");
              return (
                <button
                  key={step.span_id}
                  type="button"
                  className={classes}
                  data-testid={isFault ? "first-fault" : undefined}
                  style={{
                    left: `calc(108px + (100% - 108px) * ${left / 100})`,
                    width: `calc((100% - 108px) * ${width / 100})`,
                    top: lane * 64 + 16,
                  }}
                  title={`${step.agent} · ${step.name}`}
                  onClick={() => setPicked(step.span_id)}
                >
                  {shortLabel(step)}
                </button>
              );
            })}
          </div>
        </section>
        <aside className="dossier">
          <h2>{copy.task}</h2>
          <p className="task">{task}</p>
          {blame ? (
            <>
              <div className="seal" data-testid="mode-seal">{blame.mode} · {blame.category}</div>
              <h3>{modeName}</h3>
              <div className="meta">
                {categoryName}
                <br />
                {blame.agent} / {blame.step_name}
                <br />
                {copy.judge}: {dossier.judge_backend} · p={blame.confidence.toFixed(2)}
              </div>
              <h2 style={{ marginTop: 14 }}>{copy.evidence}</h2>
              <div className="quote">{pickedStep?.output_text || pickedStep?.reasoning || blame.evidence}</div>
              <h2>{copy.chain}</h2>
              <div className="chips">
                {blame.causal_chain.map((id) => {
                  const step = dossier.steps.find((item) => item.span_id === id);
                  return (
                    <span key={id} className={id === blame.span_id ? "root" : ""}>
                      {step ? `${callsign(step.agent)} ${step.name}` : id}
                    </span>
                  );
                })}
              </div>
              {dossier.findings.length > 1 && (
                <div className="meta">
                  {dossier.findings.map((finding) => (
                    <div key={finding.id}>
                      {finding.mode} {lang === "en" ? finding.mode_name_en : finding.mode_name_zh}
                      {finding.span_id === blame.span_id ? "  ← root" : ""}
                    </div>
                  ))}
                </div>
              )}
              {dossier.repair.plan && (
                <>
                  <h2 style={{ marginTop: 14 }}>{lang === "en" ? "REPLAN" : "重规划"}</h2>
                  <p className="task">
                    {lang === "en" ? dossier.repair.plan.instruction_en : dossier.repair.plan.instruction_zh}
                  </p>
                  <div className="meta">
                    {copy.preserved}: {dossier.repair.plan.preserved_span_ids.length}
                    {" · "}
                    {copy.replay}: {dossier.repair.plan.replay_span_ids.length}
                    {dossier.repair.fully_clean ? ` · ${copy.cleared}` : ""}
                  </div>
                  <div className="diff">
                    {changedSpans(dossier).map((pair) => (
                      <div key={pair.id} style={{ gridColumn: "1 / -1" }}>
                        <b>{pair.label}</b>
                        <div>{copy.before}: {pair.before || "—"}</div>
                        <div className="after">{copy.after}: {pair.after || (lang === "en" ? "span removed" : "该步骤已移除")}</div>
                      </div>
                    ))}
                  </div>
                </>
              )}
              <p className="meta" style={{ marginTop: 16 }}>
                {copy.seed} {dossier.gold_mode}.
              </p>
            </>
          ) : (
            <>
              <div className="seal">{copy.noFault}</div>
              <h3>{title}</h3>
              <p className="task">{copy.healthySeed}</p>
            </>
          )}
        </aside>
      </section>
    </main>
  );
}

function shortLabel(step: Step): string {
  if (step.kind === "handoff") return "HANDOFF";
  if (step.kind === "guardrail") return "CHECK";
  const raw = step.tool_name || step.name;
  return raw.length > 14 ? raw.slice(0, 13) + "…" : raw;
}

function changedSpans(dossier: Dossier): { id: string; label: string; before: string; after: string }[] {
  const after = new Map(dossier.repair.steps.map((step) => [step.span_id, step]));
  const rows = dossier.steps.flatMap((step) => {
    const next = after.get(step.span_id);
    const nextText = next?.output_text ?? "";
    if (next && nextText === step.output_text) return [];
    return [{
      id: step.span_id,
      label: `${step.agent} · ${step.name}`,
      before: step.output_text,
      after: next ? nextText : "",
    }];
  });
  return rows.slice(0, 3);
}
