import type { ReactNode } from "react";

/* Parametric flat-illustration kit: people (feet at 0,0, about 100 units tall) and three agent characters.
   Illustration colours are fixed muted tones; role badges use tokens. All characters are fictional. */

export type Expr = "neutral" | "thinking" | "pleased" | "frustrated";
export type Pose = "down" | "stop" | "wave" | "point" | "stamp" | "hold";
type Hair = "short" | "long" | "bun" | "curly" | "bald";

export interface PersonSpec {
  id: string; name: string; role: string; city: string;
  skin: string; hair: string; hairStyle: Hair; top: string; pants: string; glasses?: boolean; pose: Pose;
}

export const CAST: Record<string, PersonSpec> = {
  priya: { id: "priya", name: "Priya Nair", role: "Developer", city: "Bengaluru", skin: "#c58a5b", hair: "#2b2320", hairStyle: "long", top: "#6b7a99", pants: "#3d4455", pose: "stop" },
  tomas: { id: "tomas", name: "Tomás Rivera", role: "Developer", city: "Mexico City", skin: "#d9a074", hair: "#5a3b2a", hairStyle: "short", top: "#7a8f6a", pants: "#4a4f45", glasses: true, pose: "stop" },
  amara: { id: "amara", name: "Amara Okafor", role: "Tech lead", city: "Lagos", skin: "#5e3b27", hair: "#1d1715", hairStyle: "curly", top: "#8c6a8f", pants: "#3f3a47", pose: "stamp" },
  kenji: { id: "kenji", name: "Kenji Mori", role: "Security reviewer", city: "Osaka", skin: "#f1c9a5", hair: "#1f1c1a", hairStyle: "short", top: "#4f6f73", pants: "#33424a", glasses: true, pose: "hold" },
  sofia: { id: "sofia", name: "Sofia Lindqvist", role: "Platform engineer", city: "Stockholm", skin: "#f3d3b5", hair: "#c9a35a", hairStyle: "bun", top: "#a5675b", pants: "#44393a", pose: "stop" },
  marcus: { id: "marcus", name: "Marcus Bell", role: "CTO", city: "Toronto", skin: "#8a5a3b", hair: "#9a9aa0", hairStyle: "short", top: "#44506b", pants: "#2f3445", pose: "point" },
  lena: { id: "lena", name: "Lena Fischer", role: "Policy librarian", city: "Berlin", skin: "#f1c9a5", hair: "#5a3b2a", hairStyle: "bun", top: "#b08a4a", pants: "#4a4136", glasses: true, pose: "hold" },
};

export const BOTS = {
  pip: { id: "pip", name: "Pip", note: "Agent · the hero" },
  bolt: { id: "bolt", name: "Bolt", note: "Agent · fellow traveller" },
  nova: { id: "nova", name: "Nova", note: "Agent · fellow traveller" },
} as const;
export type BotId = keyof typeof BOTS;

const INK = "#2a2f3a";

function Face({ e, y = -85 }: { e: Expr; y?: number }) {
  const mouth = { neutral: "M-3,0 L3,0", thinking: "M-3,1 Q0,-1 3,0", pleased: "M-4,-1 Q0,4 4,-1", frustrated: "M-3.5,1.5 Q0,-1.5 3.5,1.5" }[e];
  return (
    <g transform={`translate(0 ${y})`}>
      <g className="c3-blink"><circle cx="-5" cy="0" r="1.9" fill={INK} /><circle cx="5" cy="0" r="1.9" fill={INK} /></g>
      {e === "frustrated" && <path d="M-8,-5 L-2.5,-3 M8,-5 L2.5,-3" stroke={INK} strokeWidth="1.4" strokeLinecap="round" />}
      {e === "thinking" && <path d="M2.5,-5.5 L8,-6.5" stroke={INK} strokeWidth="1.4" strokeLinecap="round" />}
      <path d={mouth} transform="translate(0 8)" stroke={INK} strokeWidth="1.5" fill="none" strokeLinecap="round" />
    </g>
  );
}

function Arm({ d, top, skin, hand }: { d: string; top: string; skin: string; hand: [number, number] }) {
  return (<g><path d={d} stroke={top} strokeWidth="7" strokeLinecap="round" fill="none" /><circle cx={hand[0]} cy={hand[1]} r="3.6" fill={skin} /></g>);
}

