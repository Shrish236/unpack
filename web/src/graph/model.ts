// Shared model for the graph prototypes. Both renderers (dots and cards) read the same analysis, so a
// colour or a word means the same thing in each. Nothing here is computed from the code: it reads
// the contract (AnalysisResponse) and sorts it.
import type { AnalysisResponse, Driver, GCollapsed, GEdge, GNode, ImpactHit } from "../api";

export type ChangeKind = "added" | "functional" | "signature" | "text_only" | "deleted";
export type CardKind = "container" | "changed" | "context" | "test" | "ghost";

export const CHANGE_KINDS: ChangeKind[] = ["added", "functional", "signature", "deleted", "text_only"];

// Colours are the app's own tokens, so the graph follows the light and dark themes. `color` fills stripes and
// dots; `text` is the same hue made readable as small text.
export const CHANGE_STYLE: Record<ChangeKind, { label: string; color: string; text: string }> = {
  added: { label: "ADDED", color: "var(--ok)", text: "var(--ok)" },
  functional: { label: "MODIFIED", color: "var(--human)", text: "var(--human-text)" },
  signature: { label: "SIGNATURE", color: "var(--warn)", text: "var(--warn)" },
  text_only: { label: "FORMATTING", color: "var(--ink-3)", text: "var(--ink-3)" },
  deleted: { label: "REMOVED", color: "var(--bad)", text: "var(--bad)" },
};


export const CHANGE_WORDS: Record<ChangeKind, string> = {
  added: "New function, added in this change",
  functional: "Behaviour changed: the body is different",
  signature: "Signature changed: parameters or return type differ",
  text_only: "Formatting only: no behaviour change",
  deleted: "Removed: it is no longer in the code",
};

export const SOURCE_WORDS: Record<string, string> = {
  session: "Edited in the agent's session",
  session_then_formatted: "Edited in the session, then reformatted",
  session_partial: "Edited in the session, then changed again outside it",
  outside_session: "Changed outside the agent's session",
};

export const DRIVER_WORDS: Record<Driver, string> = {
  user_asked: "User asked",
  agent_decided: "Agent decided",
  not_stated: "Not stated",
};

export const TEST_WORDS: Record<NonNullable<GNode["test"]>["label"], string> = {
  direct: "A test calls it directly",
  reached: "Reached by tests",
  reached_uncertain: "Maybe reached, through an uncertain path",
  none: "No test reaches this",
};

export interface Graph {
  analysis: AnalysisResponse;
  nodes: GNode[];
  byId: Record<string, GNode>;
  edges: GEdge[];
  collapsed: GCollapsed[];
  changed: GNode[]; // in reading order, then by line
  counts: Record<ChangeKind, number>;
  untested: number;
  outsideSession: number;
}

export function cardKind(n: GNode): CardKind {
  if (n.layer === "container") return "container";
  if (n.layer === "ghost" || n.change?.kind === "deleted") return "ghost";
  if (n.layer === "test" || n.kind === "test") return "test";
  if (n.change) return "changed";
  return "context";
}

export function changeKindOf(n: GNode): ChangeKind | null {
  return n.change ? (n.change.kind as ChangeKind) : null;
}

export function isUntested(n: GNode): boolean {
  return !!n.change && (!n.test || n.test.label === "none");
}

export function buildGraph(a: AnalysisResponse): Graph {
  const nodes = a.graph.nodes;
  const byId: Record<string, GNode> = {};
  for (const n of nodes) byId[n.id] = n;

  const order = new Map(a.reading_order.map((id, i) => [id, i] as const));
  const changed = nodes
    .filter((n) => n.change)
    .sort((x, y) => (order.get(x.id) ?? 1e6) - (order.get(y.id) ?? 1e6) || (x.start_line ?? 0) - (y.start_line ?? 0));

  const counts = { added: 0, functional: 0, signature: 0, text_only: 0, deleted: 0 } as Record<ChangeKind, number>;
  for (const n of changed) {
    const k = changeKindOf(n);
    if (k) counts[k] += 1;
  }

  return {
    analysis: a,
    nodes,
    byId,
    edges: a.graph.edges,
    collapsed: a.graph.collapsed,
    changed,
    counts,
    untested: changed.filter(isUntested).length,
    outsideSession: changed.filter((n) => n.change?.source === "outside_session").length,
  };
}

// Blast radius for a selected node: depth 1, 2, 3 from the server's impact list.
export function blastOf(a: AnalysisResponse, id: string): Map<string, ImpactHit> {
  const out = new Map<string, ImpactHit>();
  for (const hit of a.impact.by_node[id] ?? []) out.set(hit.id, hit);
  return out;
}

// Node ids connected to the selection by a call or a test-reach edge.
export function neighbourhood(edges: GEdge[], id: string): Set<string> {
  const s = new Set<string>([id]);
  for (const e of edges) {
    if (e.source === id) s.add(e.target);
    if (e.target === id) s.add(e.source);
  }
  return s;
}

export function sizeOf(n: GNode): number {
  const lines = n.start_line != null && n.end_line != null ? Math.max(1, n.end_line - n.start_line) : 10;
  return Math.min(12, 5 + Math.log2(lines + 1));
}

export const lastName = (id: string) => id.split("::").slice(1).join(".") || id;
export const fileOf = (n: GNode) => n.path;
