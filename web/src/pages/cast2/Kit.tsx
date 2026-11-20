import type { ReactNode } from "react";

/* A small parametric SVG avatar kit: people and agents in one flat style.
   Everything is drawn around the feet (0,0), y up is negative. Fixed illustration colours here;
   the page chrome uses tokens only. */

export type Mood = "neutral" | "thinking" | "pleased" | "frustrated";
export type HairStyle = "short" | "long" | "bun" | "curly" | "cap" | "hijab" | "bald";

export interface Look { skin: string; hair: string; style: HairStyle; shirt: string; glasses?: boolean; badge: string; badgeColor: string }

const SKIN = ["#f1c9a5", "#d9a074", "#b9774c", "#8a5434", "#5e3a24"];
// The cast. Fictional personas; roles and cities are shown on the page as "Illustrative cast".
export const CAST = {
  priya: { name: "Priya Nair", role: "Developer", city: "Bengaluru", look: { skin: SKIN[2], hair: "#1f1a17", style: "long", shirt: "#5b7c99", badge: "D", badgeColor: "#5b7c99" } as Look },
  tomas: { name: "Tomás Rivera", role: "Developer", city: "Mexico City", look: { skin: SKIN[1], hair: "#2b2018", style: "short", shirt: "#7a8f6a", glasses: true, badge: "D", badgeColor: "#5b7c99" } as Look },
  amara: { name: "Amara Okafor", role: "Tech lead", city: "Lagos", look: { skin: SKIN[4], hair: "#15110e", style: "curly", shirt: "#c9962b", badge: "L", badgeColor: "#c9962b" } as Look },
  kenji: { name: "Kenji Mori", role: "Security reviewer", city: "Osaka", look: { skin: SKIN[0], hair: "#1c1c1f", style: "short", shirt: "#8a5a6b", glasses: true, badge: "S", badgeColor: "#8a5a6b" } as Look },
  sofia: { name: "Sofia Lindqvist", role: "Platform engineer", city: "Stockholm", look: { skin: SKIN[0], hair: "#d2a35a", style: "bun", shirt: "#4f8a8b", badge: "P", badgeColor: "#4f8a8b" } as Look },
  marcus: { name: "Marcus Bell", role: "CTO", city: "Toronto", look: { skin: SKIN[3], hair: "#241a14", style: "bald", shirt: "#3f4a5c", glasses: true, badge: "C", badgeColor: "#3f4a5c" } as Look },
  lena: { name: "Lena Fischer", role: "Policy librarian", city: "Berlin", look: { skin: SKIN[1], hair: "#6a4a3a", style: "hijab", shirt: "#7d6aa0", badge: "L", badgeColor: "#7d6aa0" } as Look },
};
export type Who = keyof typeof CAST;

function Face({ mood, y = -44, dark = "#2a2320" }: { mood: Mood; y?: number; dark?: string }) {
  const e = { stroke: dark, strokeWidth: 1.3, fill: "none", strokeLinecap: "round" as const };
  return (
    <g transform={`translate(0 ${y})`}>
      {mood === "pleased" ? (
        <>
          <path d="M-5.2 0 q1.7 -2 3.4 0 M1.8 0 q1.7 -2 3.4 0" {...e} />
          <path d="M-3 3.6 q3 3 6 0" {...e} />
        </>
      ) : mood === "frustrated" ? (
        <>
          <path d="M-6 -3 l4 1.6 M6 -3 l-4 1.6" {...e} />
          <circle className="c2-blink" cx="-3.5" cy="0.4" r="1.2" fill={dark} />
          <circle className="c2-blink" cx="3.5" cy="0.4" r="1.2" fill={dark} />
          <path d="M-3 5 q1.5 -1.6 3 0 t3 0" {...e} />
        </>
      ) : mood === "thinking" ? (
        <>
          <path d="M-6 -3.6 l4 -.8" {...e} />
          <circle className="c2-blink" cx="-2.8" cy="-0.6" r="1.2" fill={dark} />
          <circle className="c2-blink" cx="4.2" cy="-0.6" r="1.2" fill={dark} />
          <circle cx="1.6" cy="4.6" r="1.2" {...e} />
        </>
      ) : (
        <>
          <circle className="c2-blink" cx="-3.5" cy="0" r="1.2" fill={dark} />
          <circle className="c2-blink" cx="3.5" cy="0" r="1.2" fill={dark} />
          <path d="M-2 4.4 h4" {...e} />
        </>
      )}
    </g>
  );
}

