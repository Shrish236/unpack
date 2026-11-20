import type { CSSProperties, ReactNode } from "react";
import { decisions, TYPE_LABEL } from "../data";

/* The centre figure. One SVG, eight states. Sizes below are viewBox units, not CSS px.
   Every decision is one pill and one dot. A pose table says where each sits in each step;
   CSS transitions do the morphing, so the same objects travel
   diff -> transcript -> ledger lanes -> overrules -> criteria -> claim -> policy -> skill. */

export const STEP_COUNT = 8;
const HEADER = [
  "PR #482 · +1,204 −311 · 14 files",
  "Session → 9 decisions",
  "Who decided · skill check",
  "Overrules · 2",
  "Acceptance criteria · 4",
  "Claim · checked against code",
  "Policy candidate · simulated",
  "Skill updated · every agent",
];

// what the transcript says at each decision's turn (same order as `decisions`)
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

// criterion slots for the ladders step: group decisions by criterion, in order
const slots = (() => {
  const seen: Record<string, number> = {};
  const rows = ["AC1", "AC2", "AC3", "AC4"];
  const out: Record<string, [number, number]> = {};
  decisions.forEach((d) => {
    if (!d.criterion) return;
    const k = (seen[d.criterion] = (seen[d.criterion] ?? -1) + 1);
    out[d.id] = [34 + k * 28, 84 + rows.indexOf(d.criterion) * 88 + 34];
  });
  return out;
})();

interface Pose { x: number; y: number; o: number; s: number }

const struck = new Set(["d2", "d5"]);
const hot = new Set(["d3", "d6"]);

function pillPose(i: number, step: number): Pose {
  const d = decisions[i];
  const lane = { x: laneX(d.who), y: rowY(i) };
  if (step === 0) return { x: 115, y: 231, o: 0, s: 0.5 };
  if (step === 1) return { x: 212, y: rowY(i), o: 1, s: 1 }; // everything extracted into one column, beside the transcript
  if (step === 2) return { ...lane, o: 1, s: 1 };
  if (step === 3) return { ...lane, o: hot.has(d.id) ? 1 : struck.has(d.id) ? 0.7 : 0.22, s: 1 };
  return { ...lane, o: 0, s: 0.96 };
}

function dotPose(i: number, step: number): Pose {
  const d = decisions[i];
  const shelf = { x: 40 + i * 40, y: 470 };
  if (step === 0) return { x: 200, y: 250, o: 0, s: 0.5 };
  if (step === 1) return { x: 226, y: rowY(i) + 19, o: 1, s: 1 };
  if (step === 2) return { x: laneX(d.who) + 14, y: rowY(i) + 19, o: 1, s: 1 };
  if (step === 3) return { x: laneX(d.who) + 14, y: rowY(i) + 19, o: hot.has(d.id) || struck.has(d.id) ? 1 : 0.25, s: 1 };
  if (step === 4) return d.criterion ? { x: slots[d.id][0], y: slots[d.id][1], o: 1, s: 1 } : { ...shelf, o: 0, s: 1 };
  if (step === 5) return d.id === "d9" ? { x: 36, y: 114, o: 1, s: 1.3 } : { ...shelf, o: 0.5, s: 1 };
  if (step === 6) return d.id === "d3" ? { x: 200, y: 150, o: 1, s: 2.2 } : { ...shelf, o: 0.4, s: 1 };
  return d.id === "d3" ? { x: 46, y: 191, o: 1, s: 1.2 } : { ...shelf, o: 0, s: 1 };
}

function extraPose(j: number, step: number): Pose {
  if (step === 6) {
    const a = (j / 10) * Math.PI * 2 - Math.PI / 2;
    return { x: 200 + Math.cos(a) * 120, y: 150 + Math.sin(a) * 56, o: 1, s: 1 };
  }
  if (step === 7) return { x: 46, y: 191, o: 0, s: 0.3 };
  return { x: 200, y: 150, o: 0, s: 0.3 };
}

