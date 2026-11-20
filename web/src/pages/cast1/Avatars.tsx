import { useId } from "react";

/* A tiny parametric avatar kit. Flat shapes on a 64x64 canvas, clipped to a circle.
   Skin, hair and clothing are fixed illustration colours (they read on both themes against --sunken);
   frames, bots and chrome use theme tokens. All personas are fictional. */

export type Expr = "neutral" | "thinking" | "pleased" | "frustrated";
type Hair = "short" | "long" | "bob" | "curly" | "bun" | "wrap" | "bald";
export interface Look { skin: string; hair: string; style: Hair; top: string; glasses?: boolean; beard?: boolean; wrap?: string }

const INK = "#2a2430";

function Face({ e, glasses }: { e: Expr; glasses?: boolean }) {
  const eye = (x: number) =>
    e === "pleased" ? <path d={`M${x - 2} 31 Q${x} 28.4 ${x + 2} 31`} fill="none" stroke={INK} strokeWidth="1.4" strokeLinecap="round" />
      : <circle cx={x} cy={31} r={1.5} fill={INK} />;
  return (
    <g>
      {eye(27.5)}{eye(36.5)}
      {e === "frustrated" && <path d="M24.5 27 L29.5 28.6 M39.5 27 L34.5 28.6" stroke={INK} strokeWidth="1.3" strokeLinecap="round" />}
      {e === "thinking" && <path d="M34.5 27.4 L39 25.8" stroke={INK} strokeWidth="1.3" strokeLinecap="round" />}
      {e === "neutral" && <path d="M28.5 39 H35.5" stroke={INK} strokeWidth="1.3" strokeLinecap="round" />}
      {e === "pleased" && <path d="M27.5 37.6 Q32 43 36.5 37.6" fill="none" stroke={INK} strokeWidth="1.4" strokeLinecap="round" />}
      {e === "thinking" && <path d="M29 40.2 Q32 38.6 36 40.2" fill="none" stroke={INK} strokeWidth="1.3" strokeLinecap="round" />}
      {e === "frustrated" && <path d="M28 41.4 Q32 37.6 36 41.4" fill="none" stroke={INK} strokeWidth="1.4" strokeLinecap="round" />}
      {glasses && (
        <g fill="none" stroke={INK} strokeWidth="1">
          <circle cx="27.5" cy="31" r="4.2" /><circle cx="36.5" cy="31" r="4.2" /><path d="M31.7 31 H32.3" />
        </g>
      )}
    </g>
  );
}

function HairBack({ look }: { look: Look }) {
  const h = look.hair;
  switch (look.style) {
    case "long": return <path d="M18 31 Q17 14 32 14 Q47 14 46 31 L48 53 Q32 57 16 53 Z" fill={h} />;
    case "bob": return <path d="M18.5 31 Q18 14 32 14 Q46 14 45.5 31 L46 41 Q32 45 18 41 Z" fill={h} />;
    case "curly": return <g fill={h}>{[[19, 26], [25, 17.5], [33, 15.5], [41, 18], [45, 26], [19.5, 34], [45, 34]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r={6.2} />)}</g>;
    case "bun": return <circle cx="32" cy="13.5" r="5.6" fill={h} />;
    default: return null;
  }
}

function HairFront({ look }: { look: Look }) {
  const h = look.hair;
  switch (look.style) {
    case "short": case "bun": return <path d="M20 29 Q19.5 15.5 32 15.5 Q44.5 15.5 44 29 Q40.5 21.5 32 21.5 Q23.5 21.5 20 29 Z" fill={h} />;
    case "long": case "bob": return <path d="M20 30 Q20 15.5 32 15.5 Q44 15.5 44 30 Q39 21.5 32 21.5 Q25 21.5 20 30 Z" fill={h} />;
    case "curly": return <path d="M21 27 Q22 18.5 32 18.5 Q42 18.5 43 27 Q38 22 32 22 Q26 22 21 27 Z" fill={h} />;
    case "wrap": return (
      <g fill={look.wrap ?? "#c2a04a"}>
        <path d="M19.5 28 Q19 12.5 32 12.5 Q45 12.5 44.5 28 Q32 19.5 19.5 28 Z" />
        <ellipse cx="41" cy="12" rx="5" ry="3.6" />
      </g>
    );
    default: return null;
  }
}

