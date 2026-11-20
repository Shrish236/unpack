import { useEffect, useRef, useState } from "react";
import { BookOpen, Check, FileText, Share2, ShieldCheck } from "lucide-react";
import { DataGate, Kpi, PageHead, Panel, Seg, TypeChip } from "../ui";
import { TYPE_LABEL, type DType, type HumanKind } from "../data";
import {
  approveCandidate, rejectCandidate, retirePolicy, revisePolicy,
  type ApproveBody, type Enforcement, type GovCandidate, type GovEvidence, type GovernanceState, type GovPolicy, type Scope,
} from "../api";
import { useGovernance, useGovernanceAction } from "../queries";
import { longDay, shortDay } from "../format";
import "../styles/govern.css";

type Tab = "candidates" | "active" | "skills" | "history";
interface Draft { statement: string; scope: Scope; enforcement: Enforcement; owner: string; expires: string }

const KIND: Record<HumanKind, string> = {
  redirect: "Redirect", reject: "Reject", permission_denied: "Permission denied",
  revert: "Revert", requirement: "Requirement", discussion: "Discussion",
};
const HEADING: Record<DType, string> = {
  architecture: "Architecture", design: "Design", dependency: "Dependencies", retries: "Retries", test: "Tests", scope: "Scope",
};
const ENF = { advice: "Advice", check: "PR check", gate: "Hard gate" } as const;
const ON_VIOLATION = { advice: "comment on the PR", check: "fail the PR check", gate: "block the merge" } as const;
const OWNERS = ["@platform", "@quality", "@api-guild", "@security"];

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);