function Hair({ style, color, skin }: { style: HairStyle; color: string; skin: string }) {
  switch (style) {
    case "long": return <g fill={color}><path d="M-10 -44 a10 10 0 0 1 20 0 v14 q-3 2 -4 -1 v-12 h-12 v12 q-1 3 -4 1z" /></g>;
    case "bun": return <g fill={color}><circle cx="0" cy="-58" r="4.4" /><path d="M-9.6 -45 a9.6 9.6 0 0 1 19.2 0 q-9.6 -5 -19.2 0z" /></g>;
    case "curly": return <g fill={color}>{[-8, -4, 0, 4, 8].map((x, i) => <circle key={i} cx={x} cy={-52 + Math.abs(x) * 0.3} r="4.6" />)}<circle cx="-9.5" cy="-45" r="3.4" /><circle cx="9.5" cy="-45" r="3.4" /></g>;
    case "cap": return <g fill={color}><path d="M-10 -47 a10 9 0 0 1 20 0z" /><rect x="0" y="-48" width="13" height="3" rx="1.5" /></g>;
    case "hijab": return <g fill={color}><path d="M-11 -42 a11 12 0 0 1 22 0 q1 12 5 14 h-32 q4 -2 5 -14z" /><ellipse cx="0" cy="-43.4" rx="7.8" ry="8.4" fill={skin} /></g>;
    case "bald": return <path d="M-9.4 -46 a9.4 4 0 0 1 18.8 0" fill={color} opacity=".35" />;
    default: return <path d="M-10 -44 a10 10 0 0 1 20 0 q-10 -5.6 -20 0z" fill={color} />;
  }
}

export function Person({ look, mood = "neutral", x, y, s = 1, sitting, flip, typing, nod = true, speaking }: { look: Look; mood?: Mood; x: number; y: number; s?: number; sitting?: boolean; flip?: boolean; typing?: boolean; nod?: boolean; speaking?: boolean }) {
  const hairBehind = look.style === "long" || look.style === "hijab";
  return (
    <g className="c2-person" transform={`translate(${x} ${y}) scale(${flip ? -s : s} ${s})`}>
      {sitting && <rect x="-12" y="-34" width="24" height="30" rx="5" fill="#8b97a8" />}
      {/* legs */}
      {sitting ? (
        <g fill="#33404f"><rect x="-8" y="-13" width="18" height="6" rx="3" /><rect x="6" y="-13" width="6" height="14" rx="3" /></g>
      ) : (
        <g fill="#33404f"><rect x="-7" y="-14" width="6" height="14" rx="2.5" /><rect x="1" y="-14" width="6" height="14" rx="2.5" /></g>
      )}
      {/* body */}
      <path d="M-10 -14 v-14 a6 6 0 0 1 6 -6 h8 a6 6 0 0 1 6 6 v14z" fill={look.shirt} />
      <g className={typing ? "c2-type" : undefined}>
        <rect x="-12" y="-32" width="5" height="15" rx="2.5" fill={look.shirt} />
        <rect x="7" y="-32" width="5" height="15" rx="2.5" fill={look.shirt} />
        <circle cx="-9.5" cy="-16" r="2.4" fill={look.skin} /><circle cx="9.5" cy="-16" r="2.4" fill={look.skin} />
      </g>
      {/* head */}
      <g className={nod ? "c2-nod" : undefined} style={speaking ? { animationDuration: "1.1s" } : undefined}>
        {hairBehind && look.style === "long" && <Hair style={look.style} color={look.hair} skin={look.skin} />}
        <rect x="-2.4" y="-36" width="4.8" height="5" fill={look.skin} />
        {look.style === "hijab" ? <Hair style="hijab" color={look.hair} skin={look.skin} /> : <circle cx="0" cy="-44" r="9" fill={look.skin} />}
        {look.style !== "long" && look.style !== "hijab" && <Hair style={look.style} color={look.hair} skin={look.skin} />}
        {look.style === "long" && <path d="M-9.4 -44 a9.4 9.4 0 0 1 18.8 0 q-9.4 -5 -18.8 0z" fill={look.hair} />}
        {look.glasses && <g fill="none" stroke="#2a2320" strokeWidth="1"><circle cx="-3.6" cy="-44" r="3.2" /><circle cx="3.6" cy="-44" r="3.2" /><path d="M-0.4 -44 h0.8" /></g>}
        <Face mood={mood} />
      </g>
      {/* role badge */}
      <g transform="translate(8 -33)"><circle r="4.4" fill={look.badgeColor} stroke="#fff" strokeWidth="1" /><text y="1.9" textAnchor="middle" fontSize="5.2" fill="#fff" style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{look.badge}</text></g>
    </g>
  );
}

