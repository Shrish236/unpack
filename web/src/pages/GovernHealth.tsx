import { AlertTriangle, Check, Clock3, Volume2 } from "lucide-react";
import { Panel } from "../ui";
import { TYPE_LABEL } from "../data";
import { TODAY, type ActivePolicy, type Enforcement } from "../data.govern";

export type Issue = "overridden" | "noisy" | "expiring";
const ISSUE_LABEL: Record<Issue, string> = { overridden: "Still overridden", noisy: "Noisy check", expiring: "Expiring soon" };
const ENF = { advice: "Advice", check: "PR check", gate: "Hard gate" } as const;
export const STEP_DOWN: Record<Enforcement, Enforcement | null> = { gate: "check", check: "advice", advice: null };

export const daysLeft = (d: string) => Math.round((Date.parse(d) - Date.parse(TODAY)) / 864e5);
const fmt = (d: string) => new Date(d).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
export const noiseOf = (p: ActivePolicy) => (p.checks && p.checks.flagged ? p.checks.wrong / p.checks.flagged : 0);

/** Why a policy needs a person. Thresholds are the same ones the KPI strip uses. */
export function issuesOf(p: ActivePolicy): Issue[] {
  const out: Issue[] = [];
  if (p.after !== null && p.after >= p.before * 0.6) out.push("overridden");
  if (noiseOf(p) > 0.2) out.push("noisy");
  if (daysLeft(p.expires) <= 45) out.push("expiring");
  return out;
}
export const reachedTarget = (p: ActivePolicy) => p.after !== null && p.target !== undefined && p.after <= p.target;