export function Avatar({ look, expr = "neutral", badge, badgeBg = "#5b6c8f", ring, size = 48, dim = false }:
  { look: Look; expr?: Expr; badge?: string; badgeBg?: string; ring?: string; size?: number | string; dim?: boolean }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} style={{ overflow: "visible", opacity: dim ? 0.55 : 1 }} aria-hidden="true">
      <defs><clipPath id={id}><circle cx="32" cy="32" r="30" /></clipPath></defs>
      <circle cx="32" cy="32" r="30" fill="var(--sunken)" />
      <g clipPath={`url(#${id})`}>
        <HairBack look={look} />
        <path d="M9 66 Q10 47 32 47 Q54 47 55 66 Z" fill={look.top} />
        <rect x="28.5" y="41" width="7" height="8" rx="2" fill={look.skin} />
        <path d="M28.5 46.5 Q32 49 35.5 46.5 L35.5 49 L28.5 49 Z" fill="#000" opacity="0.12" />
        <ellipse cx="32" cy="31" rx="11.5" ry="13" fill={look.skin} />
        <ellipse cx="20.6" cy="32" rx="1.8" ry="2.6" fill={look.skin} /><ellipse cx="43.4" cy="32" rx="1.8" ry="2.6" fill={look.skin} />
        {look.beard && <path d="M21 35 Q22 48 32 48 Q42 48 43 35 Q40.5 41.5 32 41.5 Q23.5 41.5 21 35 Z" fill={look.hair} />}
        <HairFront look={look} />
        <Face e={expr} glasses={look.glasses} />
      </g>
      <circle cx="32" cy="32" r="30" fill="none" stroke={ring ?? "var(--line-2)"} strokeWidth={ring ? 2.6 : 1.6} />
      {badge && (
        <g>
          <circle cx="53" cy="53" r="8.6" fill={badgeBg} stroke="var(--surface)" strokeWidth="2" />
          <text x="53" y="56.4" textAnchor="middle" fontSize="9.5" fontWeight="700" fill="#fff" style={{ fontFamily: "var(--font-body)" }}>{badge}</text>
        </g>
      )}
    </svg>
  );
}

export type BotKind = "pip" | "bolt" | "nova";

function BotEyes({ e, cx = [27.5, 36.5], y = 31 }: { e: Expr; cx?: number[]; y?: number }) {
  return (
    <g stroke="var(--ink)" strokeWidth="1.5" strokeLinecap="round" fill="var(--ink)">
      {cx.map((x, i) => e === "pleased"
        ? <path key={i} d={`M${x - 2.2} ${y + 1} Q${x} ${y - 2.4} ${x + 2.2} ${y + 1}`} fill="none" />
        : e === "frustrated"
          ? <path key={i} d={`M${x - 2.4} ${y + (i ? -1.6 : 1.6) * -1} L${x + 2.4} ${y + (i ? 1.6 : -1.6) * -1}`} fill="none" />
          : <circle key={i} cx={x} cy={y} r={e === "thinking" && i ? 1 : 1.7} stroke="none" />)}
    </g>
  );
}

export function Bot({ kind, expr = "neutral", learned = false, ring, size = 52, dim = false }:
  { kind: BotKind; expr?: Expr; learned?: boolean; ring?: string; size?: number | string; dim?: boolean }) {
  const id = useId().replace(/:/g, "");
  const mouth = expr === "pleased" ? "M28 38 Q32 42 36 38" : expr === "frustrated" ? "M28.5 40.5 Q32 37.5 35.5 40.5" : "M29 39.5 H35";
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} style={{ overflow: "visible", opacity: dim ? 0.55 : 1 }} aria-hidden="true">
      <defs><clipPath id={id}><circle cx="32" cy="32" r="30" /></clipPath></defs>
      <circle cx="32" cy="32" r="30" fill="var(--sunken)" />
      <g clipPath={`url(#${id})`}>
        {kind === "pip" && (
          <g>
            <circle cx="14.5" cy="36" r="4.6" fill="var(--agent)" /><circle cx="49.5" cy="36" r="4.6" fill="var(--agent)" />
            <circle cx="32" cy="36" r="19" fill="var(--agent)" />
            <ellipse cx="32" cy="34" rx="12.5" ry="10" fill="var(--raised)" />
            <BotEyes e={expr} y={33} /><path d={mouth} transform="translate(0 1)" fill="none" stroke="var(--ink)" strokeWidth="1.4" strokeLinecap="round" />
          </g>
        )}
        {kind === "bolt" && (
          <g>
            <path d="M32 24 V15" stroke="var(--ink-3)" strokeWidth="2" /><circle cx="32" cy="13.5" r="3" fill="var(--ink-3)" />
            <rect x="14" y="23" width="36" height="31" rx="7" fill="var(--agent)" />
            <rect x="18.5" y="28" width="27" height="19" rx="4.5" fill="var(--raised)" />
            <BotEyes e={expr} y={35} /><path d={mouth} transform="translate(0 3)" fill="none" stroke="var(--ink)" strokeWidth="1.4" strokeLinecap="round" />
          </g>
        )}
        {kind === "nova" && (
          <g>
            <rect x="19.5" y="9" width="25" height="46" rx="12.5" fill="var(--agent)" />
            <rect x="22" y="20" width="20" height="11" rx="5.5" fill="var(--ink)" />
            <g stroke="var(--raised)" strokeWidth="1.6" strokeLinecap="round" fill="var(--raised)">
              {[28, 36].map((x, i) => expr === "pleased"
                ? <path key={i} d={`M${x - 2} 27 Q${x} 23.6 ${x + 2} 27`} fill="none" />
                : expr === "frustrated"
                  ? <path key={i} d={`M${x - 2} ${i ? 24 : 27} L${x + 2} ${i ? 27 : 24}`} fill="none" />
                  : <circle key={i} cx={x} cy={25.5} r={expr === "thinking" && i ? 0.9 : 1.8} stroke="none" />)}
            </g>
            <circle cx="32" cy="42" r="2.4" fill={expr === "pleased" ? "var(--ok)" : expr === "frustrated" ? "var(--bad)" : "var(--ink-3)"} />
          </g>
        )}
      </g>
      <circle cx="32" cy="32" r="30" fill="none" stroke={ring ?? "var(--line-2)"} strokeWidth={ring ? 2.6 : 1.6} />
      <g>
        <circle cx="53" cy="53" r="8.6" fill={learned ? "var(--ok)" : "var(--agent)"} stroke="var(--surface)" strokeWidth="2" />
        <text x="53" y="56.6" textAnchor="middle" fontSize="10" fontWeight="700" fill={learned ? "var(--human-on)" : "var(--bg)"} style={{ fontFamily: "var(--font-body)" }}>{learned ? "✓" : "A"}</text>
      </g>
    </svg>
  );
}

