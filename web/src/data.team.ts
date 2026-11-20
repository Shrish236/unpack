// Illustrative data for the manager view. Shaped like the brief's records, aggregated per team and area.
// Nothing here is measured. Teams, areas and code are measured, never individual developers.
import type { DType } from "./data";

export type TeamId = "payments" | "auth" | "search";
export type Flag = "unsupported" | "new-dependency" | "skipped-test" | "async-gap";

export const FLAG_LABEL: Record<Flag, string> = {
  unsupported: "Unsupported claim",
  "new-dependency": "New dependency",
  "skipped-test": "Skipped test",
  "async-gap": "Untested path",
};

export interface Area { path: string; attempts: number[]; overrules: number[] } // one value per week, 0 = no criteria
export interface PrRow { n: number; title: string; area: string; week: number; agent: string; a: number; h: number; overrules: number; attempts: number; flags: Flag[] }
export interface Suggestion { cause: "requirement-thin" | "agent-missed"; text: string; prs: number[] }
export interface TeamData {
  name: string;
  kpis: { prs: number; prsDelta: string; attempts: number; attemptsDelta: string; overrules: number; thin: number; unsupported: number };
  areas: Area[];
  funnel: { total: number; first: number; second: { agent: number; thin: number }; third: { agent: number; thin: number } };
  suggestions: Suggestion[];
  mix: { type: DType; agent: number; human: number }[];
  tools: { name: string; calls: number; tokens: number }[];
  prs: PrRow[];
}

// 8 weeks ending Mon 16 Nov 2026
export const WEEKS = ["Sep 28", "Oct 5", "Oct 12", "Oct 19", "Oct 26", "Nov 2", "Nov 9", "Nov 16"];

