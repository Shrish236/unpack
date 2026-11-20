// Illustrative data for the executive view. Shaped like aggregates over DecisionRecord / OverrideEvent / Policy.
// Aggregates are per agent, area and policy. Nothing here ranks or scores individual developers.
import type { DType, HumanKind } from "./data";

export type Period = "30d" | "90d";

export const WEEKS = 12;
// Monday of the first week shown; the last week ends 2026-11-20.
const START = Date.UTC(2026, 7, 31);
export const weekLabels = Array.from({ length: WEEKS }, (_, i) =>
  new Date(START + i * 7 * 864e5).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }),
);

// % of agent decisions that followed an approved skill rule
export const adherence = [71, 72, 70, 74, 75, 77, 78, 81, 83, 84, 85, 86];
// same human correction recurring, per 100 sessions
export const repeatOverrides = [12, 13, 12, 11, 12, 11, 11, 8, 6, 5, 4, 3];

export const policyEvents = [
  { week: 3, id: "P-09", text: "Retries: exponential backoff, at most 5 attempts" },
  { week: 7, id: "P-12", text: "No new runtime dependency without approval" },
  { week: 10, id: "P-14", text: "Claims must be backed by a test that reaches the code" },
];

export const typeOrder: DType[] = ["architecture", "design", "dependency", "retries", "test", "scope"];
// decisions per week, by type
export const mix: Record<DType, number[]> = {
  architecture: [18, 20, 19, 22, 21, 23, 22, 24, 23, 25, 24, 26],
  design: [14, 15, 15, 16, 17, 16, 18, 17, 18, 19, 18, 20],
  dependency: [20, 22, 21, 19, 20, 19, 18, 12, 9, 7, 6, 5],
  retries: [9, 10, 10, 11, 10, 12, 11, 12, 13, 12, 14, 13],
  test: [24, 26, 25, 27, 28, 27, 29, 28, 30, 31, 30, 32],
  scope: [8, 9, 8, 10, 9, 11, 10, 12, 11, 13, 12, 14],
};
// of those, decided by a human
export const humanPerWeek = [26, 28, 27, 28, 27, 29, 29, 27, 25, 25, 24, 25];

// how human decisions entered the record, % of human decisions
export const humanKinds: { kind: HumanKind; label: string; pct: number }[] = [
  { kind: "redirect", label: "Redirected the agent", pct: 36 },
  { kind: "reject", label: "Rejected a proposal", pct: 28 },
  { kind: "requirement", label: "Added a requirement", pct: 22 },
  { kind: "discussion", label: "Chose in discussion", pct: 9 },
  { kind: "permission_denied", label: "Denied a tool call", pct: 5 },
];

export interface Kpis {
  adherence: { v: number; d: number };
  override: { v: number; before: number };
  verified: { v: number; d: number };
  unrequested: { v: number; d: number };
  pending: { v: number; oldestDays: number };
  sessions: number;
}
export const kpis: Record<Period, Kpis> = {
  "30d": {
    adherence: { v: 86, d: 5 }, override: { v: 3.0, before: 11 }, verified: { v: 78, d: 4 },
    unrequested: { v: 9, d: -2 }, pending: { v: 3, oldestDays: 4 }, sessions: 912,
  },
  "90d": {
    adherence: { v: 81, d: 11 }, override: { v: 5.6, before: 11.8 }, verified: { v: 74, d: 9 },
    unrequested: { v: 11, d: -5 }, pending: { v: 3, oldestDays: 4 }, sessions: 2640,
  },
};

// acceptance criteria by outcome
export const rework: Record<Period, { first: number; missed: number; thin: number }> = {
  "30d": { first: 71, missed: 38, thin: 31 },
  "90d": { first: 214, missed: 131, thin: 97 },
};

export type Autonomy = "advice" | "check" | "gate";
export const agents: {
  name: string; tool: string; decisions: number | null; verified: number | null; unrequested: number | null;
  attempts: number | null; autonomy: Autonomy | null;
}[] = [
  { name: "gemini-3.1-pro-preview", tool: "Gemini CLI", decisions: 1214, verified: 84, unrequested: 6, attempts: 1.5, autonomy: "advice" },
  { name: "gemini-2.5-pro", tool: "Gemini CLI", decisions: 782, verified: 79, unrequested: 9, attempts: 1.7, autonomy: "check" },
  { name: "gemini-3.5-flash", tool: "Gemini CLI", decisions: 436, verified: 63, unrequested: 17, attempts: 2.1, autonomy: "gate" },
  { name: "Claude Code", tool: "adapter on the roadmap", decisions: null, verified: null, unrequested: null, attempts: null, autonomy: null },
];

export const backlog = [
  { id: "C-31", statement: "No new runtime dependency for a few lines of code", sessions: 11, teams: 3, developers: 7, waitingDays: 4 },
  { id: "C-32", statement: "Never skip or delete a failing test", sessions: 8, teams: 2, developers: 5, waitingDays: 2 },
  { id: "C-33", statement: "Async parity required when retrying client code", sessions: 3, teams: 1, developers: 2, waitingDays: 1 },
];

export const expiring = [
  { id: "P-04", statement: "No force-push from agent branches", inDays: 12, owner: "@platform" },
  { id: "P-07", statement: "Log redaction on payment paths", inDays: 25, owner: "@payments" },
];
