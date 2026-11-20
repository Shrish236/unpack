import { useEffect, useState } from "react";
import { Bot, Bubble, CAST, Person, type Mood } from "./Kit";

/* The Studio: a four-floor cutaway. The camera pans floor to floor with the scroll step.
   Floors are drawn in a 480-unit-wide space, 300 units tall each; the viewport shows 336 units.
   Phases (p) play the story of the active floor; floors that are not active show their finished state. */

const H = 300;
const reduced = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const DELAYS: number[][] = [[900, 2300, 3700], [800, 1800, 2800, 3800], [900, 2200, 3500], [900, 2000, 3200], [600, 1800, 3000]];

function usePhase(step: number) {
  const [p, setP] = useState(reduced() ? 99 : 0);
  useEffect(() => {
    if (reduced()) { setP(99); return; }
    setP(0);
    const t = DELAYS[step].map((d, i) => setTimeout(() => setP(i + 1), d));
    return () => t.forEach(clearTimeout);
  }, [step]);
  return p;
}

const Room = ({ f, children, sign }: { f: number; children: React.ReactNode; sign: string }) => (
  <g transform={`translate(0 ${f * H})`}>
    <rect x="0" y="0" width="480" height="272" className="c2-wall" />
    <rect x="0" y="270" width="480" height="30" className="c2-slab" />
    <rect x="0" y="0" width="480" height="3" className="c2-slab" />
    {/* stair shaft */}
    <g className="c2-stair"><rect x="0" y="0" width="38" height="270" />
      {Array.from({ length: 9 }, (_, i) => <path key={i} d={`M0 ${262 - i * 28} h${12 + i * 3} v10 h-${12 + i * 3}z`} />)}</g>
    <text x="48" y="19" className="c2-sign">{sign}</text>
    {children}
  </g>
);

const Desk = ({ x, w = 104 }: { x: number; w?: number }) => (
  <g>
    <rect x={x} y="236" width={w} height="6" rx="2" className="c2-desk" />
    <rect x={x + 6} y="242" width="5" height="28" className="c2-desk" /><rect x={x + w - 11} y="242" width="5" height="28" className="c2-desk" />
  </g>
);
const Monitor = ({ x, y = 200, lines = true }: { x: number; y?: number; lines?: boolean }) => (
  <g><rect x={x} y={y} width="34" height="24" rx="3" className="c2-mon" /><rect x={x + 15} y={y + 24} width="4" height="12" className="c2-desk" />
    {lines && <path d={`M${x + 5} ${y + 7} h18 M${x + 5} ${y + 12} h24 M${x + 5} ${y + 17} h12`} className="c2-code" />}</g>
);

