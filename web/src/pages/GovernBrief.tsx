import { AlertTriangle, Info, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import type { HumanKind } from "../data";
import type { Brief, Enforcement, GovCandidate as Candidate, Scope } from "../api";

export const KIND_LABEL: Record<HumanKind, string> = {
  redirect: "Redirect", reject: "Reject", permission_denied: "Permission denied",
  revert: "Revert", requirement: "Requirement", discussion: "Discussion",
};
export const ENF_LABEL = { advice: "Advice", check: "PR check", gate: "Hard gate" } as const;
const SCOPE_LABEL = { repo: "this repo", team: "this team", org: "the whole org" } as const;
const pct = (n: number, d: number) => (d ? Math.round((n / d) * 100) : 0);

/** Numbers the decision and the preview both rely on, derived once. */
export function briefStats(c: Candidate, b: Brief, scope: Scope) {
  const r = b.reach[scope];
  const falsePos = r.flagged - r.confirmed;
  const accepted = b.proposed - c.sessions;
  const early = c.trend.slice(0, 4).reduce((s, v) => s + v, 0);
  const late = c.trend.slice(4).reduce((s, v) => s + v, 0);
  return {
    r, falsePos, accepted,
    overrule: pct(c.sessions, b.proposed),
    precision: pct(r.confirmed, r.flagged),
    early, late,
  };
}

function Metric({ label, value, detail, how, tone }: { label: string; value: ReactNode; detail: ReactNode; how: string; tone?: "ok" | "warn" | "bad" }) {
  return (
    <div className={`gv-metric ${tone ?? ""}`}>
      <span className="gv-label">{label}</span>
      <b>{value}</b>
      <span className="gv-metric-d">{detail}</span>
      <span className="gv-how"><Info size={12} aria-hidden="true" />{how}</span>
    </div>
  );
}

function Weeks({ v }: { v: number[] }) {
  const m = Math.max(...v, 1);
  return (
    <div className="gv-weeks" role="img" aria-label={`Overrides per week, oldest first: ${v.join(", ")}`}>
      {v.map((n, i) => (
        <div key={i} className="gv-week">
          <i style={{ height: `${Math.max(n ? 12 : 3, (n / m) * 100)}%` }} className={i >= v.length - 4 ? "late" : ""} />
          <span>{n}</span>
        </div>
      ))}
    </div>
  );
}

export default function GovernBrief({ c, b, scope, enforcement, onUse }: {
  c: Candidate; b: Brief; scope: Scope; enforcement: Enforcement; onUse: () => void;
}) {
  const s = briefStats(c, b, scope);
  const kinds = Object.entries(c.evidence.reduce<Record<string, number>>((m, e) => ({ ...m, [e.kind]: (m[e.kind] ?? 0) + 1 }), {}));
  const rec = b.recommend;
  const followed = rec.enforcement === enforcement;
  const growth = s.early === 0 ? (s.late > 0 ? "new" : "flat") : s.late > s.early ? `up ${(s.late / s.early).toFixed(1)}×` : s.late < s.early ? "falling" : "flat";

  return (
    <div className="gv-brief">
      <div className="gv-sec-h">
        <span className="gv-label">Decision brief</span>
        <span className="gv-hint">last 8 weeks · PR replay over 90 days · illustrative</span>
      </div>

      <p className="gv-headline">
        The agent made this call in <b>{b.proposed} sessions</b> and humans overruled it in <b>{c.sessions}</b> ({s.overrule}%), across {c.teams} {c.teams === 1 ? "team" : "teams"}.
        {s.accepted > 0 && <> In <b>{s.accepted}</b> more it went through unchallenged, so teams are deciding the same thing differently.</>}
      </p>

      <div className="gv-metrics">
        <Metric label="Override rate" value={`${s.overrule}%`} tone={s.overrule >= 50 ? "bad" : s.overrule >= 30 ? "warn" : undefined}
          detail={`${c.sessions} of ${b.proposed} sessions`} how="Sessions where a human overruled this proposal ÷ sessions where the agent made it." />
        <Metric label="Rework cost" value={`${b.rework.hours} h`} detail={`${b.rework.turns} turns across ${b.rework.prs} PRs`}
          how="Turns that undo or redo the agent's work after an override × a 4.5 min median turn." />
        <Metric label="Check precision" value={`${s.precision}%`} tone={s.precision >= 90 ? "ok" : s.precision >= 75 ? "warn" : "bad"}
          detail={`${s.r.confirmed} of ${s.r.flagged} flagged PRs were real`} how={`Replay over ${s.r.scanned} merged PRs in ${SCOPE_LABEL[scope]}; a reviewer confirmed each hit.`} />
        <Metric label="Reach" value={`${s.r.repos} ${s.r.repos === 1 ? "repo" : "repos"}`} detail={`${s.r.teams} ${s.r.teams === 1 ? "team" : "teams"} · ${s.r.flagged} PRs flagged in 90 days`}
          how="What the rule would touch at the scope you chose below." />
      </div>

      <div className="gv-cols">
        <div className="gv-card">
          <div className="gv-sec-h"><span className="gv-label">Is it growing?</span><span className="gv-hint">{growth} · last 4 vs first 4 weeks</span></div>
          <Weeks v={c.trend} />
          <div className="gv-axis"><span>8 weeks ago</span><span>now</span></div>
        </div>
        <div className="gv-card">
          <div className="gv-sec-h"><span className="gv-label">Same decision, decided differently</span></div>
          <div className="gv-teams">
            {b.teams.map((t) => (
              <div key={t.team} className="gv-team">
                <span>{t.team}<small>{t.developers} dev</small></span>
                <span className="gv-split-bar" role="img" aria-label={`${t.overruled} overruled, ${t.accepted} unchallenged`}>
                  <i className="o" style={{ flex: t.overruled }} /><i className="a" style={{ flex: t.accepted }} />
                </span>
                <span className="gv-nums">{t.overruled} / {t.accepted}</span>
              </div>
            ))}
          </div>
          <div className="gv-legend"><span><i className="o" />overruled</span><span><i className="a" />went through unchallenged</span></div>
        </div>
      </div>

      <div className="gv-cols">
        <div className="gv-card">
          <span className="gv-label">How humans responded</span>
          <div className="gv-tags">{kinds.map(([k, n]) => <span key={k} className="chip human">{KIND_LABEL[k as HumanKind]} {n}</span>)}</div>
          <span className="gv-label">Where it happens</span>
          <ul className="gv-areas">{b.areas.map((a) => <li key={a.area}><span>{a.area}</span><b>{a.n}</b></li>)}</ul>
        </div>
        <div className="gv-card">
          <span className="gv-label">Fit with existing rules</span>
          {b.conflicts.length === 0
            ? <p className="gv-clear">No overlap with the {" "}active policies or skill rules.</p>
            : b.conflicts.map((x) => (
              <div key={x.id} className={`gv-conf ${x.level}`}>
                <AlertTriangle size={15} aria-hidden="true" />
                <p><b>{x.level === "conflict" ? "Conflicts with" : "Overlaps"} {x.id}.</b> {x.note}</p>
              </div>
            ))}
        </div>
      </div>

      <div className={`gv-reco ${rec.action}`}>
        <Sparkles size={16} aria-hidden="true" />
        <div>
          <b>{rec.action === "approve" ? `Recommend: approve as ${ENF_LABEL[rec.enforcement]}` : rec.action === "trial" ? `Recommend: start as ${ENF_LABEL[rec.enforcement]}` : "Recommend: wait"}</b>
          <p>{rec.reason}</p>
        </div>
        {rec.action !== "wait" && <button className="btn sm" onClick={onUse} disabled={followed}>{followed ? "Selected" : `Use ${ENF_LABEL[rec.enforcement]}`}</button>}
      </div>
    </div>
  );
}
