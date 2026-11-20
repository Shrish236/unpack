// Typed client for the viewer endpoints (docs/api-contract.md §5). Same-origin: the browser sends the session cookie.

export type Driver = "user_asked" | "agent_decided" | "not_stated";
export interface Evidence { turn: string; quote: string }
export interface Reason {
  reason: string | null; driver: Driver; confidence: "high" | "medium" | "low"; source: string;
  history: { turn: string; text: string }[]; evidence: Evidence[];
}
export interface GNode {
  id: string; label: string; kind: string; path: string; start_line: number | null; end_line: number | null;
  signature: string | null; layer: string; change: { kind: string; source: string } | null;
  test: { label: "direct" | "reached" | "reached_uncertain" | "none"; count: number; nearest_tested: string | null } | null;
  callers_count: number; callees_count: number;
}
export interface TimelineItem {
  turn: string; kind: string; ts: string; label: string; nodes: string[]; reverted: boolean; exit_code: number | null; finding_id: number | null;
}
export interface Finding { id: number; kind: string; finding: string; functions: string[]; evidence: Evidence[] }
export interface ImpactHit { id: string; depth: number; tier: string; uncertain: boolean }
export interface AnalysisResponse {
  analysis: {
    public_id: string; status: string; repo: { owner: string; name: string }; branch: string; short_sha: string;
    created_at: string; agent: string | null; llm_model: string | null; has_session: boolean;
    error_code?: string | null; error_message?: string | null;
  };
  pull_request: { number: number; title: string; url: string; state: string } | null;
  banner: { kind: string; message: string } | null;
  summary: string;
  stats: { functions_changed: number; by_source: Record<string, number>; by_change: Record<string, number>; not_reached_by_tests: number };
  facts: { last_test_run: { turn: string; command: string; exit_code: number; summary: string } | null; tested_after_final_edit: boolean | null };
  graph: { nodes: GNode[] };
  reading_order: string[];
  impact: { summary: { functions: number; files: number; public_api: number; uncertain_paths: number }; by_node: Record<string, ImpactHit[]> };
  timeline: TimelineItem[];
  reasons: Record<string, Reason>;
  findings: Finding[];
  diff_hunks: Record<string, { start_line: number; end_line: number; patch: string }[]>;
}
export interface Turn { turn_id: string; kind: string; ts: string; text: string | null; path: string | null; excerpt: string | null; command: string | null }

export class ApiError extends Error {
  constructor(public kind: "login" | "forbidden" | "notfound" | "network" | "server", message: string, public status = 0) { super(message); }
}

async function get<T>(path: string): Promise<T> {
  let r: Response;
  try { r = await fetch(path, { headers: { accept: "application/json" } }); }
  catch { throw new ApiError("network", "The Unpack API is not reachable."); }
  if (r.status === 401) throw new ApiError("login", "You are not logged in.", 401);
  if (r.status === 403) throw new ApiError("forbidden", "You do not have access to this repository.", 403);
  if (r.status === 404) throw new ApiError("notfound", "No such analysis.", 404);
  if (!r.ok) throw new ApiError("server", `The API answered HTTP ${r.status}.`, r.status);
  return r.json() as Promise<T>;
}

// While queued or running the API returns only {analysis:{public_id,status}}; a failed one adds error fields.
export const fetchAnalysis = (id: string) => get<AnalysisResponse>(`/api/analyses/${encodeURIComponent(id)}`);
export const fetchTurns = (id: string, ids: string[]) =>
  get<{ turns: Turn[] }>(`/api/analyses/${encodeURIComponent(id)}/turns?ids=${ids.join(",")}`);

// There is no "latest analysis" endpoint, so #/pr opens this one. Override with VITE_DEFAULT_ANALYSIS.
export const DEFAULT_ANALYSIS: string = import.meta.env.VITE_DEFAULT_ANALYSIS || "j8ujHFB_bhPENJl1fw2haQ";
