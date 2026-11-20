import { useEffect, useRef, useState } from "react";
import { Avatar, Bot, BOTS, CAST, type BotKind, type Expr } from "./Avatars";

/* The pinned orbit: a journey panel on the left, concentric rings of people and agents on the right.
   Scrolling advances the step; before and after the pin it plays itself. Coordinates are in a 600x600 space. */

type Id = keyof typeof CAST | BotKind;
const POS: Record<string, [number, number, "t" | "b", "t" | "l" | "r"]> = {
  // x, y, name-card side, bubble side
  pip: [240, 214, "t", "l"], bolt: [360, 214, "t", "r"], nova: [300, 405, "b", "r"],
  priya: [117, 274, "b", "t"], tomas: [481, 338, "b", "t"],
  amara: [474, 104, "b", "r"], kenji: [82, 388, "b", "r"], lena: [349, 528, "b", "l"],
  sofia: [128, 79, "b", "r"], marcus: [537, 448, "b", "t"],
};
const HUB: [number, number] = [300, 300];
const RINGS = [{ r: 105, l: "" }, { r: 185, l: "I · CAPTURE" }, { r: 235, l: "II · REVIEW" }, { r: 280, l: "III · PUBLISH" }];
const BOT_IDS: Id[] = ["pip", "bolt", "nova"];

interface Step {
  t: string; s: string; dot: "agent" | "human" | "ok" | "mute";
  actors: Id[]; links: [Id | "hub", Id | "hub", "agent" | "human" | "ok"][]; docs?: [Id | "hub", Id | "hub"][];
  bubbles?: [Id, string][]; hub: string; expr?: Partial<Record<Id, Expr>>; narr: string; rule?: "orbit" | "dock";
}
export const STEPS: Step[] = [
  { t: "Agent proposes", s: "Pip · add tenacity", dot: "agent", actors: ["pip"], links: [["pip", "hub", "agent"]], bubbles: [["pip", "add tenacity"]], hub: "Proposal", narr: "Pip, a coding agent, proposes adding the tenacity package for backoff." },
  { t: "Developer overrules", s: "Priya Nair · Bengaluru", dot: "human", actors: ["priya", "pip"], links: [["priya", "pip", "human"]], bubbles: [["priya", "no new library"]], expr: { pip: "frustrated" }, hub: "Overruled", narr: "Priya, a developer, overrules it: no new library, use what the repo already has." },
  { t: "Recorded", s: "decision + quote + turn T18", dot: "ok", actors: ["priya"], links: [["priya", "hub", "human"]], docs: [["priya", "hub"]], hub: "T18 · redirect", narr: "The decision, her exact words and the turn are filed as one record." },
  { t: "Seen again", s: "Tomás Rivera, Sofia Lindqvist", dot: "human", actors: ["tomas", "sofia"], links: [["tomas", "hub", "human"], ["sofia", "hub", "human"]], bubbles: [["tomas", "seen it too"], ["sofia", "same here"]], hub: "+2 sessions", narr: "Other teams make the same correction. Nobody knew Priya had already said it." },
  { t: "Policy candidate", s: "11 sessions · 3 teams", dot: "human", actors: ["priya", "tomas", "sofia"], links: [["priya", "hub", "human"], ["tomas", "hub", "human"], ["sofia", "hub", "human"]], hub: "11 sessions · 3 teams", narr: "Eleven sessions across three teams: not a preference any more. It becomes a candidate." },
  { t: "Reviewed", s: "Amara + Kenji approve", dot: "ok", actors: ["amara", "kenji", "lena"], links: [["amara", "hub", "ok"], ["kenji", "hub", "ok"]], bubbles: [["amara", "approved"], ["kenji", "approved"]], expr: { amara: "pleased", kenji: "pleased" }, hub: "Approved", narr: "A tech lead and a security reviewer read the evidence and approve it. Lena files it." },
  { t: "Published", s: "AGENTS.md · PR check", dot: "ok", actors: ["lena", "marcus"], links: [["lena", "hub", "ok"]], docs: [["hub", "lena"]], expr: { marcus: "pleased", lena: "pleased" }, hub: "P-12 published", rule: "orbit", narr: "P-12 goes out as an AGENTS.md rule and a PR check, with an owner and an expiry." },
  { t: "Agents follow it", s: "Pip · Bolt · Nova learned P-12", dot: "ok", actors: ["pip", "bolt", "nova", "marcus"], links: [["hub", "pip", "ok"], ["hub", "bolt", "ok"], ["hub", "nova", "ok"]], expr: { pip: "pleased", bolt: "pleased", nova: "pleased", marcus: "pleased" }, hub: "P-12 · followed", rule: "dock", narr: "Every agent reads the rule before its first edit. Repeat corrections: 11 → 1." },
];