export const teams: Record<TeamId, TeamData> = {
  payments: {
    name: "Payments",
    kpis: { prs: 38, prsDelta: "+6", attempts: 1.71, attemptsDelta: "+0.18", overrules: 1.4, thin: 19, unsupported: 11 },
    areas: [
      { path: "payments/client", attempts: [1.3, 1.4, 1.2, 1.6, 2.1, 2.4, 2.2, 1.9], overrules: [1, 1, 0, 2, 4, 5, 4, 3] },
      { path: "payments/ledger", attempts: [1.1, 1.0, 1.2, 1.1, 1.3, 1.2, 1.1, 1.2], overrules: [0, 0, 1, 0, 1, 1, 0, 1] },
      { path: "payments/webhooks", attempts: [0, 1.5, 1.8, 1.4, 0, 1.6, 1.7, 2.0], overrules: [0, 2, 3, 1, 0, 2, 2, 4] },
      { path: "payments/refunds", attempts: [1.2, 0, 1.3, 1.5, 1.4, 0, 1.2, 1.3], overrules: [1, 0, 1, 2, 1, 0, 1, 1] },
      { path: "shared/http", attempts: [0, 0, 1.1, 0, 1.9, 2.2, 0, 1.4], overrules: [0, 0, 0, 0, 3, 4, 0, 2] },
    ],
    funnel: { total: 112, first: 61, second: { agent: 29, thin: 22 }, third: { agent: 9, thin: 5 } },
    suggestions: [
      { cause: "requirement-thin", text: "Add a parity line to the ticket template: “applies to Client and AsyncClient”.", prs: [482, 471, 455] },
      { cause: "agent-missed", text: "Agents add a new package for small helpers. The skill rule exists but is not applied in payments/client.", prs: [482, 468] },
      { cause: "requirement-thin", text: "Webhook tickets omit the retry budget. Humans add it at the second turn.", prs: [477, 463] },
    ],
    mix: [
      { type: "architecture", agent: 31, human: 6 },
      { type: "design", agent: 27, human: 9 },
      { type: "dependency", agent: 14, human: 11 },
      { type: "retries", agent: 18, human: 7 },
      { type: "test", agent: 33, human: 12 },
      { type: "scope", agent: 6, human: 15 },
    ],
    tools: [
      { name: "read_file", calls: 1480, tokens: 1_310_000 },
      { name: "replace", calls: 610, tokens: 1_790_000 },
      { name: "run_shell_command", calls: 430, tokens: 320_000 },
      { name: "grep_search", calls: 340, tokens: 150_000 },
      { name: "write_todos", calls: 96, tokens: 41_000 },
      { name: "write_file", calls: 74, tokens: 108_000 },
    ],
    prs: [
      { n: 482, title: "Add retry to the payments client", area: "payments/client", week: 7, agent: "Gemini CLI", a: 6, h: 3, overrules: 2, attempts: 1.75, flags: ["unsupported", "new-dependency", "skipped-test"] },
      { n: 477, title: "Retry failed webhook deliveries", area: "payments/webhooks", week: 7, agent: "Gemini CLI", a: 8, h: 4, overrules: 2, attempts: 2.0, flags: ["async-gap"] },
      { n: 471, title: "Idempotency keys for refunds", area: "payments/refunds", week: 6, agent: "Claude Code", a: 7, h: 2, overrules: 1, attempts: 1.3, flags: [] },
      { n: 468, title: "Shared HTTP client timeouts", area: "shared/http", week: 6, agent: "Gemini CLI", a: 5, h: 5, overrules: 4, attempts: 2.2, flags: ["new-dependency"] },
      { n: 463, title: "Webhook signature rotation", area: "payments/webhooks", week: 5, agent: "Claude Code", a: 9, h: 3, overrules: 2, attempts: 1.6, flags: [] },
      { n: 455, title: "Ledger entry reconciliation", area: "payments/ledger", week: 4, agent: "Gemini CLI", a: 6, h: 1, overrules: 0, attempts: 1.1, flags: [] },
      { n: 449, title: "Async client connection pool", area: "payments/client", week: 4, agent: "Gemini CLI", a: 7, h: 4, overrules: 3, attempts: 2.1, flags: ["unsupported", "skipped-test"] },
    ],
  },
  auth: {
    name: "Auth",
    kpis: { prs: 24, prsDelta: "+2", attempts: 1.42, attemptsDelta: "−0.05", overrules: 0.9, thin: 12, unsupported: 6 },
    areas: [
      { path: "auth/session", attempts: [1.2, 1.1, 1.3, 1.2, 1.4, 1.2, 1.1, 1.3], overrules: [0, 0, 1, 1, 1, 0, 0, 1] },
      { path: "auth/oauth", attempts: [0, 1.6, 1.9, 1.7, 1.5, 0, 1.4, 1.6], overrules: [0, 2, 3, 2, 1, 0, 1, 2] },
      { path: "auth/tokens", attempts: [1.1, 0, 1.2, 1.0, 0, 1.3, 1.2, 0], overrules: [0, 0, 1, 0, 0, 1, 1, 0] },
      { path: "auth/admin", attempts: [0, 0, 0, 1.5, 1.3, 0, 1.2, 1.1], overrules: [0, 0, 0, 1, 1, 0, 0, 0] },
    ],
    funnel: { total: 71, first: 46, second: { agent: 13, thin: 7 }, third: { agent: 3, thin: 2 } },
    suggestions: [
      { cause: "agent-missed", text: "Agents read token lifetimes from env instead of the config module.", prs: [479, 466] },
      { cause: "requirement-thin", text: "OAuth tickets leave out the error redirect behaviour.", prs: [473] },
    ],
    mix: [
      { type: "architecture", agent: 12, human: 3 },
      { type: "design", agent: 15, human: 4 },
      { type: "dependency", agent: 6, human: 4 },
      { type: "retries", agent: 3, human: 1 },
      { type: "test", agent: 19, human: 5 },
      { type: "scope", agent: 3, human: 8 },
    ],
    tools: [
      { name: "read_file", calls: 910, tokens: 790_000 },
      { name: "replace", calls: 320, tokens: 940_000 },
      { name: "run_shell_command", calls: 260, tokens: 190_000 },
      { name: "grep_search", calls: 210, tokens: 88_000 },
      { name: "write_todos", calls: 48, tokens: 20_000 },
      { name: "write_file", calls: 41, tokens: 61_000 },
    ],
    prs: [
      { n: 479, title: "Rotate refresh tokens on use", area: "auth/tokens", week: 7, agent: "Claude Code", a: 6, h: 2, overrules: 1, attempts: 1.3, flags: [] },
      { n: 473, title: "OAuth error redirects", area: "auth/oauth", week: 6, agent: "Gemini CLI", a: 7, h: 3, overrules: 2, attempts: 1.9, flags: ["unsupported"] },
      { n: 466, title: "Session expiry sliding window", area: "auth/session", week: 5, agent: "Gemini CLI", a: 5, h: 2, overrules: 1, attempts: 1.4, flags: [] },
      { n: 458, title: "Admin impersonation audit log", area: "auth/admin", week: 4, agent: "Claude Code", a: 8, h: 1, overrules: 0, attempts: 1.1, flags: [] },
      { n: 452, title: "PKCE for mobile clients", area: "auth/oauth", week: 3, agent: "Gemini CLI", a: 6, h: 3, overrules: 2, attempts: 1.7, flags: ["new-dependency"] },
    ],
  },
  search: {
    name: "Search",
    kpis: { prs: 17, prsDelta: "−1", attempts: 1.93, attemptsDelta: "+0.31", overrules: 2.1, thin: 28, unsupported: 16 },
    areas: [
      { path: "search/index", attempts: [1.4, 1.6, 1.5, 1.9, 2.2, 2.5, 2.3, 2.6], overrules: [1, 2, 2, 3, 4, 5, 5, 6] },
      { path: "search/query", attempts: [1.2, 1.3, 0, 1.5, 1.4, 1.6, 0, 1.5], overrules: [0, 1, 0, 2, 1, 2, 0, 2] },
      { path: "search/ranking", attempts: [0, 0, 1.8, 2.0, 0, 1.7, 1.9, 0], overrules: [0, 0, 3, 3, 0, 2, 3, 0] },
    ],
    funnel: { total: 48, first: 19, second: { agent: 11, thin: 12 }, third: { agent: 3, thin: 3 } },
    suggestions: [
      { cause: "requirement-thin", text: "Index tickets do not state the reindex strategy. The agent picks one, a human changes it.", prs: [480, 474, 465] },
      { cause: "agent-missed", text: "Agents quarantine flaky tests with a marker instead of fixing the cause.", prs: [474] },
      { cause: "requirement-thin", text: "Ranking changes lack a baseline query set in the brief.", prs: [469] },
    ],
    mix: [
      { type: "architecture", agent: 9, human: 5 },
      { type: "design", agent: 11, human: 6 },
      { type: "dependency", agent: 5, human: 3 },
      { type: "retries", agent: 2, human: 0 },
      { type: "test", agent: 13, human: 7 },
      { type: "scope", agent: 2, human: 9 },
    ],
    tools: [
      { name: "read_file", calls: 620, tokens: 560_000 },
      { name: "replace", calls: 240, tokens: 700_000 },
      { name: "run_shell_command", calls: 190, tokens: 140_000 },
      { name: "grep_search", calls: 170, tokens: 72_000 },
      { name: "write_todos", calls: 31, tokens: 13_000 },
      { name: "write_file", calls: 22, tokens: 33_000 },
    ],
    prs: [
      { n: 480, title: "Reindex on schema change", area: "search/index", week: 7, agent: "Gemini CLI", a: 6, h: 4, overrules: 3, attempts: 2.6, flags: ["unsupported", "skipped-test"] },
      { n: 474, title: "Quarantine flaky query tests", area: "search/query", week: 5, agent: "Gemini CLI", a: 5, h: 3, overrules: 2, attempts: 1.6, flags: ["skipped-test"] },
      { n: 469, title: "Boost exact title matches", area: "search/ranking", week: 6, agent: "Claude Code", a: 7, h: 3, overrules: 3, attempts: 1.9, flags: ["async-gap"] },
      { n: 465, title: "Incremental index shards", area: "search/index", week: 5, agent: "Gemini CLI", a: 8, h: 5, overrules: 5, attempts: 2.5, flags: ["new-dependency", "unsupported"] },
    ],
  },
};