/* Agents: three silhouettes, so a viewer can tell them apart at a glance. */
function Screen({ mood, w, h, x = 0, y = 0 }: { mood: Mood; w: number; h: number; x?: number; y?: number }) {
  const c = "#dbeafe";
  const e = { stroke: c, strokeWidth: 1.5, fill: "none", strokeLinecap: "round" as const };
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={h / 3} fill="#1e293b" />
      {mood === "pleased" ? <><path d="M-6 -1.5 q2 -2.6 4 0 M2 -1.5 q2 -2.6 4 0" {...e} /><path d="M-3 3 q3 3 6 0" {...e} /></> :
        mood === "frustrated" ? <><path d="M-7 -4.4 l5 2 M7 -4.4 l-5 2" {...e} /><circle className="c2-blink" cx="-4" cy="-0.4" r="1.4" fill={c} /><circle className="c2-blink" cx="4" cy="-0.4" r="1.4" fill={c} /><path d="M-3.5 4.4 q1.7 -1.8 3.5 0 t3.5 0" {...e} /></> :
          mood === "thinking" ? <><circle className="c2-blink" cx="-3.4" cy="-1.4" r="1.5" fill={c} /><circle className="c2-blink" cx="4.6" cy="-1.4" r="1.5" fill={c} /><path d="M-3 4 h.1 M0 4 h.1 M3 4 h.1" {...e} /></> :
            <><circle className="c2-blink" cx="-4" cy="-1" r="1.5" fill={c} /><circle className="c2-blink" cx="4" cy="-1" r="1.5" fill={c} /><path d="M-2.4 4 h4.8" {...e} /></>}
    </g>
  );
}

export function Bot({ kind, mood = "neutral", x, y, s = 1, flip, badge }: { kind: "pip" | "bolt" | "nova"; mood?: Mood; x: number; y: number; s?: number; flip?: boolean; badge?: ReactNode }) {
  return (
    <g className="c2-bot" transform={`translate(${x} ${y}) scale(${flip ? -s : s} ${s})`}>
      <g className="c2-bob">
        {kind === "pip" && (
          <>
            <ellipse cx="0" cy="-1" rx="12" ry="2.6" fill="#000" opacity=".12" />
            <circle cx="0" cy="-15" r="14" fill="#7b8da6" />
            <circle cx="0" cy="-15" r="14" fill="none" stroke="#fff" strokeOpacity=".35" />
            <Screen mood={mood} w={20} h={13} y={-16} />
            <rect x="-3" y="-34" width="6" height="4" rx="2" fill="#5d6e86" />
          </>
        )}
        {kind === "bolt" && (
          <>
            <ellipse cx="0" cy="-1" rx="13" ry="2.6" fill="#000" opacity=".12" />
            <rect x="-13" y="-34" width="26" height="32" rx="6" fill="#98a6b8" />
            <rect x="-13" y="-6" width="26" height="4" rx="2" fill="#7b8a9f" />
            <path d="M0 -34 v-8" stroke="#5d6e86" strokeWidth="2" strokeLinecap="round" /><circle className="c2-blink" cx="0" cy="-44" r="2.6" fill="#94a3b8" />
            <Screen mood={mood} w={20} h={14} y={-22} />
          </>
        )}
        {kind === "nova" && (
          <>
            <ellipse cx="0" cy="-1" rx="11" ry="2.4" fill="#000" opacity=".12" />
            <rect x="-9" y="-48" width="18" height="46" rx="8" fill="#56667d" />
            <rect x="-10.5" y="-46" width="21" height="11" rx="5.5" fill="#1e293b" />
            <Screen mood={mood} w={17} h={8} y={-40.5} />
            <rect x="-5" y="-28" width="10" height="10" rx="2" fill="#6b7d96" />
          </>
        )}
        {badge}
      </g>
    </g>
  );
}

/* A small speech bubble. Width follows the text so it works at any text scale k. */
export function Bubble({ x, y, text, k = 1, human, show = true, up }: { x: number; y: number; text: string | string[]; k?: number; human?: boolean; show?: boolean; up?: boolean }) {
  const lines = Array.isArray(text) ? text : [text];
  const fs = 9 * k;
  const w = Math.max(...lines.map((l) => l.length)) * fs * 0.56 + 14;
  const h = lines.length * fs * 1.25 + 9;
  const top = up ? y : y - h - 7;
  return (
    <g className="c2-bubble" data-show={show} style={{ transformOrigin: `${x}px ${y}px` }}>
      <rect x={x - w / 2} y={top} width={w} height={h} rx="6" className={human ? "c2-bub human" : "c2-bub"} />
      <path d={`M${x - 4} ${top + h - .5} l4 6 l4 -6z`} className={human ? "c2-bub human" : "c2-bub"} style={{ strokeWidth: 0 }} />
      {lines.map((l, i) => <text key={i} x={x} y={top + 6 + fs * (0.9 + i * 1.25)} textAnchor="middle" className="c2-bt" style={{ fontSize: fs }}>{l}</text>)}
    </g>
  );
}