const person = (id: Id) => (id in CAST ? CAST[id as keyof typeof CAST] : BOTS[id as BotKind]);
const xy = (id: Id | "hub"): [number, number] => (id === "hub" ? HUB : [POS[id][0], POS[id][1]]);
const pc = (n: number) => `${(n / 6).toFixed(3)}%`; // 600-space coordinate -> percent
const reduceMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

function Pic({ id, step, on, ring }: { id: Id; step: number; on: boolean; ring?: string }) {
  const e = STEPS[step].expr?.[id] ?? "neutral";
  if (BOT_IDS.includes(id)) return <Bot kind={id as BotKind} expr={e} learned={step === 7} ring={on ? ring : undefined} size="100%" dim={!on} />;
  const p = CAST[id as keyof typeof CAST];
  return <Avatar look={p.look} expr={e} badge={p.badge} badgeBg={p.badgeBg} ring={on ? ring : undefined} size="100%" dim={!on} />;
}

function Card({ id, learned = false }: { id: Id; learned?: boolean }) {
  const p = person(id);
  const bot = BOT_IDS.includes(id);
  return (
    <div className="c1-card" data-bot={bot}>
      <b>{p.name}</b>
      <span className="mono"><i className="c1-dot" data-k={learned ? "ok" : bot ? "agent" : "human"} />{learned ? "LEARNED P-12" : bot ? "AGENT" : `${p.role} · ${p.city}`.toUpperCase()}</span>
    </div>
  );
}

function Journey({ step }: { step: number }) {
  return (
    <aside className="c1-journey" aria-label="Correction journey">
      <div className="c1-j-head"><span className="mono">CORRECTION P-12 · JOURNEY</span><span className="mono"><b>{step + 1}</b> / 8</span></div>
      <ol>
        {STEPS.map((s, i) => {
          const done = i < step, live = i === step;
          return (
            <li key={s.t} className="c1-row" data-live={live} data-done={done} data-near={Math.abs(i - step) <= 1}>
              <i className="c1-rdot" data-k={s.dot} />
              <div><b>{s.t}</b><span className="mono">{s.s}</span></div>
              <em className={`c1-pill ${live ? "live" : done ? "done" : ""}`}>{live ? "LIVE" : done ? "✓" : "–"}</em>
            </li>
          );
        })}
      </ol>
      <div className="c1-j-foot">
        <span className="mono c1-j-lbl">OUTPUTS</span>
        {["AGENTS.md", "PR check", "expires 2027-03", "owner @platform"].map((c) => <span key={c} className="c1-out mono" data-on={step >= 6}>{c}</span>)}
      </div>
    </aside>
  );
}

function Orbit({ step, picked, setPicked }: { step: number; picked: Id | null; setPicked: (i: Id | null) => void }) {
  const S = STEPS[step];
  const reduce = reduceMotion();
  const ringOf = (id: Id) => (BOT_IDS.includes(id) ? "var(--agent)" : "var(--human)");
  const lines = S.links.map(([a, b]) => [xy(a), xy(b)] as const);
  const q = picked ? person(picked).quote : S.narr;
  return (
    <div className="c1-orbit-wrap">
      <div className="c1-orbit" key="o">
        <svg viewBox="0 0 600 600" className="c1-svg" aria-hidden="true">
          {RINGS.map((r, i) => <circle key={r.r} cx="300" cy="300" r={r.r} className={`c1-ring r${i}`} />)}
          <circle cx="300" cy="300" r="294" className="c1-ticks" />
          {S.links.map(([, , k], i) => {
            const [[x1, y1], [x2, y2]] = lines[i];
            return <line key={`${step}-${i}`} x1={x1} y1={y1} x2={x2} y2={y2} className={`c1-link ${k}`} />;
          })}
          {!reduce && S.docs?.map(([a, b], i) => {
            const [x1, y1] = xy(a), [x2, y2] = xy(b);
            return (
              <g key={`${step}-d${i}`} className="c1-doc">
                <rect x="-6" y="-8" width="12" height="16" rx="2" />
                <path d="M-3 -3 H3 M-3 0 H3 M-3 3 H1" />
                <animateMotion dur="1.8s" repeatCount="indefinite" path={`M${x1} ${y1} L${x2} ${y2}`} />
              </g>
            );
          })}
          {S.rule === "orbit" && <g className="c1-spin"><rect x="262" y="12" width="76" height="24" rx="12" className="c1-rulechip" /><text x="300" y="28" textAnchor="middle">P-12</text></g>}
          <circle cx="300" cy="300" r="68" className="c1-arc-bg" />
          <circle cx="300" cy="300" r="68" className="c1-arc" pathLength="1" strokeDasharray={`${(step + 1) / 8} 1`} transform="rotate(-90 300 300)" />
          {RINGS.slice(1).map((r) => {
            const a = (55 * Math.PI) / 180;
            return <foreignObject key={r.l} x={300 + r.r * Math.cos(a) - 62} y={300 + r.r * Math.sin(a) - 11} width="124" height="22"><span className="c1-ringlbl mono">{r.l}</span></foreignObject>;
          })}
        </svg>

        <div className="c1-hub" style={{ left: pc(HUB[0]), top: pc(HUB[1]) }}>
          <span className="mono">DECISION RECORD</span><b key={step}>{S.hub}</b>
        </div>

        {(Object.keys(POS) as Id[]).map((id) => {
          const [x, y, cardSide, bubSide] = POS[id];
          const on = S.actors.includes(id) || reduce && step === 7;
          const bub = S.bubbles?.find(([w]) => w === id);
          return (
            <button key={id} type="button" className="c1-node" data-on={on} data-picked={picked === id} data-card={cardSide}
              style={{ left: `${(x / 6)}%`, top: `${(y / 6)}%` }} onClick={() => setPicked(picked === id ? null : id)} aria-label={person(id).name}>
              <span className="c1-av"><Pic id={id} step={step} on={on} ring={ringOf(id)} /></span>
              <Card id={id} learned={step === 7 && BOT_IDS.includes(id)} />
              {bub && <span key={`${step}-b`} className={`c1-bub ${bubSide}`}>{bub[1]}</span>}
            </button>
          );
        })}
      </div>
      <p className="c1-quote" key={`${step}-${picked}`}>{q}</p>
    </div>
  );
}

