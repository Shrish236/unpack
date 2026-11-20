import type { DType, HumanKind } from "./data";
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
  test: { label: "direct" | "reached" | "reached_uncertain" | "none"; count: number; nearest_tested: string | null; shortest_path?: string[] } | null;
  callers_count: number; callees_count: number;
  parent: string | null; is_async: boolean; is_public: boolean; has_reason: boolean; finding_ids: number[];
}
export interface GEdge {
  id: string; source: string; target: string;
  kind: "CALLS" | "INHERITS" | "OVERRIDES" | "REACHES" | "IMPORTS";
  tier: "EXTRACTED" | "INFERRED" | "AMBIGUOUS" | null; via: string | null;
}
export interface GCollapsed { id: string; anchor: string; direction: "callers" | "callees" | "tests"; file: string; count: number; node_ids: string[] }
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
  graph: { nodes: GNode[]; edges: GEdge[]; collapsed: GCollapsed[] };
  reading_order: string[];
  impact: { summary: { functions: number; files: number; public_api: number; uncertain_paths: number }; by_node: Record<string, ImpactHit[]> };
  timeline: TimelineItem[];
  reasons: Record<string, Reason>;
  findings: Finding[];
  diff_hunks: Record<string, { start_line: number; end_line: number; patch: string }[]>;
  governance: Governance;
}
export interface GovDecision {
  turn: string; actor: "agent" | "human"; kind: string; type: string; proposal: string; choice: string; statement: string;
  quote: string; rule: string | null; rule_followed: boolean | null; source: "parsed" | "llm";
}
export interface Governance {
  decisions: GovDecision[];
  highlights: { kind: "went_right" | "went_wrong"; text: string; turn: string; quote: string }[];
  flags: { flag: string; path: string; detail: string }[];
  tool_stats: Record<string, { calls: number; tokens: number }>;
  attempts: number; human_interventions: number; steering_files: string[]; steering_rules: number; available: boolean;
}
export interface Measured {
  sessions: number; decisions: number; human_decisions: number; human_kinds: Record<string, number>;
  adherence: number | null; rule_checks: number; overrides_per_100: number | null; tool_calls: number; tokens: number;
  flags: Record<string, number>;
}
export interface Turn { turn_id: string; kind: string; ts: string; text: string | null; path: string | null; excerpt: string | null; command: string | null }

export class ApiError extends Error {
  constructor(public kind: "login" | "forbidden" | "notfound" | "network" | "server", message: string, public status = 0) { super(message); }
}

interface RequestInit2 { method?: "GET" | "POST"; body?: unknown }

// One place for transport and error mapping. A 400 or 409 carries the server's message, shown to the person.
async function request<T>(path: string, init: RequestInit2 = {}): Promise<T> {
  const hasBody = init.body !== undefined;
  let r: Response;
  try {
    r = await fetch(path, {
      method: init.method ?? "GET",
      headers: hasBody ? { accept: "application/json", "content-type": "application/json" } : { accept: "application/json" },
      body: hasBody ? JSON.stringify(init.body) : undefined,
    });
  } catch { throw new ApiError("network", "The Unpack API is not reachable."); }
  if (r.status === 401) throw new ApiError("login", "You are not logged in.", 401);
  if (r.status === 403) throw new ApiError("forbidden", "You do not have access to this repository.", 403);
  if (!r.ok) {
    const detail = await r.json().then((b) => (b?.error?.message as string | undefined), () => undefined);
    if (r.status === 404) throw new ApiError("notfound", detail ?? "Not found.", 404);
    throw new ApiError("server", detail ?? `The API answered HTTP ${r.status}.`, r.status);
  }
  return r.json() as Promise<T>;
}


// While queued or running the API returns only {analysis:{public_id,status}}; a failed one adds error fields.
export const fetchAnalysis = (id: string) => request<AnalysisResponse>(`/api/analyses/${encodeURIComponent(id)}`);
export const fetchTurns = (id: string, ids: string[]) =>
  request<{ turns: Turn[] }>(`/api/analyses/${encodeURIComponent(id)}/turns?ids=${ids.join(",")}`);

// There is no "latest analysis" endpoint, so #/pr opens this one. Override with VITE_DEFAULT_ANALYSIS.
export const DEFAULT_ANALYSIS: string = import.meta.env.VITE_DEFAULT_ANALYSIS || "j8ujHFB_bhPENJl1fw2haQ";

/* ------------------------------------------------------------------------------------------
   Dashboards: executive, managers, governance. Dummy data on the server until the pipeline measures
   it (server/app/dashboard_seed.py). Field names follow the API, which is snake_case.
   ------------------------------------------------------------------------------------------ */

export type Period = "30d" | "90d";
export type Autonomy = "advice" | "check" | "gate";
export type Scope = "repo" | "team" | "org";
export type Enforcement = "advice" | "check" | "gate";
export type Flag = "unsupported" | "new-dependency" | "skipped-test" | "async-gap";

export interface ExecData {
  period: Period;
  measured?: Measured;
  weeks: string[]; // ISO Mondays, oldest first, within the period
  adherence: number[];
  repeat_overrides: number[];
  human_per_week: number[];
  mix: Record<DType, number[]>;
  policy_events: { id: string; week: number; text: string }[]; // week is an index into weeks
  headline: { id: string; before: number; after: number } | null;
  kpis: {
    adherence: { v: number; d: number };
    override: { v: number; before: number };
    verified: { v: number; d: number };
    unrequested: { v: number; d: number };
    pending: { v: number; oldest_days: number };
    sessions: number;
  };
  rework: { first: number; missed: number; thin: number };
  human_kinds: { kind: HumanKind; label: string; pct: number }[];
  agents: {
    name: string; tool: string; decisions: number | null; verified: number | null; unrequested: number | null;
    attempts: number | null; autonomy: Autonomy | null;
  }[];
  backlog: { id: string; statement: string; sessions: number; teams: number; developers: number; waiting_days: number }[];
  expiring: { id: string; statement: string; in_days: number; owner: string }[];
}