function HairBack({ s }: { s: PersonSpec }) {
  return s.hairStyle === "long" ? <path d="M-15,-88 L-16,-60 Q0,-54 16,-60 L15,-88Z" fill={s.hair} /> : null;
}
function HairTop({ s }: { s: PersonSpec }) {
  const top = <path d="M-15,-84 C-16,-104 16,-104 15,-84 C9,-93 -9,-93 -15,-84Z" fill={s.hair} />;
  switch (s.hairStyle) {
    case "bun": return <>{top}<circle cx="0" cy="-102" r="6" fill={s.hair} /></>;
    case "curly": return <g fill={s.hair}>{[-12, -6, 0, 6, 12].map((x, i) => <circle key={x} cx={x} cy={-93 - (i % 2 ? 2 : 0)} r="6.5" />)}</g>;
    case "bald": return null;
    default: return top;
  }
}

/** A standing person. `x,y` is the feet position; `flip` mirrors; `walk` bobs. */
export function Person({ spec, x = 0, y = 0, scale = 1, expr = "neutral", pose, flip, walk, children }: {
  spec: PersonSpec; x?: number; y?: number; scale?: number; expr?: Expr; pose?: Pose; flip?: boolean; walk?: boolean; children?: ReactNode;
}) {
  const p = pose ?? spec.pose;
  const sk = spec.skin;
  const arms = {
    down: [["M-14,-64 L-17,-40", [-17, -37]], ["M14,-64 L17,-40", [17, -37]]],
    stop: [["M-14,-64 L-17,-40", [-17, -37]], ["M14,-64 L24,-84", [25, -87]]],
    wave: [["M-14,-64 L-17,-40", [-17, -37]], ["M14,-64 L26,-90", [27, -94]]],
    point: [["M-14,-64 L-17,-40", [-17, -37]], ["M14,-64 L32,-68", [35, -68]]],
    stamp: [["M-14,-64 L-17,-40", [-17, -37]], ["M14,-64 L26,-52", [28, -50]]],
    hold: [["M-14,-64 L-8,-46", [-6, -45]], ["M14,-64 L8,-46", [6, -45]]],
  }[p] as [string, [number, number]][];
  return (
    <g transform={`translate(${x} ${y}) scale(${flip ? -scale : scale} ${scale})`}>
      <g className={walk ? "c3-walk" : "c3-idle"}>
        <ellipse cx="0" cy="1" rx="18" ry="3.5" fill="#000" opacity="0.16" />
        <HairBack s={spec} />
        <rect x="-8" y="-36" width="7" height="34" rx="3" fill={spec.pants} /><rect x="1" y="-36" width="7" height="34" rx="3" fill={spec.pants} />
        <ellipse cx="-5" cy="-1.5" rx="6" ry="3" fill={INK} /><ellipse cx="5" cy="-1.5" rx="6" ry="3" fill={INK} />
        <rect x="-14" y="-72" width="28" height="42" rx="9" fill={spec.top} />
        <rect x="-3" y="-74" width="6" height="7" fill={sk} />
        <Arm d={arms[0][0]} top={spec.top} skin={sk} hand={arms[0][1]} />
        <g className={p === "wave" ? "c3-wave" : p === "stamp" ? "c3-stamp" : undefined}><Arm d={arms[1][0]} top={spec.top} skin={sk} hand={arms[1][1]} /></g>
        <circle cx="0" cy="-85" r="14" fill={sk} />
        <HairTop s={spec} />
        {spec.glasses && <g fill="none" stroke={INK} strokeWidth="1.2"><circle cx="-5" cy="-85" r="4.6" /><circle cx="5" cy="-85" r="4.6" /><path d="M-0.4,-85 L0.4,-85" /></g>}
        <Face e={expr} />
        {children}
      </g>
    </g>
  );
}

/** Head-and-shoulders crop for the cast strip. */
export function Bust({ spec, size = 64 }: { spec: PersonSpec; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="-24 -108 48 48" role="img" aria-label={spec.name} style={{ borderRadius: "50%", background: "var(--sunken)", boxShadow: "0 0 0 2px var(--human)" }}>
      <clipPath id={`c3-bust-${spec.id}`}><circle cx="0" cy="-84" r="24" /></clipPath>
      <g clipPath={`url(#c3-bust-${spec.id})`}><Person spec={spec} expr="pleased" pose="down" /></g>
    </svg>
  );
}

const BOT_COLOR: Record<BotId, string> = { pip: "#5f7089", bolt: "#6d7f8a", nova: "#56607a" };