/* ---- the cast ---- */
export interface Person { name: string; role: string; city: string; look: Look; badge: string; badgeBg: string; quote: string }
export const CAST: Record<string, Person> = {
  priya: { name: "Priya Nair", role: "Developer", city: "Bengaluru", badge: "‹›", badgeBg: "#5b6c8f", quote: "“No new library. Use what we already have.”",
    look: { skin: "#c68c5f", hair: "#1f1717", style: "long", top: "#4f8a86" } },
  tomas: { name: "Tomás Rivera", role: "Developer", city: "Mexico City", badge: "‹›", badgeBg: "#5b6c8f", quote: "“Same thing happened to me on Tuesday.”",
    look: { skin: "#9a6a47", hair: "#241a14", style: "short", top: "#b9694f", beard: true } },
  amara: { name: "Amara Okafor", role: "Tech lead", city: "Lagos", badge: "✓", badgeBg: "#4f8a86", quote: "“Eleven sessions, three teams. That is a rule.”",
    look: { skin: "#6b4430", hair: "#1a1414", style: "wrap", wrap: "#c2a04a", top: "#3c4a66" } },
  kenji: { name: "Kenji Mori", role: "Security reviewer", city: "Osaka", badge: "!", badgeBg: "#b9694f", quote: "“A new dependency needs a review. Approved.”",
    look: { skin: "#f0cfae", hair: "#1c1c22", style: "short", top: "#5b6c8f", glasses: true } },
  sofia: { name: "Sofia Lindqvist", role: "Platform engineer", city: "Stockholm", badge: "#", badgeBg: "#7d9a72", quote: "“Platform keeps hitting this too.”",
    look: { skin: "#f3d6bd", hair: "#d2b36a", style: "bun", top: "#7d9a72" } },
  marcus: { name: "Marcus Bell", role: "CTO", city: "Toronto", badge: "★", badgeBg: "#3c4a66", quote: "“Fewer repeat corrections. That is what I wanted to see.”",
    look: { skin: "#a77352", hair: "#2a2a30", style: "bald", top: "#4a5568", beard: true } },
  lena: { name: "Lena Fischer", role: "Policy librarian", city: "Berlin", badge: "≡", badgeBg: "#8c6a8f", quote: "“Filed, with the quotes and turn ids attached.”",
    look: { skin: "#e8bf9c", hair: "#9a9aa5", style: "bob", top: "#8c6a8f", glasses: true } },
};
export const BOTS: Record<BotKind, { name: string; role: string; city: string; quote: string }> = {
  pip: { name: "Pip", role: "Agent", city: "Gemini CLI", quote: "“I proposed tenacity. I was told no, and why.”" },
  bolt: { name: "Bolt", role: "Agent", city: "2nd agent", quote: "“I read the new rule before my first edit.”" },
  nova: { name: "Nova", role: "Agent", city: "3rd agent", quote: "“Same rule, different agent. I follow it too.”" },
};