const place = (p: Pose, delay: number): CSSProperties => ({
  transform: `translate(${p.x}px, ${p.y}px) scale(${p.s})`,
  opacity: p.o,
  transitionDelay: `${delay}ms`,
});

// deterministic "diff wall"
const wall = Array.from({ length: 17 }, (_, k) => ({
  w: 70 + ((k * 53) % 250),
  kind: k % 5 === 1 ? "del" : k % 3 === 0 ? "ctx" : "add",
}));

function Layer({ on, children }: { on: boolean; children: ReactNode }) {
  return <g className="layer" data-on={on}>{children}</g>;
}
const st = (i: number): CSSProperties => ({ ["--i" as string]: i });

// Position with an attribute on the outer <g>; the rise animation runs on the inner one, so they never fight over `transform`.
function At({ x, y, i = 0, children }: { x: number; y: number; i?: number; children: ReactNode }) {
  return <g transform={`translate(${x},${y})`}><g className="st" style={st(i)}>{children}</g></g>;
}

export default function Stage({ step }: { step: number }) {
  const on = (...s: number[]) => s.includes(step);
  const types = ["architecture", "dependency", "retries", "test", "design", "scope"] as const;
  const checked = decisions.filter((d) => d.who === "agent" && d.rule);

  return (
    <svg className="stage-svg" viewBox="0 0 400 500" role="img" aria-label={`Unpack figure, step ${step + 1} of ${STEP_COUNT}: ${HEADER[step]}`}>
      <rect x="0.5" y="0.5" width="399" height="499" rx="20" className="st-card" />

      <g key={step} className="st-head">
        <text x="20" y="30" className="st-title">{HEADER[step]}</text>
      </g>
      <text x="380" y="30" textAnchor="end" className="st-count">{String(step + 1).padStart(2, "0")}/{String(STEP_COUNT).padStart(2, "0")}</text>

      {/* 0: the diff wall and the agent's narration */}
      <Layer on={on(0)}>
        {wall.map((r, k) => (
          <rect key={k} className={`st wall ${r.kind}`} style={st(k)} x="24" y={60 + k * 19} width={r.w} height="7" rx="3.5" />
        ))}
        <At x={24} y={398} i={18}>
          <rect width="352" height="64" rx="14" className="bubble" />
          <text x="16" y="24" className="st-small">AGENT · FINAL MESSAGE</text>
          <text x="16" y="48" className="st-quote">“All done. Full test coverage.”</text>
        </At>
      </Layer>

      {/* 1: the transcript on the left, the extracted decisions on the right */}
      <Layer on={on(1)}>
        <text x="18" y="52" className="lane">SESSION TRANSCRIPT</text>
        <text x="382" y="52" textAnchor="end" className="lane typed">DECISIONS · TYPED</text>
        {decisions.map((d, i) => (
          <g key={d.id} className="st" style={st(i)}>
            <text x="18" y={rowY(i) + 23} className={`tx-turn ${d.who}`}>T{d.turn}</text>
            <text x="48" y={rowY(i) + 23} className="tx-text">{TX[i]}</text>
            <line x1="188" x2="206" y1={rowY(i) + 19} y2={rowY(i) + 19} className="tick" />
          </g>
        ))}
        {types.map((t, k) => (
          <g key={t} transform={`translate(${[18, 101, 174, 232, 274, 327][k]},486)`} className={`t-${t}`}>
            <circle r="3.5" cy="-3" className="legend-dot" />
            <text x="9" className="st-legend">{TYPE_LABEL[t]}</text>
          </g>
        ))}
      </Layer>

      {/* 2-3: lanes and spine */}
      <Layer on={on(2, 3)}>
        <text x="18" y="52" className="lane agent">AGENT DECIDED</text>
        <text x="382" y="52" textAnchor="end" className="lane human">HUMAN DECIDED</text>
        <line x1="200" y1="62" x2="200" y2="462" className="spine" />
      </Layer>

      {/* 2: skill check on the spine, beside each agent decision */}
      <Layer on={on(2)}>
        {checked.map((d) => {
          const i = decisions.indexOf(d), ok = d.rule!.status === "followed";
          return (
            <g key={d.id} transform={`translate(200,${rowY(i) + 19})`}>
              <g className="st" style={st(i)}>
                <circle r="8" className={`badge ${ok ? "ok" : "bad"}`} />
                <text y="3.5" textAnchor="middle" className="badge-t">{ok ? "✓" : "✕"}</text>
              </g>
            </g>
          );
        })}
        <text x="200" y="486" textAnchor="middle" className="st-small">SKILL CHECK · 2 FOLLOWED · 3 VIOLATED</text>
      </Layer>

      {/* pills */}
      {decisions.map((d, i) => {
        const cls = ["el pill", d.who, struck.has(d.id) && step === 3 ? "struck" : "", `t-${d.type}`].join(" ");
        return (
          <g key={d.id} className={cls} style={place(pillPose(i, step), i * 40)}>
            <rect width="170" height="38" rx="10" className="pill-bg" />
            <text x="30" y="16" className="pill-label">{d.label}</text>
            <text x="30" y="29" className="pill-meta">{TYPE_LABEL[d.type]} · T{d.turn}</text>
            <line x1="30" x2="150" y1="12" y2="12" className="strike" />
          </g>
        );
      })}

      {/* 3: the human chip points at the agent chip it overruled */}
      <Layer on={on(3)}>
        {decisions.filter((d) => d.overrides).map((d, k) => {
          const from = decisions.indexOf(d), to = decisions.findIndex((x) => x.id === d.overrides);
          const y1 = rowY(from) + 19, y2 = rowY(to) + 19;
          return <path key={d.id} className="st arrow" style={st(k * 3)} d={`M212 ${y1} C 196 ${y1}, 196 ${y2}, 190 ${y2}`} />;
        })}
        <text x="200" y="486" textAnchor="middle" className="st-small">AN OVERRULE IS THE MOST VALUABLE LINE IN A SESSION</text>
      </Layer>

      {/* 4: criteria ladders (the dots fly in from the lanes) */}
      <Layer on={on(4)}>
        {[
          ["AC1", "Retry 5xx with backoff", "first try", "ok"],
          ["AC2", "No new dependencies", "agent missed it", "agent"],
          ["AC3", "Tests green, none skipped", "agent missed it", "agent"],
          ["AC4", "Async behaves the same", "requirement thin", "warn"],
        ].map(([id, text, v, k], r) => (
          <At key={id} x={0} y={84 + r * 88} i={r * 2}>
            <line x1="20" x2="380" y1="-18" y2="-18" className="hair" />
            <text x="24" y="2" className="crit-id">{id}</text>
            <text x="58" y="2" className="crit-text">{text}</text>
            <text x="376" y="34" textAnchor="end" className={`verdict ${k}`}>{v}</text>
          </At>
        ))}
        <text x="24" y="478" className="st-small">● AGENT   ◎ HUMAN CORRECTION</text>
      </Layer>

      {/* 5: claim vs the code graph */}
      <Layer on={on(5)}>
        <text x="56" y="84" className="st-small">AGENT CLAIM (UNVERIFIED) · T47</text>
        <text x="56" y="124" className="st-quote xl">“Full test coverage.”</text>
        <line x1="24" x2="376" y1="150" y2="150" className="hair" />
        <text x="24" y="176" className="st-small">CODE GRAPH · TESTS THAT REACH EACH FUNCTION</text>
        <g className="st" style={st(2)}>
          <path d="M92 258 L200 258 M200 258 L308 258" className="edge" />
          {[["Client.send", 70, "2 tests", "ok"], ["_send_single", 200, "2 tests", "ok"], ["Async._send_single", 330, "0 tests", "bad"]].map(([n, x, t, k]) => (
            <g key={n as string} transform={`translate(${x},258)`}>
              <circle r="22" className={`node ${k}`} />
              <text y="5" textAnchor="middle" className="node-t">{k === "ok" ? "✓" : "✕"}</text>
              <text y="42" textAnchor="middle" className="node-n">{n as string}</text>
              <text y="56" textAnchor="middle" className={`node-c ${k}`}>{t as string}</text>
            </g>
          ))}
        </g>
        <g transform="translate(200,376)">
          <g className="stamp">
            <rect x="-104" y="-26" width="208" height="52" rx="8" className="stamp-box" />
            <text y="7" textAnchor="middle" className="stamp-t">UNSUPPORTED</text>
          </g>
        </g>
        <text x="200" y="436" textAnchor="middle" className="st-small">STATIC ESTIMATE · CODE DECIDES, THE MODEL ONLY EXTRACTS</text>
      </Layer>

      {/* 6: the policy candidate (extras are the other sessions) */}
      <Layer on={on(6)}>
        <text x="200" y="84" textAnchor="middle" className="st-small">THE SAME OVERRULE · 11 SESSIONS · 3 TEAMS</text>
        <At x={24} y={262} i={3}>
          <rect width="352" height="170" rx="16" className="card" />
          <text x="20" y="30" className="st-small">POLICY CANDIDATE</text>
          <text x="20" y="62" className="card-h">Add no new runtime dependency</text>
          <text x="20" y="84" className="card-h">without approval.</text>
          <text x="20" y="110" className="st-small">7 developers · scope: org · expires 2027-03</text>
          <g transform="translate(20,126)">
            <rect width="96" height="30" rx="15" className="approve" />
            <text x="48" y="19.5" textAnchor="middle" className="btn-t on">Approve</text>
            <text x="120" y="19.5" className="btn-t">Edit</text>
            <text x="164" y="19.5" className="btn-t">Reject</text>
          </g>
        </At>
      </Layer>
      {Array.from({ length: 10 }, (_, j) => (
        <circle key={j} r="5" className="el extra" style={place(extraPose(j, step), j * 30)} />
      ))}

      {/* 7: the skill file */}
      <Layer on={on(7)}>
        <At x={24} y={70}>
          <rect width="352" height="190" rx="14" className="card mono-card" />
          <text x="20" y="28" className="file">skills/dependencies.md</text>
          <text x="20" y="62" className="md-h"># Dependencies</text>
          <g className="type">
            <text x="40" y="126" className="md">Add no new runtime dependency</text>
            <text x="40" y="146" className="md">without approval. Write it with</text>
            <text x="40" y="166" className="md">what the repo already has.</text>
          </g>
          <text x="40" y="96" className="md dim">- P-12 · owner @platform · expires 2027-03</text>
        </At>
        <At x={24} y={290} i={5}>
          <text x="0" y="0" className="st-small">OVERRIDES PER 100 SESSIONS · SIMULATED</text>
          <rect y="14" width="352" height="12" rx="6" className="bar-bg" />
          <rect y="14" width="352" height="12" rx="6" className="bar before" />
          <text x="0" y="48" className="md">before 11</text>
          <rect y="62" width="352" height="12" rx="6" className="bar-bg" />
          <rect y="62" width="352" height="12" rx="6" className="bar after" />
          <text x="0" y="96" className="md">after 3</text>
        </At>
        <path className="st loop" style={st(8)} d="M366 424 C 366 462, 34 462, 34 424" />
        <text x="200" y="484" textAnchor="middle" className="st-small">BACK INTO EVERY AGENT'S CONTEXT</text>
      </Layer>

      {/* dots drawn last so they ride above everything */}
      {decisions.map((d, i) => (
        <g key={d.id} className={`el dot ${d.who} t-${d.type}`} style={place(dotPose(i, step), i * 40 + 120)}>
          {d.who === "human" && <circle r="9" className="ring" />}
          <circle r="5.5" className="core" />
        </g>
      ))}
    </svg>
  );
}
