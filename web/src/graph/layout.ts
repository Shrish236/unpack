// Layered left-to-right layout for the file cards (dagre: small, synchronous, deterministic).
import { graphlib, layout } from "@dagrejs/dagre";

export interface Sized { id: string; w: number; h: number }

export function layoutFiles(nodes: Sized[], edges: { source: string; target: string }[]): Record<string, { x: number; y: number }> {
  const g = new graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 36, ranksep: 84, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(n.id, { width: n.w, height: n.h });
  for (const e of edges) if (e.source !== e.target) g.setEdge(e.source, e.target);
  layout(g);
  const out: Record<string, { x: number; y: number }> = {};
  for (const n of nodes) {
    const p = g.node(n.id);
    out[n.id] = { x: p.x - n.w / 2, y: p.y - n.h / 2 };
  }
  return out;
}

// A tidy grid for many cards: reading order left to right, top to bottom, so the riskiest come first.
// Used instead of the layered layout once there are too many cards for the call structure to read clearly.
export function layoutGrid(nodes: Sized[], aspect = 1.5): Record<string, { x: number; y: number }> {
  const cols = Math.max(1, Math.ceil(Math.sqrt(nodes.length * aspect)));
  const out: Record<string, { x: number; y: number }> = {};
  const gapX = 36, gapY = 34;
  let y = 0;
  for (let i = 0; i < nodes.length; i += cols) {
    const row = nodes.slice(i, i + cols);
    let x = 0;
    for (const n of row) { out[n.id] = { x, y }; x += n.w + gapX; }
    y += Math.max(...row.map((n) => n.h)) + gapY;
  }
  return out;
}
