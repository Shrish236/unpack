import { useMemo } from "react";
import type { ReactNode } from "react";
import { Bot, CAST, Person, type Expr } from "./kit";

/* The road: vertical scroll drives horizontal travel. One world, five parallax layers.
   Pip's world x = 300 + p * TRAVEL; the camera follows so Pip stays at x = 300 on screen. */

const TRAVEL = 6000;
const MAIN = 415, UP = 375, LOW = 445;
const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const ease = (t: number) => t * t * (3 - 2 * t);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

function laneY(x: number) {
  if (x < 1600) return MAIN;
  if (x < 1950) return lerp(MAIN, UP, ease((x - 1600) / 350));
  if (x < 2520) return UP;
  if (x < 3000) return lerp(UP, LOW, ease((x - 2520) / 480));
  return LOW;
}

export const STATIONS = [
  { k: "Task", t: "A task for Pip", d: "A developer hands Pip a task: add retry with backoff. Pip is an agent. Quick, confident, and it decides things on its own.", f: "Every decision Pip makes is recorded and typed.", cast: [] as string[] },
  { k: "Fork", t: "A fork in the road", d: "Pip reaches a decision and picks a library. Nobody asked for one.", f: "Recorded: Dependency · agent · T16 · unrequested.", cast: [] },
  { k: "Guard", t: "The crossing guard", d: "You step in. “No new library. Use what we have.” Pip takes the detour.", f: "Recorded: redirect · human · T18 · your exact words.", cast: ["priya"] },
  { k: "Archive", t: "The archive", d: "Lena files your words. Tomás and Sofia are stopping Bolt and Nova at the same fork, and the cards pile up.", f: "11 sessions · 3 teams · 7 developers: a policy candidate.", cast: ["lena", "tomas", "sofia"] },
  { k: "Council", t: "The council", d: "Amara and Kenji read the evidence once and decide for everyone.", f: "Approved: scope org · enforcement PR check · expires 2027-03.", cast: ["amara", "kenji"] },
  { k: "Training", t: "The training ground", d: "The rule becomes a branch on the skill tree. Pip, Bolt and Nova each grow a leaf, and Marcus watches trust rise.", f: "Published to AGENTS.md and skill files. Autonomy: PR check → gate relaxed.", cast: ["marcus"] },
  { k: "Again", t: "The road again", d: "Pip reaches the same fork. The signpost already points the right way, and Priya waves.", f: "Repeat overrides: 11 → 3 per 100 sessions.", cast: ["priya"] },
];

function hillPath(x0: number, x1: number, base: number, amp: number, seed: number) {
  let d = `M${x0},900 L${x0},${base}`;
  for (let x = x0; x <= x1; x += 40) d += ` L${x},${(base - amp * (Math.sin(x * 0.006 + seed) + 0.5 * Math.sin(x * 0.017 + seed * 2) + 1)).toFixed(1)}`;
  return d + ` L${x1},900Z`;
}

function Bubble({ x, y, children, human, show = true }: { x: number; y: number; children: ReactNode; human?: boolean; show?: boolean }) {
  return <div className={`c3-bubble${human ? " human" : ""}${show ? " on" : ""}`} style={{ left: x, top: y }}>{children}</div>;
}

function Sign({ x, y, text, dir = 0, flip }: { x: number; y: number; text: string; dir?: number; flip?: boolean }) {
  const w = 12 + text.length * 7.2;
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x="-2" y="-62" width="4" height="62" rx="1.5" fill="#6b5a46" />
      <g transform={`translate(0 -56) rotate(${dir})`}>
        <path d={flip ? `M2,-12 H${-w} L${-w - 10},0 L${-w},12 H2Z` : `M-2,-12 H${w} L${w + 10},0 L${w},12 H-2Z`} fill="#e9e2d2" stroke="#6b5a46" strokeWidth="1.5" />
        <text x={flip ? -w / 2 - 2 : w / 2 + 2} y="4" textAnchor="middle" fontSize="11.5" fontFamily="var(--font-mono)" fill="#3a3326">{text}</text>
      </g>
    </g>
  );
}