function Trend({ v, target }: { v: number[]; target?: number }) {
  const w = 160, h = 44, m = Math.max(...v, target ?? 0, 1);
  const y = (n: number) => (h - 4 - (n / m) * (h - 8)).toFixed(1);
  const pts = v.map((n, i) => `${((i / (v.length - 1)) * w).toFixed(1)},${y(n)}`).join(" ");
  return (
    <svg className="gh-trend" width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`Overrides per 100 sessions since approval: ${v.join(", ")}`}>
      {target !== undefined && <line x1="0" x2={w} y1={y(target)} y2={y(target)} stroke="var(--ok)" strokeDasharray="3 3" strokeWidth="1" />}
      <polyline points={pts} fill="none" stroke="var(--human-text)" strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export default function PolicyHealth({ actives, onRevise, onRetire, onRenew, onRelax }: {
  actives: ActivePolicy[];
  onRevise: (p: ActivePolicy) => void;
  onRetire: (p: ActivePolicy) => void;
  onRenew: (p: ActivePolicy) => void;
  onRelax: (p: ActivePolicy) => void;
}) {
  const flagged = actives.filter((p) => issuesOf(p).length);
  const healthy = actives.filter((p) => !issuesOf(p).length);

  return (
    <Panel title={`Needs attention · ${flagged.length}`} sub="A policy is only useful if overrides fall and reviewers trust the check. These are not doing that yet."
      aside={<span className="chip sim">Illustrative data</span>}>
      {flagged.length === 0 && <div className="gv-empty"><Check size={20} /><b>Every policy is working</b><span>Overrides are falling, checks are accurate and nothing expires soon.</span></div>}
      <div className="gh-list">
        {flagged.map((p) => {
          const issues = issuesOf(p), left = daysLeft(p.expires), noise = noiseOf(p), next = STEP_DOWN[p.enforcement];
          const span = p.before - (p.target ?? 0);
          const progress = p.after === null || span <= 0 ? 0 : Math.max(0, Math.min(100, Math.round(((p.before - p.after) / span) * 100)));
          return (
            <article key={p.id} className={`gh-card ${issues.includes("overridden") || issues.includes("noisy") ? "hot" : ""}`}>
              <header>
                <div>
                  <b className="gh-t">{p.statement}</b>
                  <span className="gv-cell-s">{p.id} · {TYPE_LABEL[p.type]} · {ENF[p.enforcement]} · {p.scopeName} · {p.owner}{p.approved && <> · approved {fmt(p.approved)}</>}</span>
                </div>
                <div className="gh-chips">{issues.map((i) => <span key={i} className={`chip ${i === "expiring" ? "" : "warn"}`}>{ISSUE_LABEL[i]}</span>)}</div>
              </header>

              <div className="gh-grid">
                <div className="gh-m">
                  <span className="gv-label">Overrides per 100 sessions</span>
                  <b>{p.before} → {p.after ?? "…"}</b>
                  <span className="gh-prog" role="img" aria-label={`${progress}% of the way to the target`}><i style={{ width: `${progress}%` }} /></span>
                  <span className="gv-hint">{p.target !== undefined ? <>target ≤ {p.target} · {progress}% of the way</> : "no target set"}</span>
                </div>
                <div className="gh-m">
                  <span className="gv-label">Adherence</span>
                  <b>{p.adherence === null ? "…" : `${p.adherence}%`}</b>
                  <span className="gv-hint">agent decisions that followed the rule</span>
                </div>
                <div className="gh-m">
                  <span className="gv-label">Check accuracy</span>
                  {p.checks ? <><b className={noise > 0.2 ? "bad" : ""}>{Math.round((1 - noise) * 100)}%</b><span className="gv-hint">reviewers overrode {p.checks.wrong} of {p.checks.flagged} flagged PRs</span></>
                    : <><b>n/a</b><span className="gv-hint">advice only, nothing to override</span></>}
                </div>
                <div className="gh-m">
                  <span className="gv-label">Since approval</span>
                  {p.weekly ? <Trend v={p.weekly} target={p.target} /> : <b>…</b>}
                  <span className="gv-hint">{p.weekly ? `${p.weekly.length} weeks · dashed = target` : "still measuring"}</span>
                </div>
              </div>

              <ul className="gh-why">
                {issues.includes("overridden") && <li><AlertTriangle size={14} aria-hidden="true" />
                  <span>Overrides fell from {p.before} to {p.after} but are still {Math.round(((p.after ?? 0) / p.before) * 100)}% of where they started.{" "}
                    {p.recurrence ? <>{p.recurrence.sessions} sessions across {p.recurrence.teams} teams repeated the override since, so the wording probably misses the real case.</> : <>Revise the wording or retire it.</>}</span></li>}
                {issues.includes("noisy") && <li><Volume2 size={14} aria-hidden="true" />
                  <span>Reviewers overrode {Math.round(noise * 100)}% of the PRs this check flagged. A rule that is wrong this often teaches people to ignore it.{next ? <> Relax it to {ENF[next]} or tighten the match.</> : " Tighten the match."}</span></li>}
                {issues.includes("expiring") && <li><Clock3 size={14} aria-hidden="true" />
                  <span>Expires {fmt(p.expires)}, in {left} days. It is {reachedTarget(p) ? "meeting" : "not yet meeting"} its target, so renew it or let it lapse.</span></li>}
              </ul>

              <div className="gv-row-actions">
                {p.recurrence && issues.includes("overridden") && <button className="btn sm" onClick={() => onRevise(p)}>Revise wording</button>}
                {issues.includes("noisy") && next && <button className="btn sm" onClick={() => onRelax(p)}>Relax to {ENF[next]}</button>}
                {issues.includes("expiring") && <button className="btn sm" onClick={() => onRenew(p)}>Renew 6 months</button>}
                <button className="btn sm danger" onClick={() => onRetire(p)}>Retire</button>
              </div>
            </article>
          );
        })}
      </div>
      {healthy.length > 0 && (
        <p className="gh-ok"><Check size={14} aria-hidden="true" /><span><b>Working:</b> {healthy.map((p) => `${p.id}${p.after === null ? " (measuring)" : ""}`).join(", ")}</span></p>
      )}
    </Panel>
  );
}
