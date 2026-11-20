import type { CSSProperties, ReactNode } from "react";
import { decisions, TYPE_LABEL } from "../../data";

/* The 2D story figure for #/home-b, adapted from Stage.tsx (which #/home-v1 still uses).
   Governance-led order, six states. Sizes are viewBox units. Every decision is one pill and one dot;
   a pose table places them per step and CSS transitions do the morphing. */

export const STEP_COUNT = 6;
const HEADER = [
  "Session → 9 decisions",
  "Human decisions · 2 overrules",
  "Agent decisions · skill check",
  "Same overrule · 11 sessions",
  "Approve · set the rule",
  "Published · every agent",
];

const TX = [
  "wrap send() so errors…",
  "adding tenacity for…",
  "Don't add a library…",
  "Retrying 5x, expo…",
  "flaky, so skip it…",
  "No skipping tests…",
  "Retry in _send_single…",
  "Has to work for Async…",
  "Full test coverage…",
];

const laneX = (who: string) => (who === "agent" ? 18 : 212);
const rowY = (i: number) => 66 + i * 44;

interface Pose { x: number; y: number; o: number; s: number }

const struck = new Set(["d2", "d5"]);
const hot = new Set(["d3", "d6"]);

function pillPose(i: number, step: number): Pose {
  const d = decisions[i];
  const lane = { x: laneX(d.who), y: rowY(i) };
  if (step === 0) return { x: 212, y: rowY(i), o: 1, s: 1 };
  if (step === 1) return { ...lane, o: hot.has(d.id) ? 1 : struck.has(d.id) ? 0.7 : 0.22, s: 1 };
  if (step === 2) return { ...lane, o: d.who === "agent" ? 1 : 0.22, s: 1 };
  return { ...lane, o: 0, s: 0.96 };
}

function dotPose(i: number, step: number): Pose {
  const d = decisions[i];
  const shelf = { x: 40 + i * 40, y: 470 };
  const lane = { x: laneX(d.who) + 14, y: rowY(i) + 19 };
  if (step === 0) return { x: 226, y: rowY(i) + 19, o: 1, s: 1 };
  if (step === 1) return { ...lane, o: hot.has(d.id) || struck.has(d.id) ? 1 : 0.25, s: 1 };
  if (step === 2) return { ...lane, o: d.who === "agent" ? 1 : 0.25, s: 1 };
  if (step === 3) return d.id === "d3" ? { x: 200, y: 150, o: 1, s: 2.2 } : { ...shelf, o: 0.4, s: 1 };
  if (step === 4) return d.id === "d3" ? { x: 46, y: 137, o: 1, s: 1.2 } : { ...shelf, o: 0, s: 1 };
  return d.id === "d3" ? { x: 46, y: 191, o: 1, s: 1.2 } : { ...shelf, o: 0, s: 1 };
}

function extraPose(j: number, step: number): Pose {
  if (step === 3) {
    const a = (j / 10) * Math.PI * 2 - Math.PI / 2;
    return { x: 200 + Math.cos(a) * 120, y: 150 + Math.sin(a) * 56, o: 1, s: 1 };
  }
  if (step > 3) return { x: 46, y: 137, o: 0, s: 0.3 };
  return { x: 200, y: 150, o: 0, s: 0.3 };
}

const place = (p: Pose, delay: number): CSSProperties => ({
  transform: `translate(${p.x}px, ${p.y}px) scale(${p.s})`,
  opacity: p.o,
  transitionDelay: `${delay}ms`,
});

function Layer({ on, children }: { on: boolean; children: ReactNode }) {
  return <g className="hb-layer" data-on={on}>{children}</g>;
}
const st = (i: number): CSSProperties => ({ ["--i" as string]: i });
function At({ x, y, i = 0, children }: { x: number; y: number; i?: number; children: ReactNode }) {
  return <g transform={`translate(${x},${y})`}><g className="hb-st" style={st(i)}>{children}</g></g>;
}

// one row of the approve form: label, then options with the chosen one highlighted
function FormRow({ y, label, opts, pick, i }: { y: number; label: string; opts: string[]; pick: number; i: number }) {
  return (
    <At x={20} y={y} i={i}>
      <text y="14" className="hb-st-small">{label}</text>
      {opts.map((o, k) => (
        <g key={o} transform={`translate(${104 + k * 66},0)`}>
          <rect width="60" height="22" rx="11" className={`hb-opt ${k === pick ? "on" : ""}`} style={st(i)} />
          <text x="30" y="15" textAnchor="middle" className={`hb-opt-t ${k === pick ? "on" : ""}`}>{o}</text>
        </g>
      ))}
    </At>
  );
}