export default function Road({ p, size, live }: { p: number; size: { w: number; h: number }; live: boolean }) {
  const p6 = p * 6, cx = p * TRAVEL;
  const scale = Math.max(size.w / 1000, size.h / 560, 0.2);
  const Hv = size.h / scale, Wv = size.w / scale;
  const yTop = clamp(445 - 0.72 * Hv, -200, 200);
  const pr = (k: number, len = 0.6) => clamp((p6 - (k - 0.6)) / len);
  // On narrow screens Pip sits further left so the guard and props ahead stay in frame.
  const cxv = cx + 300 - Math.min(300, Wv * 0.3);
  const px = (wx: number, wy: number) => ({ x: Math.min(Math.max((wx - cxv) * scale, 85), size.w - 85), y: (wy - yTop) * scale });

  const pipX = 300 + cx;
  const pipY = laneY(pipX);
  const stopped = p6 > 2.0 && p6 < 2.32;
  const pipExpr: Expr = p6 < 2.0 ? "pleased" : p6 < 2.32 ? "frustrated" : p6 < 3 ? "thinking" : p6 < 4.9 ? "neutral" : "pleased";
  const show = (k: number, a = 0.1, b = 0.9) => p6 > k - a && p6 < k + b;

  const far = useMemo(() => hillPath(-200, 1700 + TRAVEL * 0.12, 380, 70, 1), []);
  const mid = useMemo(() => hillPath(-200, 1700 + TRAVEL * 0.4, 440, 38, 4), []);
  const trees = useMemo(() => Array.from({ length: 70 }, (_, i) => { const x = -100 + i * 62 + (i % 3) * 14; const h = 46 + ((i * 37) % 30); return `M${x},470 L${x + 17},${470 - h} L${x + 34},470Z`; }).join(" "), []);
  const tufts = useMemo(() => Array.from({ length: 120 }, (_, i) => ({ x: -100 + i * 82 + (i % 4) * 13, y: 520 + (i % 3) * 14, k: i % 5 })), []);

  const cards = Math.round(pr(3) * 11);
  const teams = Math.min(3, Math.ceil(cards / 4));
  const stamp = ease(pr(4));
  const grow = ease(pr(5, 0.55));
  const council = show(4, 0.35, 0.55);

  return (
    <div className="c3-scene" style={{ width: size.w, height: size.h }}>
      <div className="c3-dim" style={{ opacity: (1 - p) * 0.55 }} />
      <svg width={size.w} height={size.h} viewBox={`0 ${yTop} ${Wv} ${Hv}`} aria-hidden="true">
        {/* sun rises as the agent improves */}
        <g opacity={0.25 + 0.7 * p}><circle cx={Wv * 0.8} cy={160 + 90 * (1 - p)} r="70" fill="var(--human)" opacity="0.22" /><circle cx={Wv * 0.8} cy={160 + 90 * (1 - p)} r="34" fill="var(--human)" /></g>
        <g transform={`translate(${-cxv * 0.05} 0)`} className="c3-cloud">{[120, 520, 980, 1500, 2100, 2700].map((x, i) => <g key={x} transform={`translate(${x} ${90 + (i % 3) * 36})`}><ellipse rx="54" ry="14" /><ellipse cx="30" cy="-8" rx="32" ry="12" /></g>)}</g>
        <g transform={`translate(${-cxv * 0.12} 0)`}><path d={far} className="c3-far" /></g>
        <g transform={`translate(${-cxv * 0.4} 0)`}><path d={mid} className="c3-mid" /><path d={trees} className="c3-trees" /></g>

        <g transform={`translate(${-cxv} 0)`}>
          <rect x="-400" y="430" width="8400" height="500" className="c3-ground" />
          <g className="c3-bed" strokeLinecap="round" fill="none">
            <path d="M-400,415 H1600" /><path d="M1600,415 C1760,415 1790,375 1950,375 H2800" /><path d="M2520,375 C2700,375 2820,445 3000,445" />
            <path d="M1600,415 C1760,415 1790,445 1950,445 H7600" /><path d="M6350,445 C6450,445 6480,405 6600,405 H6860" />
          </g>
          <g className="c3-road-edge" strokeLinecap="round" fill="none" strokeDasharray="14 18"><path d="M-400,415 H1600" /><path d="M1950,445 H7600" /></g>

          {/* 0 · task */}
          <Sign x={640} y={400} text="Add retry with backoff" />
          {/* 1 · fork */}
          <Sign x={1660} y={396} text="add a library" dir={-14} />
          <Sign x={1740} y={430} text="use what we have" dir={14} />
          {/* barrier at the end of the library road */}
          <g transform="translate(2800 375)"><rect x="-4" y="-40" width="6" height="40" fill="#6b5a46" /><rect x="-34" y="-34" width="64" height="9" fill="#c9694a" /><rect x="-34" y="-16" width="64" height="9" fill="#e9e2d2" /></g>

          {/* 2 · guard */}
          <Person spec={CAST.priya} x={2400} y={352} scale={1.1} flip expr={p6 > 2.0 ? "neutral" : "pleased"} pose="stop" />
          {/* 3 · archive */}
          <g opacity={0.35 + 0.65 * ease(pr(3, 0.9))}>
            <Person spec={CAST.tomas} x={3450} y={398} scale={0.85} expr="neutral" pose="stop" />
            <Bot id="bolt" x={3540} y={398} scale={0.8} flip expr="frustrated" />
            <Person spec={CAST.sofia} x={3650} y={398} scale={0.85} expr="neutral" pose="stop" />
            <Bot id="nova" x={3740} y={398} scale={0.8} flip expr="frustrated" />
          </g>
          <g transform="translate(3865 438)">
            <path d="M-62,-6 V-62 L0,-98 L62,-62 V-6Z" fill="#8a7358" /><path d="M-70,-58 L0,-104 L70,-58 L58,-52 L0,-90 L-58,-52Z" fill="#6d4f3c" />
            <rect x="-22" y="-48" width="44" height="42" rx="3" fill="#3a3326" />
            <Person spec={CAST.lena} x={0} y={-6} scale={0.62} expr="pleased" pose="hold" />
            <g transform="translate(78 -4)">{Array.from({ length: cards }, (_, i) => <rect key={i} x={-14 + (i % 3) * 3} y={-8 - i * 4.2} width="28" height="9" rx="2" fill={i === cards - 1 ? "var(--human)" : "#efe9da"} stroke="#6b5a46" strokeWidth="0.8" />)}</g>
          </g>
          {/* 4 · council */}
          <g opacity={0.3 + 0.7 * ease(pr(4, 0.9))}>
            <Person spec={CAST.amara} x={4660} y={408} scale={1.05} expr="pleased" pose="stamp" />
            <Person spec={CAST.kenji} x={4745} y={408} scale={1.05} flip expr="neutral" pose="hold" />
            <rect x="4600" y="402" width="200" height="40" rx="6" fill="#8d8a84" /><rect x="4600" y="402" width="200" height="9" rx="4" fill="#a8a59e" />
            <rect x="4665" y="395" width="70" height="9" rx="2" fill="#efe9da" stroke="#6b5a46" strokeWidth="0.8" />
            <g transform={`translate(4700 396) rotate(-8) scale(${0.4 + 0.6 * stamp})`} opacity={stamp}><rect x="-30" y="-9" width="60" height="18" rx="3" fill="var(--human)" /><text y="4" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight="600" fill="#1e293b">APPROVED</text></g>
          </g>
          {/* 5 · training ground */}
          <g opacity={0.3 + 0.7 * ease(pr(5, 0.9))}>
            <rect x="5666" y="300" width="14" height="140" rx="5" fill="#7a5b43" />
            {[[-1, 340, 70], [1, 360, 90], [-1, 380, 60]].map(([d, y, l], i) => <g key={i}><path d={`M5673,${y} L${5673 + d * l},${y - 26}`} stroke="#7a5b43" strokeWidth="7" strokeLinecap="round" /><circle cx={5673 + d * l} cy={y - 28} r="11" fill="#6aa377" /></g>)}
            <path d={`M5673,320 L${5673 + 120 * grow},${320 - 54 * grow}`} stroke="var(--human)" strokeWidth="8" strokeLinecap="round" />
            <circle cx={5673 + 120 * grow} cy={320 - 54 * grow} r={13 * grow} fill="var(--human)" />
            <rect x="5790" y="350" width="86" height="64" rx="6" fill="#efe9da" stroke="#6b5a46" strokeWidth="1.2" />
            <rect x="5800" y="382" width="66" height="10" rx="5" fill="#cdd3da" /><rect x="5800" y="382" width={66 * grow} height="10" rx="5" fill="var(--human)" />
            <rect x="5832" y="414" width="4" height="26" fill="#6b5a46" />
          </g>
          <Bot id="bolt" x={5440} y={444} scale={0.95} expr={p6 > 5 ? "pleased" : "neutral"} leaf={grow > 0.6} />
          <Bot id="nova" x={5540} y={444} scale={0.95} expr={p6 > 5 ? "pleased" : "neutral"} leaf={grow > 0.8} />
          <g opacity={0.3 + 0.7 * ease(pr(5, 0.9))}><Person spec={CAST.marcus} x={5930} y={440} scale={1.1} flip expr="pleased" pose="point" /></g>
          {/* 6 · the road again */}
          <g transform="translate(6580 408)"><rect x="-4" y="-40" width="6" height="40" fill="#6b5a46" /><rect x="-30" y="-34" width="60" height="9" fill="#c9694a" /><text y="-40" textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fill="var(--ink-3)">closed</text></g>
          <Sign x={6440} y={470} text="use what we have ✓" dir={12} />
          <Person spec={CAST.priya} x={6800} y={402} scale={1.0} flip expr="pleased" pose={p6 > 5.7 ? "wave" : "down"} />

          {/* Pip, the hero */}
          <Bot id="pip" x={pipX} y={pipY} scale={1.15} expr={pipExpr} walk={live && !stopped} leaf={p6 > 5.2} />
        </g>

        <g transform={`translate(${-cxv * 1.25} 0)`} className="c3-fg">
          {tufts.map((t, i) => <g key={i} transform={`translate(${t.x} ${t.y})`}><path d="M0,0 L-5,-14 M0,0 L0,-18 M0,0 L5,-13" />{t.k === 0 && <circle cx="9" cy="-12" r="3.2" fill="var(--human)" />}</g>)}
        </g>
      </svg>

      {/* speech bubbles are HTML so type stays on the product scale */}
      {(() => { const a = px(pipX, pipY - 150); return <Bubble x={a.x} y={a.y} show={live && (show(0, 0.1, 0.7) || show(1, 0.05, 0.6) || (p6 > 2.1 && p6 < 2.9) || p6 > 5.7)}>
        {p6 < 1 ? "Retry with backoff. On it." : p6 < 2 ? "Easy. There is a library for that." : p6 < 3 ? (stopped ? "Hm. OK." : "Fine, I will use what we have.") : "Using what we have."}
      </Bubble>; })()}
      {(() => { const a = px(2400, 352 - 122); return <Bubble x={a.x} y={a.y} human show={live && p6 > 1.95 && p6 < 2.9}>No new library. Use what we have.</Bubble>; })()}
      {(() => { const a = px(3865, 438 - 120); return <Bubble x={a.x} y={a.y} human show={live && show(3, 0.4, 0.9)}>Filed: T18 “No new library”<b>{cards} · {teams} teams</b></Bubble>; })()}
      {(() => { const a = px(3450, 398 - 100); return <Bubble x={a.x} y={a.y} human show={live && show(3, 0.4, 0.8)}>Not here either.</Bubble>; })()}
      {(() => { const a = px(4700, 408 - 125); return <Bubble x={a.x} y={a.y} human show={live && council && stamp > 0.5}>Approved<b>org · PR check · expires 2027-03</b></Bubble>; })()}
      {(() => { const a = px(5673 + 120, 250); return <Bubble x={a.x} y={a.y} human show={live && grow > 0.7 && p6 < 5.9}>No new runtime dependency</Bubble>; })()}
      {(() => { const a = px(5833, 345); return <Bubble x={a.x} y={a.y} show={live && grow > 0.6 && p6 < 5.9}>Autonomy<b>PR check → gate relaxed</b></Bubble>; })()}
      {(() => { const a = px(6800, 402 - 122); return <Bubble x={a.x} y={a.y} human show={live && p6 > 5.8}>Nice.<b>overrides 11 → 3</b></Bubble>; })()}
    </div>
  );
}