export interface ConsistencyItem {
  id: string; type: DType; question: string; rows: { team: string; approach: string; prs: number }[];
}

export interface TeamsIndex {
  teams: { id: string; name: string }[];
  consistency: ConsistencyItem[];
}

export interface TeamPage {
  id: string;
  name: string;
  weeks: string[]; // ISO Mondays, oldest first
  kpis: { prs: number; prs_delta: string; attempts: number; attempts_delta: string; overrules: number; thin: number; unsupported: number };
  areas: { path: string; attempts: number[]; overrules: number[] }[]; // one value per week, 0 = no criteria
  funnel: { total: number; first: number; second: { agent: number; thin: number }; third: { agent: number; thin: number } };
  suggestions: { cause: "requirement-thin" | "agent-missed"; text: string; prs: number[] }[];
  mix: { type: DType; agent: number; human: number }[];
  tools: { name: string; calls: number; tokens: number }[];
  prs: {
    number: number; title: string; area: string; week: number; agent: string; agent_decisions: number;
    human_decisions: number; overrules: number; attempts: number; flags: Flag[]; source?: "sample" | "measured";
  }[];
}

export interface GovEvidence {
  id: string; session: string; pr: string; team: string; dev: string; turn: number; kind: HumanKind;
  proposal: string; choice: string; quote: string; when: string; source?: "sample" | "measured";
}

// The decision brief: what a reviewer needs to decide on a candidate beyond the quotes.
export interface Reach { repos: number; teams: number; scanned: number; flagged: number; confirmed: number } // PR replay over 90 days
export interface TeamSplit { team: string; developers: number; overruled: number; accepted: number } // accepted = same proposal, nobody objected
export interface Conflict { id: string; level: "overlap" | "conflict"; note: string }
export interface Recommendation { action: "approve" | "trial" | "wait"; enforcement: Enforcement; reason: string }
export interface Brief {
  proposed: number; // sessions in which the agent made this kind of proposal
  teams: TeamSplit[];
  areas: { area: string; n: number }[];
  rework: { turns: number; hours: number; prs: number };
  reach: Record<Scope, Reach>;
  conflicts: Conflict[];
  recommend: Recommendation;
}

export interface GovCandidate {
  id: string; pid: string; statement: string; type: DType; sessions: number; teams: number; developers: number;
  trend: number[]; per_hundred: number; match: string; scope: Scope; enforcement: Enforcement; owner: string;
  expires: string; evidence: GovEvidence[]; source?: "sample" | "measured";
  brief?: Brief | null;
}

export interface GovPolicy {
  id: string; statement: string; type: DType; scope: Scope; scope_name: string; enforcement: Enforcement; owner: string;
  expires: string; adherence: number | null; before: number; after: number | null; match: string;
  recurrence: { sessions: number; teams: number; developers: number; evidence: GovEvidence[] } | null;
  target?: number | null; // overrides per 100 sessions the policy is meant to reach
  review?: string | null; // date the owner checks whether it worked
  approved?: string | null;
  weekly?: number[] | null; // overrides per 100 sessions per week since approval, oldest first
  checks?: { flagged: number; wrong: number } | null; // PRs the check flagged, and how many a reviewer overrode as wrong
}

export interface GovRule {
  id: string; text: string; skill: string; followed: number; violated: number; trend: number[];
  latest_pr: string; latest_turn: number; source?: "sample" | "measured";
}

export interface GovHistory { id: string; statement: string; outcome: "approved" | "rejected" | "expired" | "watching"; role: string; when: string; why: string }

export interface GovernanceState {
  today: string;
  candidates: GovCandidate[];
  policies: GovPolicy[];
  rules: GovRule[];
  history: GovHistory[];
}

export interface ApproveBody { statement: string; scope: Scope; enforcement: Enforcement; owner: string; expires: string; target?: number | null; review?: string | null }

export const fetchExec = (period: Period) => request<ExecData>(`/api/dashboard/exec?period=${period}`);
export const fetchTeams = () => request<TeamsIndex>("/api/dashboard/teams");
export const fetchTeam = (id: string) => request<TeamPage>(`/api/dashboard/teams/${encodeURIComponent(id)}`);
export const fetchGovernance = () => request<GovernanceState>("/api/governance");
export const approveCandidate = (id: string, body: ApproveBody) =>
  request<GovernanceState>(`/api/governance/candidates/${encodeURIComponent(id)}/approve`, { method: "POST", body });
export const rejectCandidate = (id: string, reason: string) =>
  request<GovernanceState>(`/api/governance/candidates/${encodeURIComponent(id)}/reject`, { method: "POST", body: { reason } });
export const retirePolicy = (id: string) =>
  request<GovernanceState>(`/api/governance/policies/${encodeURIComponent(id)}/retire`, { method: "POST" });
export const revisePolicy = (id: string) =>
  request<GovernanceState>(`/api/governance/policies/${encodeURIComponent(id)}/revise`, { method: "POST" });
export const watchCandidate = (id: string) =>
  request<GovernanceState>(`/api/governance/candidates/${encodeURIComponent(id)}/watch`, { method: "POST" });
export const renewPolicy = (id: string) =>
  request<GovernanceState>(`/api/governance/policies/${encodeURIComponent(id)}/renew`, { method: "POST" });
export const relaxPolicy = (id: string) =>
  request<GovernanceState>(`/api/governance/policies/${encodeURIComponent(id)}/relax`, { method: "POST" });
