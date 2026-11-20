// Isometric projection (2:1) and the scene's world data. World units: x runs down-right, y down-left, z up.
// The flow runs top to bottom on screen: session plane -> policy pad -> skill file -> agent.

export const W = 600;
export const H = 630;
const S = 38;   // half tile width in svg units
const HF = 19;  // half tile height
const ZU = 36;  // one unit of height
const OX = 262;
const OY = 76;
const K = 1.118; // the scene was laid out at 1x; T() maps those hand-placed screen points (callouts, loop path) to this scale
export const T = ([x, y]: XY): XY => [(x - 300) * K + 300, (y - 300) * K + 300];

export type XY = [number, number];
export const P = (x: number, y: number, z = 0): XY => [OX + (x - y) * S, OY + (x + y) * HF - z * ZU];
const L = (x: number, y: number, z = 0): XY => [(x - y) * S, (x + y) * HF - z * ZU]; // local: box min corner at the origin
export const pts = (a: XY[]) => a.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

/** Faces of a box with its min base corner at the local origin. `l` faces +y (front-left), `r` faces +x (front-right). */
export function faces(w: number, d: number, h: number) {
  return {
    t: pts([L(0, 0, h), L(w, 0, h), L(w, d, h), L(0, d, h)]),
    l: pts([L(0, d, 0), L(w, d, 0), L(w, d, h), L(0, d, h)]),
    r: pts([L(w, 0, 0), L(w, d, 0), L(w, d, h), L(w, 0, h)]),
    top: L(w / 2, d / 2, h),
  };
}
export const quad = (a: [number, number, number], b: [number, number, number], c: [number, number, number], d: [number, number, number]) =>
  pts([P(...a), P(...b), P(...c), P(...d)]);

export type DType = "architecture" | "design" | "dependency" | "retries" | "test" | "scope";
export interface Cube {
  id: string; who: "agent" | "human"; type: DType; tx: number; ty: number; turn: number;
  bump?: [number, number]; // world offset when a human decision displaces it
  verdict?: "ok" | "bad";  // the governance gate's verdict on an agent decision
}
// Ordered by turn. h1/h2 overrule a2/a4.
export const CUBES: Cube[] = [
  { id: "a1", who: "agent", type: "architecture", tx: 0, ty: 0, turn: 14 },
  { id: "a2", who: "agent", type: "dependency", tx: 1, ty: 1, turn: 16, bump: [0, 1.1], verdict: "bad" },
  { id: "h1", who: "human", type: "dependency", tx: 2, ty: 1, turn: 18 },
  { id: "a3", who: "agent", type: "retries", tx: 3, ty: 0, turn: 22, verdict: "ok" },
  { id: "a4", who: "agent", type: "test", tx: 2, ty: 2, turn: 31, bump: [0, 1.0], verdict: "bad" },
  { id: "h2", who: "human", type: "test", tx: 3, ty: 2, turn: 33 },
  { id: "a5", who: "agent", type: "design", tx: 4, ty: 1, turn: 36, verdict: "ok" },
  { id: "h3", who: "human", type: "scope", tx: 5, ty: 2, turn: 40 },
  { id: "a6", who: "agent", type: "test", tx: 4, ty: 3, turn: 47, verdict: "bad" },
];

export const COLS = 6;
export const ROWS = 4;
export const CUBE = { inset: 0.2, size: 0.6, h: 0.58, base: 0.1 };

// 11 sessions where the same overrule happened (tile coords), and where they pile up on the pad
export const MICRO_TILES: XY[] = [[0, 1], [0, 3], [1, 0], [1, 2], [2, 0], [3, 1], [3, 3], [4, 0], [4, 2], [5, 0], [5, 3]];
export const PAD = { cx: 7.4, cy: 5.6 };
export const PILE: [number, number, number][] = (() => {
  const out: [number, number, number][] = [];
  for (let j = 0; j < 3; j++) for (let i = 0; i < 3; i++) out.push([PAD.cx - 0.48 + i * 0.32, PAD.cy - 0.48 + j * 0.32, 0]);
  out.push([PAD.cx - 0.32, PAD.cy - 0.32, 0.3], [PAD.cx, PAD.cy, 0.3]);
  return out;
})();

export const GATE = { rest: 6.2, start: -0.7 }; // x of the gate frame at rest (past the plane) and where its sweep starts
export const SKILL = { x: 8.6, y: 7.4, w: 1.8, d: 2.2, h: 0.3 };
export const SLAB = { x: 6.75, y: 5.05, w: 1.3, d: 1.1, h: 0.3 };
export const AGENT = { x: 12.3, y: 10.9, w: 0.9, d: 0.9, h: 1.0 };
export const CONV = { s: [10.6, 9.5] as XY, e: [12.2, 11.1] as XY };

/** Callout in svg units: the card sits on `side` of the anchor; the leader runs from the anchor to the target. */
export interface Callout { ax: number; ay: number; side: "l" | "r" | "b"; tx: number; ty: number; sec?: boolean; key: string }
export const px = (n: number) => `${((n / W) * 100).toFixed(2)}%`;
export const py = (n: number) => `${((n / H) * 100).toFixed(2)}%`;