// Same decision, decided differently. Cross-team, so independent of the selector.
export interface Consistency {
  id: string;
  type: DType;
  question: string;
  rows: { team: TeamId; approach: string; prs: number }[];
}
export const consistency: Consistency[] = [
  {
    id: "retries", type: "retries", question: "How do we retry a failed outbound call?",
    rows: [
      { team: "payments", approach: "Exponential, 5 tries, in the client layer", prs: 9 },
      { team: "auth", approach: "Fixed 3 tries, in the caller", prs: 4 },
      { team: "search", approach: "No retry, surface the error", prs: 3 },
    ],
  },
  {
    id: "timeouts", type: "design", question: "What is the default request timeout?",
    rows: [
      { team: "payments", approach: "10 s, set on the shared client", prs: 6 },
      { team: "auth", approach: "30 s, set per call", prs: 5 },
      { team: "search", approach: "5 s, set per call", prs: 4 },
    ],
  },
  {
    id: "flaky", type: "test", question: "What happens to a flaky test?",
    rows: [
      { team: "payments", approach: "Fix the cause. A human rejects any skip", prs: 5 },
      { team: "auth", approach: "Fix the cause", prs: 2 },
      { team: "search", approach: "Quarantine with a marker, fix later", prs: 6 },
    ],
  },
];