function Spark({ v, w = 72, h = 22 }: { v: number[]; w?: number; h?: number }) {
  const m = Math.max(...v, 1);
  const pts = v.map((y, i) => `${((i / (v.length - 1)) * w).toFixed(1)},${(h - 2 - (y / m) * (h - 4)).toFixed(1)}`).join(" ");
  return (
    <svg className="gv-spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function EvidenceCard({ e }: { e: GovEvidence }) {
  return (
    <div className="gv-ev">
      <div className="gv-ev-h">
        <span className="chip human">{KIND[e.kind]}</span>
        <a href="#/pr">PR {e.pr}</a><span>{e.session}</span><span>T{e.turn}</span><span>{e.team}</span><span>{e.dev}</span>
        <span className="gv-when">{shortDay(e.when)}</span>
      </div>
      <div className="gv-pair">
        <div className="a"><small>Agent proposed</small>{e.proposal}</div>
        <div className="h"><small>Human chose</small>{e.choice}</div>
      </div>
      <blockquote className="gv-quote">“{e.quote}”</blockquote>
    </div>
  );
}

export default function Govern() {
  const q = useGovernance();
  return (
    <main className="wrap page">
      <DataGate q={q}>{(g) => <GovernanceView g={g} />}</DataGate>
    </main>
  );
}

function GovernanceView({ g }: { g: GovernanceState }) {
  const approveM = useGovernanceAction((a: { id: string; body: ApproveBody }) => approveCandidate(a.id, a.body));
  const rejectM = useGovernanceAction((a: { id: string; reason: string }) => rejectCandidate(a.id, a.reason));
  const retireM = useGovernanceAction((id: string) => retirePolicy(id));
  const reviseM = useGovernanceAction((id: string) => revisePolicy(id));
  const busy = approveM.isPending || rejectM.isPending || retireM.isPending || reviseM.isPending;

  const [tab, setTab] = useState<Tab>("candidates");
  const [sel, setSel] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [minS, setMinS] = useState(3);
  const [minD, setMinD] = useState(2);
  const [toast, setToast] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const detail = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 3800);
    return () => clearTimeout(t);
  }, [toast]);

  const { candidates: cands, policies: actives, history: hist, rules, today } = g;
  const meets = (c: GovCandidate) => c.sessions >= minS && c.developers >= minD;
  // the server orders candidates by developers, then sessions: strongest evidence first
  const c = cands.find((x) => x.id === sel) ?? cands[0];
  const ready = cands.filter(meets).length;

  const draftOf = (x: GovCandidate): Draft => drafts[x.id] ?? { statement: x.statement, scope: x.scope, enforcement: x.enforcement, owner: x.owner, expires: x.expires };
  const patch = (x: GovCandidate, p: Partial<Draft>) => setDrafts((ds) => ({ ...ds, [x.id]: { ...draftOf(x), ...p } }));
  const dropDraft = (id: string) => setDrafts((ds) => Object.fromEntries(Object.entries(ds).filter(([k]) => k !== id)));

  const pick = (id: string) => {
    setSel(id); setRejecting(false); setEditing(false); setShowAll(false); setReason("");
    if (matchMedia("(max-width: 960px)").matches) setTimeout(() => detail.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };
  // after a decision the candidate leaves the inbox; with no selection the view falls back to the first one
  const settle = () => { setSel(null); setRejecting(false); setEditing(false); setShowAll(false); setReason(""); };
  const fail = (e: Error) => setToast(e.message);

  const approve = (x: GovCandidate) => {
    const d = draftOf(x);
    approveM.mutate({
      id: x.id,
      body: { statement: d.statement, scope: d.scope, enforcement: d.enforcement, owner: d.owner, expires: d.expires },
    }, {
      onSuccess: () => {
        dropDraft(x.id); settle();
        setToast(`${x.pid} approved. Published to AGENTS.md${d.enforcement === "advice" ? "" : " and the PR check"}.`);
      },
      onError: fail,
    });
  };
  const reject = (x: GovCandidate) => {
    rejectM.mutate({ id: x.id, reason }, {
      onSuccess: () => { dropDraft(x.id); settle(); setToast(`${x.pid} rejected and moved to history.`); },
      onError: fail,
    });
  };
  const retire = (p: GovPolicy) => retireM.mutate(p.id, { onSuccess: () => setToast(`${p.id} retired.`), onError: fail });
  const revise = (p: GovPolicy) => reviseM.mutate(p.id, {
    onSuccess: () => {
      settle(); setTab("candidates"); setSel(`c-${p.id}`);
      setToast(`${p.id} reopened as a candidate. Edit the statement and approve to replace it.`);
    },
    onError: fail,
  });

  const stillHappening = (p: GovPolicy) => p.after !== null && p.after >= p.before * 0.6;
  const measured = actives.filter((a) => a.adherence !== null);
  const avgAdherence = Math.round(measured.reduce((s, a) => s + a.adherence!, 0) / Math.max(1, measured.length));
  const overridden = actives.filter(stillHappening).length;
  const daysLeft = (d: string) => Math.round((Date.parse(d) - Date.parse(today)) / 864e5);

  const d = c ? draftOf(c) : null;
  const agentsMd = c && d ? `## ${HEADING[c.type]}\n- ${d.statement}\n  <!-- ${c.pid} · scope: ${d.scope} · owner: ${d.owner} · expires: ${d.expires} -->` : "";
  const prRule = c && d ? `rule: ${slug(d.statement)}\nwhen: ${c.match}\nscope: ${d.scope}\nenforcement: ${d.enforcement}\non_violation: ${ON_VIOLATION[d.enforcement]}\nexpires: ${d.expires}` : "";
  const evidence = c ? (showAll ? c.evidence : c.evidence.slice(0, 3)) : [];

  return (
    <>
      <PageHead
        crumbs={<>Company <b>›</b> <span>Governance</span></>}
        title="Governance inbox"
        sub="Approved decisions are added back to your agents' skills and context, so every agent improves over time. You decide what counts as a rule."
        meta={<><span className="chip sim">Illustrative data</span><span className="chip">Candidate = same override, ≥ {minS} sessions, ≥ {minD} developers</span></>}
      />

      <section className="kpis" aria-label="Summary">
        <Kpi value={ready} label="ready for review" sub={`${cands.length} candidates in the inbox`} tone="hot" />
        <Kpi value={actives.length} label="active policies" sub={`${actives.filter((a) => a.enforcement !== "advice").length} enforced in PRs`} />
        <Kpi value={`${avgAdherence}%`} label="average adherence" sub="agent decisions that followed the rule" tone="ok" />
        <Kpi value={overridden} label="still being overridden" sub="revise or retire" tone={overridden ? "bad" : undefined} />
      </section>

      <section className="gv-pub" aria-label="Published to">
        <div><FileText size={18} /><p><b>AGENTS.md</b><span>{actives.length} rules · repo root</span></p></div>
        <div><BookOpen size={18} /><p><b>Skill files</b><span>skills/*.md · {new Set(actives.map((a) => a.type)).size} files</span></p></div>
        <div><ShieldCheck size={18} /><p><b>PR check</b><span>{actives.filter((a) => a.enforcement !== "advice").length} checks · {actives.filter((a) => a.enforcement === "gate").length} gates</span></p></div>
        <div><Share2 size={18} /><p><b>Exports</b><span>Copilot memory · Qodo rules · any agent</span></p></div>
      </section>

      <div className="gv-tabs">
        <Seg<Tab> value={tab} onChange={setTab} options={[
          { id: "candidates", label: `Candidates ${cands.length}` }, { id: "active", label: `Active ${actives.length}` },
          { id: "skills", label: `Agent vs skills ${rules.length}` }, { id: "history", label: `History ${hist.length}` },
        ]} />
        <span className="gv-flow">Human overrides <b>→</b> candidate <b>→</b> you approve <b>→</b> agents read it <b>→</b> overrides drop</span>
      </div>

      {tab === "candidates" && (!c ? (
        <Panel><div className="gv-empty"><Check size={20} /><b>Inbox clear</b><span>New candidates appear when the same override repeats across sessions.</span></div></Panel>
      ) : (
        <div className="gv-split">
          <div className="gv-list" role="list" aria-label="Policy candidates">
            {cands.map((x) => (
              <button key={x.id} className={`gv-item t-${x.type}`} aria-pressed={x.id === c.id} onClick={() => pick(x.id)}>
                <span className="gv-item-t">{x.statement}</span>
                <span className="gv-item-m">
                  <TypeChip t={x.type} />
                  <span>{x.sessions} sessions · {x.teams} {x.teams === 1 ? "team" : "teams"} · {x.developers} dev</span>
                  <Spark v={x.trend} />
                </span>
                <span className="gv-item-m">
                  {meets(x) ? <span className="chip ok">Meets threshold</span> : <span className="chip warn">Preference · below threshold</span>}
                  <span>{x.pid}</span>
                </span>
              </button>
            ))}
          </div>

          <div ref={detail} className={`panel gv-detail t-${c.type}`} aria-label="Candidate detail">
            <div className="gv-sec">
              <div className="gv-chips"><TypeChip t={c.type} /><span className="chip">Proposed</span><span className="chip mono">{c.pid}</span>{c.source === "measured" && <span className="chip ok">From your sessions</span>}</div>
              <h3>{c.statement}</h3>
              <div className="gv-stats">
                <div className="gv-stat"><b>{c.sessions}</b><span>sessions</span></div>
                <div className="gv-stat"><b>{c.teams}</b><span>{c.teams === 1 ? "team" : "teams"}</span></div>
                <div className="gv-stat"><b>{c.developers}</b><span>developers</span></div>
                <Spark v={c.trend} w={96} h={30} />
              </div>
            </div>

            <div className={`gv-rule ${meets(c) ? "ok" : "low"}`}>
              <div><b>{meets(c) ? "This is a candidate." : "This is still a preference."}</b>{" "}
                One developer overriding is a preference. The same override from several developers is a candidate.</div>
              <div className="gv-th">
                <label>sessions ≥ <input type="number" min={1} max={20} value={minS} onChange={(e) => setMinS(Math.max(1, +e.target.value || 1))} /></label>
                <label>developers ≥ <input type="number" min={1} max={20} value={minD} onChange={(e) => setMinD(Math.max(1, +e.target.value || 1))} /></label>
                <span className="gv-hint">threshold is configurable</span>
              </div>
            </div>

            <div className="gv-sec">
              <div className="gv-sec-h">
                <span className="gv-label">Evidence · human overrides</span>
                <span className="gv-hint">{evidence.length} of {c.sessions} sessions shown · quotes stay behind login</span>
              </div>
              {evidence.map((e) => <EvidenceCard key={e.id} e={e} />)}
              {c.evidence.length > 3 && <button className="gv-more" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${c.evidence.length}`}</button>}
            </div>

            <div className="gv-sec">
              <span className="gv-label">Your decision</span>
              <div className="gv-form">
                <div className="gv-field wide">
                  <div className="gv-statement">
                    {editing
                      ? <textarea className="gv-text" aria-label="Policy statement" value={d!.statement} onChange={(e) => patch(c, { statement: e.target.value })} />
                      : <span>{d!.statement}</span>}
                    <button className="gv-link" onClick={() => setEditing(!editing)}>{editing ? "Done" : "Edit statement"}</button>
                  </div>
                </div>
                <div className="gv-field"><span className="gv-label">Scope</span>
                  <Seg<Scope> value={d!.scope} onChange={(v) => patch(c, { scope: v })} options={[{ id: "repo", label: "Repo" }, { id: "team", label: "Team" }, { id: "org", label: "Org" }]} /></div>
                <div className="gv-field"><span className="gv-label">Enforcement</span>
                  <Seg<Enforcement> value={d!.enforcement} onChange={(v) => patch(c, { enforcement: v })} options={[{ id: "advice", label: "Advice" }, { id: "check", label: "PR check" }, { id: "gate", label: "Hard gate" }]} /></div>
                <label className="gv-field"><span className="gv-label">Owner</span>
                  <select className="gv-select" value={d!.owner} onChange={(e) => patch(c, { owner: e.target.value })}>{OWNERS.map((o) => <option key={o}>{o}</option>)}</select></label>
                <label className="gv-field"><span className="gv-label">Expires</span>
                  <input className="gv-input" type="date" value={d!.expires} min={today} onChange={(e) => patch(c, { expires: e.target.value })} /></label>
              </div>
              {rejecting ? (
                <div className="gv-field">
                  <span className="gv-label">Why reject? Saved to history</span>
                  <textarea className="gv-text" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="One team's preference, covered by the linter…" />
                  <div className="gv-actions"><button className="btn danger" disabled={busy} onClick={() => reject(c)}>Reject candidate</button><button className="btn" onClick={() => setRejecting(false)}>Cancel</button></div>
                </div>
              ) : (
                <div className="gv-actions">
                  <button className="btn ok" disabled={!meets(c) || busy} onClick={() => approve(c)}><Check size={16} /> Approve and publish</button>
                  <button className="btn" disabled={busy} onClick={() => setRejecting(true)}>Reject</button>
                  {!meets(c) && <span className="gv-hint">Below threshold: keep watching, or lower it above.</span>}
                </div>
              )}
            </div>

            <div className="gv-out">
              <div className="gv-sec-h"><span className="gv-label">Published on approve</span><span className="gv-hint">updates as you edit</span></div>
              <div><div className="gv-hint">AGENTS.md / skills/{c.type === "dependency" ? "dependencies" : c.type}.md</div><pre className="gv-code">{agentsMd}</pre></div>
              <div><div className="gv-hint">PR rule · {d!.enforcement === "advice" ? "advice only, no check created" : d!.enforcement === "check" ? "fails the PR check" : "blocks the merge"}</div><pre className="gv-code">{prRule}</pre></div>
            </div>
          </div>
        </div>
      ))}

      {tab === "active" && (
        <Panel title="Active policies" sub="Adherence is measured on agent decisions. Overrides are per 100 sessions."
          aside={<span className="chip sim">Illustrative data</span>}>
          <div className="gv-scroll">
            <table className="table">
              <thead><tr><th>Policy</th><th>Scope</th><th>Enforcement</th><th>Owner</th><th>Expires</th><th>Adherence</th><th>Overrides</th><th /></tr></thead>
              <tbody>
                {actives.map((p) => {
                  const left = daysLeft(p.expires);
                  const again = stillHappening(p);
                  return (
                    <tr key={p.id}>
                      <td><div className="gv-cell-t">{p.statement}</div><div className="gv-cell-s">{p.id} · {TYPE_LABEL[p.type]}</div></td>
                      <td><span className="chip">{p.scope}</span> <span className="gv-cell-s">{p.scope_name}</span></td>
                      <td><span className={`chip ${p.enforcement === "gate" ? "bad" : p.enforcement === "check" ? "agent" : ""}`}>{ENF[p.enforcement]}</span></td>
                      <td className="gv-nums">{p.owner}</td>
                      <td className={left <= 45 ? "gv-soon" : "gv-nums"}>{longDay(p.expires)}{left <= 45 && <div className="gv-cell-s">in {left} days</div>}</td>
                      <td>{p.adherence === null ? <span className="gv-cell-s">Measuring</span> : (
                        <div className="gv-pair-bars"><span className="gv-nums">{p.adherence}%</span>
                          <span className={`gv-bar ad ${p.adherence < 60 ? "bad" : p.adherence < 80 ? "low" : ""}`}><i style={{ width: `${p.adherence}%` }} /></span></div>)}</td>
                      <td>{p.after === null ? <span className="gv-cell-s">{p.before} before</span> : (
                        <div className="gv-pair-bars">
                          <span className="gv-nums">{p.before} → {p.after}</span>
                          <span className="gv-bar before"><i style={{ width: `${Math.min(100, p.before * 5)}%` }} /></span>
                          <span className="gv-bar after"><i style={{ width: `${Math.min(100, p.after * 5)}%` }} /></span>
                        </div>)}</td>
                      <td>{again && <div className="gv-row-actions">
                        <span className="chip warn">Still overridden</span>
                        {p.recurrence && <button className="btn sm" disabled={busy} onClick={() => revise(p)}>Revise</button>}
                        <button className="btn sm danger" disabled={busy} onClick={() => retire(p)}>Retire</button></div>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {tab === "skills" && (
        <Panel title="Agent decisions against skill rules" sub="Per rule, never per person. Last 8 weeks."
          aside={<span className="chip sim">Illustrative data</span>}>
          <div className="gv-scroll">
            <table className="table">
              <thead><tr><th>Rule</th><th>Followed</th><th>Violated</th><th>Adherence</th><th>Violations / week</th><th>Latest violation</th></tr></thead>
              <tbody>
                {[...rules].sort((a, b) => b.violated / (b.followed + b.violated) - a.violated / (a.followed + a.violated)).map((r) => {
                  const pct = Math.round((r.followed / (r.followed + r.violated)) * 100);
                  return (
                    <tr key={r.id}>
                      <td><div className="gv-cell-t">{r.text}{r.source === "measured" && <span className="chip ok" style={{ marginLeft: 8 }}>Measured</span>}</div><div className="gv-cell-s">{r.skill}</div></td>
                      <td className="gv-nums">{r.followed}</td><td className="gv-nums">{r.violated}</td>
                      <td><div className="gv-pair-bars"><span className="gv-nums">{pct}%</span><span className={`gv-bar ad ${pct < 75 ? "bad" : pct < 90 ? "low" : ""}`}><i style={{ width: `${pct}%` }} /></span></div></td>
                      <td><Spark v={r.trend} /></td>
                      <td><a className="gv-link" href="#/pr">PR {r.latest_pr} · T{r.latest_turn}</a></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {tab === "history" && (
        <Panel title="History" sub="Roles, not names." aside={<span className="chip sim">Illustrative data</span>}>
          <div className="gv-hist">
            {hist.map((h) => (
              <div key={h.id}>
                <span className={`chip ${h.outcome === "approved" ? "ok" : h.outcome === "rejected" ? "bad" : ""}`}>{h.outcome}</span>
                <div><b>{h.statement}</b><p>{h.why}</p></div>
                <div className="gv-cell-s">{h.role}<br />{longDay(h.when)}</div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {toast && <div className="gv-toast" role="status"><Check size={16} />{toast}</div>}
    </>
  );
}
