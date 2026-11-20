// The order a reviewer reads the changed functions in. Four choices:
//   session      the order the agent edited them (first edit turn in the session timeline), so you can follow how it worked
//   logical      callers before callees: the entry points first, then what they depend on. The server computes it
//                (analysis.flow.deterministic); an older analysis without it falls back to the same rule here
//   ai           the model's reading flow: stages with a title, and a note per function (analysis.flow.llm)
//   alphabetical by file, then function name
// Functions the session did not edit (changed outside it) follow the session ones, in the server's reading order.
import type { Graph } from "./model";

export type OrderMode = "session" | "logical" | "ai" | "alphabetical";

export const ORDER_LABEL: Record<OrderMode, string> = { session: "Agent's order", logical: "Call order", ai: "AI flow", alphabetical: "A–Z" };
export const ORDER_HINT: Record<OrderMode, string> = {
  session: "The order the agent edited them in this session",
  logical: "Callers first, then the functions they depend on",
  ai: "The model's reading flow: stages, from where the work enters to where it ends",
  alphabetical: "By file, then function name",
};

// The modes a given analysis can offer. The AI flow only exists when the model produced one.
export function availableModes(g: Graph): OrderMode[] {
  return (["ai", "logical", "session", "alphabetical"] as OrderMode[]).filter((m) => m !== "ai" || !!g.analysis.flow?.llm);
}

// Keep the flow's order for the functions that are in the graph, and put any the flow left out at the end in the
// server's reading order, so a flow can never hide a changed function.
function fromFlow(order: string[], ids: string[]): string[] {
  const known = new Set(ids);
  const seen = new Set<string>();
  const out = order.filter((id) => known.has(id) && !seen.has(id) && seen.add(id));
  return [...out, ...ids.filter((id) => !seen.has(id))];
}

// The stage a function belongs to in the given flow, with the model's role and note for it.
export function stageOf(g: Graph, mode: OrderMode, id: string): { title: string; summary: string; index: number; role: string | null; note: string } | null {
  const flow = mode === "ai" ? g.analysis.flow?.llm : mode === "logical" ? g.analysis.flow?.deterministic : null;
  if (!flow) return null;
  const index = flow.stages.findIndex((s) => s.node_ids.includes(id));
  if (index < 0) return null;
  const st = flow.stages[index];
  const step = st.steps.find((x) => x.node === id);
  return { title: st.title, summary: st.summary, index, role: step?.role ?? null, note: step?.note ?? "" };
}

const turnNumber = (t: string) => Number(t.replace(/\D/g, "")) || 0;

export function orderFunctions(g: Graph, mode: OrderMode): string[] {
  const ids = g.changed.map((n) => n.id); // already in the server's reading order
  const base = new Map(ids.map((id, i) => [id, i] as const));

  if (mode === "alphabetical") {
    return [...ids].sort((a, b) => g.byId[a].path.localeCompare(g.byId[b].path) || g.byId[a].label.localeCompare(g.byId[b].label));
  }

  if (mode === "session") {
    const first = new Map<string, number>();
    for (const ev of g.analysis.timeline) {
      if (ev.kind !== "edit") continue;
      for (const id of ev.nodes) if (base.has(id) && !first.has(id)) first.set(id, turnNumber(ev.turn));
    }
    return [...ids].sort((a, b) => (first.get(a) ?? 1e9) - (first.get(b) ?? 1e9) || base.get(a)! - base.get(b)!);
  }

  if (mode === "ai" && g.analysis.flow?.llm) return fromFlow(g.analysis.flow.llm.order, ids);
  if (mode === "logical" && g.analysis.flow?.deterministic.order.length) return fromFlow(g.analysis.flow.deterministic.order, ids);

  // logical without a server flow: a stable topological order over the calls between changed functions, callers first
  const callees = new Map<string, string[]>();
  const indeg = new Map<string, number>(ids.map((id) => [id, 0]));
  for (const e of g.edges) {
    if (e.kind !== "CALLS" || !base.has(e.source) || !base.has(e.target) || e.source === e.target) continue;
    (callees.get(e.source) ?? callees.set(e.source, []).get(e.source)!).push(e.target);
    indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1);
  }
  const out: string[] = [];
  const done = new Set<string>();
  let ready = ids.filter((id) => indeg.get(id) === 0);
  while (out.length < ids.length) {
    if (ready.length === 0) { // a cycle: take the earliest unplaced function and carry on
      const next = ids.find((id) => !done.has(id));
      if (!next) break;
      ready = [next];
    }
    ready.sort((a, b) => base.get(a)! - base.get(b)!);
    const id = ready.shift()!;
    if (done.has(id)) continue;
    done.add(id);
    out.push(id);
    for (const c of callees.get(id) ?? []) {
      indeg.set(c, (indeg.get(c) ?? 1) - 1);
      if ((indeg.get(c) ?? 0) <= 0 && !done.has(c)) ready.push(c);
    }
  }
  return out;
}