export default function Studio({ step, k = 1 }: { step: number; k?: number }) {
  const phase = usePhase(step);
  const floor = [0, 1, 2, 3, 3][step];
  const pOf = (f: number) => (step === f ? phase : 99); // active floor plays, others show their end state
  const p0 = pOf(0), p1 = pOf(1), p2 = pOf(2), p3 = step === 3 ? phase : 99, epi = step === 4 ? phase : 0;

  const pipMood0: Mood = p0 >= 3 ? "thinking" : p0 >= 2 ? "frustrated" : "pleased";
  const cards = p1 >= 4 ? 11 : p1 >= 3 ? 8 : p1 >= 2 ? 5 : p1 >= 1 ? 1 : 0;
  const learned = step === 4 && epi >= 3;
  const pip3: Mood = step === 4 ? (epi >= 3 ? "pleased" : epi >= 2 ? "thinking" : "neutral") : p3 >= 3 ? "pleased" : "thinking";
  const overrides = step === 4 && epi >= 3 ? 3 : 11;
  const walking = step === 4;
  const pipX = !walking ? 92 : epi >= 1 ? 150 : 30;

  return (
    <svg className="c2-svg" viewBox="0 0 480 336" role="img" aria-label="Cutaway of a four-floor studio where agents learn from human corrections">
      <g className="c2-cam" style={{ transform: `translateY(${-(floor * H - 12)}px)` }}>
        {/* ---------- floor 1: dev floor ---------- */}
        <Room f={0} sign="1 · DEV FLOOR">
          <rect x="150" y="34" width="64" height="44" rx="3" className="c2-window" /><path d="M182 34 v44 M150 56 h64" className="c2-mullion" />
          <Desk x={76} /><Monitor x={84} />
          <Person s={1.45} look={CAST.priya.look} x={132} y={270} sitting typing mood={p0 >= 2 ? "frustrated" : "neutral"} speaking={p0 >= 2} />
          <Desk x={296} /><Monitor x={304} />
          <Person s={1.45} look={CAST.tomas.look} x={352} y={270} sitting typing />
          <Bot s={1.35} kind="pip" x={216} y={270} mood={pipMood0} />
          <Bot s={1.35} kind="bolt" x={430} y={270} mood="neutral" />
          <Bubble x={216} y={216} text="Added tenacity!" k={k} show={p0 >= 1 && p0 < 2} />
          <Bubble x={138} y={186} text={["Not here.", "Use what we have."]} k={k} human show={p0 >= 2} />
          <text x="76" y="288" className="c2-tag">{CAST.priya.name} · {CAST.priya.role.toUpperCase()}</text>
          <text x="296" y="288" className="c2-tag">{CAST.tomas.name} · {CAST.tomas.role.toUpperCase()}</text>
        </Room>

        {/* ---------- floor 2: the library ---------- */}
        <Room f={1} sign="2 · THE LIBRARY">
          <rect x="52" y="22" width="122" height="40" rx="6" className="c2-board" />
          <text x="113" y="38" textAnchor="middle" className="c2-bt" style={{ fontSize: 9 * k }}>same correction</text>
          <text x="113" y="54" textAnchor="middle" className="c2-big" style={{ fontSize: 15 * k }}>{cards} · {cards >= 8 ? 3 : cards >= 4 ? 2 : 1} {cards >= 8 ? "teams" : "team"}</text>
          {[0, 1, 2, 3].map((r) => <rect key={r} x="226" y={86 + r * 44} width="208" height="4" className="c2-slab" />)}
          {Array.from({ length: 16 }, (_, i) => {
            const on = i < cards;
            return <rect key={i} x={230 + (i % 4) * 51} y={60 + Math.floor(i / 4) * 44} width="40" height="26" rx="3" className={`c2-card ${on ? "on" : ""}`} style={{ transitionDelay: `${(i % 4) * 90}ms` }} />;
          })}
          <rect x="52" y="116" width="122" height="4" className="c2-slab" />
          <Person look={CAST.tomas.look} x={80} y={116} s={0.8} nod={false} />
          <Person look={CAST.sofia.look} x={140} y={116} s={0.8} nod={false} />
          <text x="52" y="132" className="c2-tag">TOMÁS · PAYMENTS</text><text x="126" y="132" className="c2-tag">SOFIA · PLATFORM</text>
          {p1 >= 2 && <g className="c2-drop"><rect x="70" y="124" width="12" height="9" rx="2" className="c2-card on" /><rect x="130" y="124" width="12" height="9" rx="2" className="c2-card on" style={{ animationDelay: ".5s" }} /></g>}
          <Desk x={70} w={120} /><Monitor x={76} y={202} lines={false} />
          <Person s={1.45} look={CAST.lena.look} x={150} y={270} sitting typing mood={p1 >= 4 ? "pleased" : "neutral"} />
          <text x="70" y="288" className="c2-tag">{CAST.lena.name} · {CAST.lena.role.toUpperCase()}</text>
        </Room>

        {/* ---------- floor 3: council room ---------- */}
        <Room f={2} sign="3 · COUNCIL ROOM">
          <g className="c2-boardwrap">
            <rect x="56" y="34" width="136" height="104" rx="6" className="c2-paper" />
            <text x="66" y="52" className="c2-bt" style={{ fontSize: 9 * k, fontWeight: 600 }}>POLICY P-12</text>
            <text x="66" y="70" className="c2-bt" style={{ fontSize: 8.5 * k }}>No new runtime dependency</text>
            <text x="66" y="88" className="c2-mono" style={{ fontSize: 8 * k }}>scope · org</text>
            <text x="66" y="100" className="c2-mono" style={{ fontSize: 8 * k }}>enforce · PR check</text>
            <text x="66" y="112" className="c2-mono" style={{ fontSize: 8 * k }}>expires · 2027-03</text>
            <g className="c2-stamp" data-show={p2 >= 2}><rect x="142" y="114" width="56" height="22" rx="4" /><text x="170" y="128" textAnchor="middle" style={{ fontSize: 8.5 * k }}>APPROVED</text></g>
          </g>
          <rect x="230" y="34" width="150" height="92" rx="6" className="c2-mon" />
          <text x="240" y="50" className="c2-screen" style={{ fontSize: 8 * k }}>overrides / 100 sessions</text>
          <path d="M240 112 L262 66 L290 72 L316 84 L342 100 L366 108" className={`c2-line ${p2 >= 3 ? "draw" : ""}`} pathLength="1" />
          <Person s={1.45} look={CAST.marcus.look} x={420} y={270} nod={false} mood={p2 >= 3 ? "pleased" : "thinking"} />
          <Person s={1.45} look={CAST.amara.look} x={104} y={262} sitting mood={p2 >= 2 ? "pleased" : "thinking"} speaking={p2 >= 1 && p2 < 3} />
          <Person s={1.45} look={CAST.kenji.look} x={196} y={262} sitting flip mood={p2 >= 2 ? "pleased" : "neutral"} />
          <ellipse cx="150" cy="238" rx="74" ry="12" className="c2-desk" /><rect x="146" y="238" width="8" height="32" className="c2-desk" />
          <path d="M122 236 h16 M162 236 h22" className="c2-code" />
          <text x="60" y="288" className="c2-tag">AMARA · TECH LEAD · KENJI · SECURITY</text><text x="360" y="288" className="c2-tag">MARCUS · CTO</text>
        </Room>

        {/* ---------- floor 4: training room ---------- */}
        <Room f={3} sign={step === 4 ? "4 · TRAINING ROOM · NEXT MORNING" : "4 · TRAINING ROOM"}>
          <rect x="150" y="30" width="170" height="86" rx="4" className="c2-paper" />
          <rect x="150" y="30" width="170" height="14" rx="4" className="c2-pinhead" />
          <text x="160" y="41" className="c2-bt" style={{ fontSize: 8.5 * k, fontWeight: 600 }}>P-12 · THE RULE</text>
          <text x="160" y="66" className="c2-bt" style={{ fontSize: 10.5 * k, fontWeight: 600 }}>No new runtime dependency</text>
          <text x="160" y="82" className="c2-bt" style={{ fontSize: 10.5 * k, fontWeight: 600 }}>without approval.</text>
          <text x="160" y="104" className="c2-mono" style={{ fontSize: 8 * k }}>org · PR check · owner @platform</text>
          <circle cx="156" cy="34" r="3" className="c2-pin" /><circle cx="314" cy="34" r="3" className="c2-pin" />
          {/* picture-in-picture of the dev floor */}
          <rect x="344" y="30" width="112" height="86" rx="6" className="c2-window" />
          <Person look={CAST.priya.look} x={400} y={112} s={0.95} sitting mood={epi >= 3 ? "pleased" : "neutral"} nod={false} />
          <text x="350" y="44" className="c2-tag">DEV FLOOR</text>
          <rect x="52" y="30" width="80" height="50" rx="5" className="c2-mon" />
          <text x="60" y="43" className="c2-screen" style={{ fontSize: 7.5 * k }}>overrides</text>
          <text x="60" y="68" className="c2-big on" style={{ fontSize: 17 * k }}>{overrides === 3 ? "11 → 3" : "11"}</text>
          {[100, 210, 320].map((x, i) => <g key={x}><rect x={x - 38} y="240" width="76" height="6" rx="2" className="c2-desk" /><rect x={x - 32} y="246" width="5" height="24" className="c2-desk" /><rect x={x + 27} y="246" width="5" height="24" className="c2-desk" /><rect x={x - 12} y="222" width="26" height="18" rx="2" className="c2-paper" /><path d={`M${x - 7} 229 h16 M${x - 7} 234 h10`} className="c2-code" /> {i === 0 && walking ? null : null}</g>)}
          {!walking && <Bot s={1.35} kind="pip" x={100} y={270} mood={pip3} />}
          <Bot s={1.35} kind="bolt" x={210} y={270} mood={step === 4 || p3 >= 3 ? "pleased" : "thinking"} />
          <Bot s={1.35} kind="nova" x={320} y={270} mood={step === 4 || p3 >= 3 ? "pleased" : "thinking"} />
          {p3 >= 1 && step !== 4 && <path d="M110 244 Q150 160 170 100 M210 244 Q215 170 232 100 M320 244 Q300 170 262 100" className="c2-gaze" />}
          {walking && (
            <g className="c2-walk" style={{ transform: `translateX(${pipX}px)` }}>
              <Bot s={1.35} kind="pip" x={0} y={270} mood={pip3} badge={learned ? <g className="c2-promo"><circle cx="0" cy="-34" r="7" fill="#f5b301" /><path d="M-3 -34 l2.2 2.4 l4 -4.6" stroke="#1e293b" strokeWidth="1.6" fill="none" strokeLinecap="round" /></g> : undefined} />
              <Bubble x={0} y={210} text={["Reuse the", "retry helper."]} k={k} show={epi >= 2 && epi < 3} />
              {learned && <g><rect x="-52" y="188" width="104" height="22" rx="11" className="c2-chip" /><text x="0" y="203" textAnchor="middle" className="c2-chiptext" style={{ fontSize: 8.5 * k }}>trusted with PR checks</text></g>}
            </g>
          )}
          <text x="52" y="288" className="c2-tag">PIP · BOLT · NOVA · AGENTS READING THE SAME WALL</text>
        </Room>

        {/* pneumatic tube from the dev floor to the library */}
        <g className="c2-tube"><rect x="462" y="36" width="8" height="300" rx="4" /><rect x="446" y="332" width="24" height="30" rx="4" className="c2-recv" />
          <rect x="460" y="46" width="12" height="18" rx="3" className="c2-capsule" style={{ transform: `translateY(${step > 0 || p0 >= 3 ? 282 : 0}px)` }} />
        </g>
      </g>
    </svg>
  );
}