function Focus({ step, picked, setPicked }: { step: number; picked: Id | null; setPicked: (i: Id | null) => void }) {
  const S = STEPS[step];
  const q = picked ? person(picked).quote : S.narr;
  return (
    <div className="c1-focus">
      <div className="c1-hubm"><span className="mono">DECISION RECORD</span><b>{S.hub}</b>
        <i style={{ ["--p" as string]: (step + 1) / 8 }} /></div>
      <div className="c1-chips">
        {S.actors.map((id) => (
          <button key={`${step}-${id}`} type="button" className="c1-chip" data-picked={picked === id} onClick={() => setPicked(picked === id ? null : id)}>
            <span className="c1-av"><Pic id={id} step={step} on ring={BOT_IDS.includes(id) ? "var(--agent)" : "var(--human)"} /></span>
            <Card id={id} />
            {S.bubbles?.find(([w]) => w === id) && <span className="c1-bub t">{S.bubbles.find(([w]) => w === id)![1]}</span>}
          </button>
        ))}
      </div>
      <p className="c1-quote">{q}</p>
    </div>
  );
}

export default function OrbitSection() {
  const pin = useRef<HTMLElement>(null);
  const [step, setStep] = useState(0);
  const [pinned, setPinned] = useState(false);
  const [picked, setPicked] = useState<Id | null>(null);
  const reduce = reduceMotion();

  useEffect(() => {
    if (reduce) { setStep(7); return; }
    const on = () => {
      const el = pin.current; if (!el) return;
      const top = parseFloat(getComputedStyle(el).getPropertyValue("--c1-top")) || 56;
      const r = el.getBoundingClientRect();
      const range = r.height - (innerHeight - top);
      const isPinned = r.top <= top + 1 && r.bottom >= innerHeight - 1;
      setPinned(isPinned);
      if (isPinned) setStep(Math.min(7, Math.max(0, Math.floor(((top - r.top) / range) * 8))));
    };
    on();
    addEventListener("scroll", on, { passive: true }); addEventListener("resize", on);
    return () => { removeEventListener("scroll", on); removeEventListener("resize", on); };
  }, [reduce]);

  // not pinned: play the story by itself
  useEffect(() => {
    if (reduce || pinned) return;
    const t = setInterval(() => setStep((s) => (s + 1) % 8), 2800);
    return () => clearInterval(t);
  }, [pinned, reduce]);

  useEffect(() => { setPicked(null); }, [step]);

  return (
    <section className="c1-pin" ref={pin} data-reduce={reduce}>
      <div className="c1-sticky">
        <div className="wrap c1-grid">
          <Journey step={step} />
          <Orbit step={step} picked={picked} setPicked={setPicked} />
          <Focus step={step} picked={picked} setPicked={setPicked} />
        </div>
      </div>
    </section>
  );
}