function BotFace({ e, cy, wide = 5 }: { e: Expr; cy: number; wide?: number }) {
  return (
    <g transform={`translate(0 ${cy})`}>
      {e === "pleased" ? <path d={`M${-wide - 3},1 Q${-wide},-3 ${-wide + 3},1 M${wide - 3},1 Q${wide},-3 ${wide + 3},1`} stroke="#12141a" strokeWidth="1.8" fill="none" strokeLinecap="round" />
        : <g className="c3-blink"><circle cx={-wide} cy="0" r={e === "thinking" ? 2.2 : 2.6} fill="#12141a" /><circle cx={wide} cy="0" r={e === "thinking" ? 1.2 : 2.6} fill="#12141a" /></g>}
      {e === "frustrated" && <path d={`M${-wide - 3},-5 L${-wide + 2},-3 M${wide + 3},-5 L${wide - 2},-3`} stroke="#12141a" strokeWidth="1.6" strokeLinecap="round" />}
      <path d={{ neutral: "M-3,8 L3,8", thinking: "M-3,8.5 Q0,6.5 3,8", pleased: "M-4,7 Q0,11 4,7", frustrated: "M-3.5,9.5 Q0,6 3.5,9.5" }[e]} stroke="#12141a" strokeWidth="1.5" fill="none" strokeLinecap="round" />
    </g>
  );
}

/** Agent characters. Feet at 0,0. */
export function Bot({ id, x = 0, y = 0, scale = 1, expr = "neutral", flip, walk, leaf }: {
  id: BotId; x?: number; y?: number; scale?: number; expr?: Expr; flip?: boolean; walk?: boolean; leaf?: boolean;
}) {
  const c = BOT_COLOR[id];
  return (
    <g transform={`translate(${x} ${y}) scale(${flip ? -scale : scale} ${scale})`}>
      <g className={walk ? "c3-walk" : "c3-idle"}>
        <ellipse cx="0" cy="1" rx="22" ry="4" fill="#000" opacity="0.16" />
        {id === "pip" && <>
          <rect x="-12" y="-14" width="8" height="13" rx="4" fill="#3f4a5e" /><rect x="4" y="-14" width="8" height="13" rx="4" fill="#3f4a5e" />
          <circle cx="0" cy="-34" r="24" fill={c} /><circle cx="0" cy="-36" r="16" fill="#e8ecf2" />
          <path d="M0,-58 L0,-66" stroke="#3f4a5e" strokeWidth="2" /><circle cx="0" cy="-68" r="3.5" fill="var(--human)" />
          <BotFace e={expr} cy={-38} />
        </>}
        {id === "bolt" && <>
          <rect x="-13" y="-16" width="9" height="15" rx="2" fill="#3f4a5e" /><rect x="4" y="-16" width="9" height="15" rx="2" fill="#3f4a5e" />
          <rect x="-22" y="-60" width="44" height="46" rx="8" fill={c} /><rect x="-15" y="-52" width="30" height="24" rx="5" fill="#e8ecf2" />
          <path d="M0,-60 L0,-72" stroke="#3f4a5e" strokeWidth="2" /><circle cx="0" cy="-74" r="3" fill="#9fb4c8" />
          <rect x="-26" y="-46" width="5" height="16" rx="2.5" fill="#3f4a5e" /><rect x="21" y="-46" width="5" height="16" rx="2.5" fill="#3f4a5e" />
          <BotFace e={expr} cy={-42} />
        </>}
        {id === "nova" && <>
          <rect x="-10" y="-20" width="7" height="19" rx="3" fill="#3f4a5e" /><rect x="3" y="-20" width="7" height="19" rx="3" fill="#3f4a5e" />
          <rect x="-16" y="-84" width="32" height="68" rx="16" fill={c} />
          <rect x="-13" y="-76" width="26" height="14" rx="7" fill="#12141a" /><rect x="-11" y="-74" width="22" height="10" rx="5" fill="#9fc3d8" opacity="0.85" />
          <BotFace e={expr} cy={-69} wide={4} />
          <rect x="-8" y="-52" width="16" height="10" rx="3" fill="#e8ecf2" opacity="0.9" />
        </>}
        {leaf && <path d="M18,-70 C34,-86 52,-76 48,-58 C34,-52 22,-58 18,-70Z" fill="#6aa377" />}
      </g>
    </g>
  );
}