export default function StageB({ step }: { step: number }) {
  const on = (...s: number[]) => s.includes(step);
  const types = ["architecture", "dependency", "retries", "test", "design", "scope"] as const;
  const checked = decisions.filter((d) => d.who === "agent" && d.rule);

  return (
    <svg className="hb-stage-svg" viewBox="0 0 400 500" role="img" aria-label={`Unpack figure, step ${step + 1} of ${STEP_COUNT}: ${HEADER[step]}`}>
      <rect x="0.5" y="0.5" width="399" height="499" rx="20" className="hb-st-card" />
      <g key={step}><text x="20" y="30" className="hb-st-title">{HEADER[step]}</text></g>
      <text x="380" y="30" textAnchor="end" className="hb-st-count">{String(step + 1).padStart(2, "0")}/{String(STEP_COUNT).padStart(2, "0")}</text>

      {/* 0: transcript on the left, typed decisions on the right */}
      <Layer on={on(0)}>
        <text x="18" y="52" className="hb-lane">SESSION TRANSCRIPT</text>
        <text x="382" y="52" textAnchor="end" className="hb-lane">DECISIONS · TYPED</text>
        {decisions.map((d, i) => (
          <g key={d.id} className="hb-st" style={st(i)}>
            <text x="18" y={rowY(i) + 23} className={`hb-tx-turn ${d.who}`}>T{d.turn}</text>
            <text x="48" y={rowY(i) + 23} className="hb-tx-text">{TX[i]}</text>
            <line x1="188" x2="206" y1={rowY(i) + 19} y2={rowY(i) + 19} className="hb-tick" />
          </g>
        ))}
        {types.map((t, k) => (
          <g key={t} transform={`translate(${[18, 101, 174, 232, 274, 327][k]},486)`} className={`t-${t}`}>
            <circle r="3.5" cy="-3" className="hb-legend-dot" />
            <text x="9" className="hb-st-legend">{TYPE_LABEL[t]}</text>
          </g>
        ))}
      </Layer>

      {/* 1-2: lanes */}
      <Layer on={on(1, 2)}>
        <text x="18" y="52" className="hb-lane agent">AGENT DECIDED</text>
        <text x="382" y="52" textAnchor="end" className="hb-lane human">HUMAN DECIDED</text>
        <line x1="200" y1="62" x2="200" y2="462" className="hb-spine" />
      </Layer>

      {/* 1: the human chip points at the agent chip it overruled */}
      <Layer on={on(1)}>
        {decisions.filter((d) => d.overrides).map((d, k) => {
          const from = decisions.indexOf(d), to = decisions.findIndex((x) => x.id === d.overrides);
          const y1 = rowY(from) + 19, y2 = rowY(to) + 19;
          return <path key={d.id} className="hb-st hb-arrow" style={st(k * 3)} d={`M212 ${y1} C 196 ${y1}, 196 ${y2}, 190 ${y2}`} />;
        })}
        <text x="200" y="486" textAnchor="middle" className="hb-st-small">YOUR WORDS, THE PROPOSAL, THE TURN</text>
      </Layer>

      {/* 2: skill check beside each agent decision */}
      <Layer on={on(2)}>
        {checked.map((d) => {
          const i = decisions.indexOf(d), ok = d.rule!.status === "followed";
          return (
            <g key={d.id} transform={`translate(200,${rowY(i) + 19})`}>
              <g className="hb-st" style={st(i)}>
                <circle r="8" className={`hb-badge ${ok ? "ok" : "bad"}`} />
                <text y="3.5" textAnchor="middle" className="hb-badge-t">{ok ? "✓" : "✕"}</text>
              </g>
            </g>
          );
        })}
        <text x="200" y="486" textAnchor="middle" className="hb-st-small">SKILL CHECK · 2 FOLLOWED · 3 VIOLATED</text>
      </Layer>

      {/* pills */}
      {decisions.map((d, i) => (
        <g key={d.id} className={`hb-el hb-pill ${d.who} ${struck.has(d.id) && step === 1 ? "struck" : ""} t-${d.type}`} style={place(pillPose(i, step), i * 40)}>
          <rect width="170" height="38" rx="10" className="hb-pill-bg" />
          <text x="30" y="16" className="hb-pill-label">{d.label}</text>
          <text x="30" y="29" className="hb-pill-meta">{TYPE_LABEL[d.type]} · T{d.turn}</text>
          <line x1="30" x2="150" y1="12" y2="12" className="hb-strike" />
        </g>
      ))}

      {/* 3: the same overrule from many sessions is a candidate */}
      <Layer on={on(3)}>
        <text x="200" y="84" textAnchor="middle" className="hb-st-small">SAME OVERRULE · 11 SESSIONS · 3 TEAMS · 7 DEVELOPERS</text>
        <At x={24} y={276} i={3}>
          <rect width="352" height="140" rx="16" className="hb-card" />
          <text x="20" y="30" className="hb-st-small">POLICY CANDIDATE</text>
          <text x="20" y="62" className="hb-card-h">Add no new runtime dependency</text>
          <text x="20" y="84" className="hb-card-h">without approval.</text>
          <rect x="20" y="104" width="200" height="22" rx="11" className="hb-meets" />
          <text x="120" y="119" textAnchor="middle" className="hb-meets-t">MEETS ≥3 SESSIONS · ≥2 DEVS</text>
        </At>
      </Layer>
      {Array.from({ length: 10 }, (_, j) => (
        <circle key={j} r="5" className="hb-el hb-extra" style={place(extraPose(j, step), j * 30)} />
      ))}

      {/* 4: approve, with scope, enforcement and expiry */}
      <Layer on={on(4)}>
        <At x={24} y={80}>
          <rect width="352" height="330" rx="16" className="hb-card" />
          <text x="20" y="28" className="hb-st-small">GOVERNANCE INBOX · P-12</text>
        </At>
        <At x={24} y={80} i={1}>
          <text x="40" y="62" className="hb-card-h">Add no new runtime</text>
          <text x="40" y="84" className="hb-card-h">dependency without approval.</text>
        </At>
        <At x={24} y={80} i={2}><line x1="20" x2="332" y1="104" y2="104" className="hb-hair" /></At>
        <g transform="translate(24,80)">
          <FormRow y={122} label="SCOPE" opts={["repo", "team", "org"]} pick={2} i={3} />
          <FormRow y={158} label="ENFORCE" opts={["advice", "PR check", "gate"]} pick={1} i={5} />
          <FormRow y={194} label="EXPIRES" opts={["2027-03"]} pick={0} i={7} />
          <At x={20} y={240} i={9}>
            <rect width="120" height="34" rx="17" className="hb-approve" />
            <text x="60" y="22" textAnchor="middle" className="hb-btn-t on">Approve</text>
            <text x="140" y="22" className="hb-btn-t">Edit</text>
            <text x="184" y="22" className="hb-btn-t">Reject</text>
          </At>
          <At x={20} y={302} i={12}>
            <text className="hb-st-small">OUTPUTS · AGENTS.md +1 rule · PR check added</text>
          </At>
        </g>
        <text x="200" y="450" textAnchor="middle" className="hb-st-small">EVERY RULE HAS AN OWNER AND AN EXPIRY</text>
      </Layer>

      {/* 5: the skill file, and the override rate falls */}
      <Layer on={on(5)}>
        <At x={24} y={70}>
          <rect width="352" height="190" rx="14" className="hb-card hb-mono-card" />
          <text x="20" y="28" className="hb-file">skills/dependencies.md</text>
          <text x="20" y="62" className="hb-md-h"># Dependencies</text>
          <g className="hb-type">
            <text x="40" y="126" className="hb-md">Add no new runtime dependency</text>
            <text x="40" y="146" className="hb-md">without approval. Write it with</text>
            <text x="40" y="166" className="hb-md">what the repo already has.</text>
          </g>
          <text x="40" y="96" className="hb-md dim">- P-12 · owner @platform · expires 2027-03</text>
        </At>
        <At x={24} y={290} i={5}>
          <text className="hb-st-small">REPEAT OVERRIDES PER 100 SESSIONS · SIMULATED</text>
          <rect y="14" width="352" height="12" rx="6" className="hb-bar-bg" />
          <rect y="14" width="352" height="12" rx="6" className="hb-bar before" />
          <text y="48" className="hb-md">before 11</text>
          <rect y="62" width="352" height="12" rx="6" className="hb-bar-bg" />
          <rect y="62" width="352" height="12" rx="6" className="hb-bar after" />
          <text y="96" className="hb-md">after 3</text>
        </At>
        <path className="hb-st hb-loop" style={st(8)} d="M366 424 C 366 462, 34 462, 34 424" />
        <text x="200" y="484" textAnchor="middle" className="hb-st-small">BACK INTO EVERY AGENT'S CONTEXT</text>
      </Layer>

      {/* dots last so they ride above everything */}
      {decisions.map((d, i) => (
        <g key={d.id} className={`hb-el hb-dot ${d.who} t-${d.type}`} style={place(dotPose(i, step), i * 40 + 120)}>
          {d.who === "human" && <circle r="9" className="hb-ring" />}
          <circle r="5.5" className="hb-core" />
        </g>
      ))}
    </svg>
  );
}
