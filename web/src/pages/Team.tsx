import { useState } from "react";
import { ArrowRight, ExternalLink } from "lucide-react";
import { Kpi, PageHead, Panel, RepoSelect, Seg, TypeChip, DataGate, useSelectedRepo } from "../ui";
import { type ConsistencyItem, type Flag, type Source, type TeamPage } from "../api";
import { useRepoDashboard } from "../queries";
import { shortDay } from "../format";
import "../styles/team.css";

const FLAG_LABEL: Record<Flag, string> = {
  unsupported: "Unsupported claim",
  "new-dependency": "New dependency",
  "skipped-test": "Skipped test",
  "async-gap": "Untested path",
};

const fmtTok = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : `${Math.round(n / 1e3)}k`);

function TeamBody({ t, consistency, names }: { t: TeamPage; consistency: ConsistencyItem[]; names: Record<string, string> }) {
  const [metric, setMetric] = useState<"attempts" | "overrules">("attempts");
  const [tool, setTool] = useState<"calls" | "tokens">("calls");
  const [sel, setSel] = useState<{ area: string; week: number | null } | null>(null);

  const k = t.kpis;
  const labels = t.weeks.map(shortDay);
  const prs = t.prs.filter((p) => !sel || (p.area === sel.area && (sel.week === null || p.week === sel.week)));
  const maxTool = Math.max(1, ...t.tools.map((x) => x[tool]));
  const maxMix = Math.max(1, ...t.mix.map((m) => m.agent + m.human));
  const f = t.funnel;
  const bar = (n: number) => `${f.total ? (n / f.total) * 100 : 0}%`;
  const second = f.second.agent + f.second.thin;
  const third = f.third.agent + f.third.thin;

  const mixed = Object.values(t.sources).includes("measured");
  // when the page mixes measured and sample sections, each sample one says so
  const src = (s: Source) => (mixed && s === "sample" ? <span className="chip sim">Sample data</span> : undefined);
  const prHref = (p: { public_id?: string | null }) => (p.public_id ? `#/pr/${p.public_id}` : "#/pr");

  const maxAttempts = Math.max(2.6, ...t.areas.flatMap((a) => a.attempts));
  const maxOverrules = Math.max(6, ...t.areas.flatMap((a) => a.overrules));
  const heat = (v: number) => (metric === "attempts" ? Math.min(1, Math.max(0, (v - 1) / Math.max(0.5, maxAttempts - 1))) : Math.min(1, v / maxOverrules));

  return (
    <>
      <section className="kpis" aria-label="Summary">
        <Kpi value={k.prs} label="PRs with agent sessions" sub={<span className="delta up">{k.prs_delta} vs prior 8 wk</span>} />
        <Kpi value={k.attempts.toFixed(2)} label="Attempts per criterion" sub={<span className={`delta ${k.attempts_delta.startsWith("+") ? "down" : "up"}`}>{k.attempts_delta} vs prior 8 wk</span>} />
        <Kpi value={k.overrules.toFixed(1)} label="Human overrules per PR" tone="hot" sub="agent proposals rejected or redirected" />
        <Kpi value={`${k.thin}%`} label="Criteria that were thin" sub="requirement, not the agent" />
        <Kpi value={`${k.unsupported}%`} label="PRs with an unsupported claim" tone="bad" sub="checked against the code graph" />
      </section>

      <Panel
        title="Rework hotspots"
        sub="Click a row or a cell to filter the PR list below"
        aside={<>{src(t.sources.areas)} <Seg value={metric} onChange={setMetric} options={[{ id: "attempts", label: "Attempts" }, { id: "overrules", label: "Overrules" }]} /></>}
      >
        <div className="tm-heat" role="grid" aria-label="Rework by area and week">
          <span />
          {labels.map((w) => <span key={w} className="hd">{w.slice(4)}</span>)}
          {t.areas.map((a) => {
            const vals = metric === "attempts" ? a.attempts : a.overrules;
            return (
              <div key={a.path} style={{ display: "contents" }} role="row">
                <button className={`tm-rowlbl ${sel?.area === a.path && sel.week === null ? "on" : ""}`} title={a.path} onClick={() => setSel(sel?.area === a.path && sel.week === null ? null : { area: a.path, week: null })}><span className="pre">{a.path.split("/")[0]}/</span>{a.path.split("/")[1]}</button>
                {vals.map((v, w) => {
                  const empty = a.attempts[w] === 0;
                  const on = sel?.area === a.path && sel.week === w;
                  return (
                    <button
                      key={w}
                      className={`tm-cell ${empty ? "empty" : ""} ${on ? "on" : ""}`}
                      style={empty ? undefined : { ["--p" as string]: `${Math.round(8 + heat(v) * 62)}%` }}
                      title={empty ? `${a.path}, week of ${labels[w]}: no criteria` : `${a.path}, week of ${labels[w]}: ${metric === "attempts" ? `${v.toFixed(1)} attempts per criterion` : `${v} overrules`}`}
                      onClick={() => setSel(on ? null : { area: a.path, week: w })}
                    >
                      {empty ? "·" : metric === "attempts" ? v.toFixed(1) : v}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
        <div className="tm-scale">{metric === "attempts" ? "1.0" : "0"} <i /> {metric === "attempts" ? `${maxAttempts.toFixed(1)} attempts` : `${maxOverrules} overrules`} <span>· dots mean no sessions that week</span></div>
      </Panel>

      <div className="grid-7-5">
        <Panel title="Criteria quality" sub={t.sources.funnel === "measured" ? "Was it the agent, or the brief? One row per session." : "Was it the agent, or the brief?"} aside={src(t.sources.funnel)}>
          <div className="tm-fun">
            <div className="tm-fr"><span className="lbl">All criteria</span><div className="tm-bar"><span className="all" style={{ width: "100%" }} /></div><b>{f.total}</b></div>
            <div className="tm-fr"><span className="lbl">Met first try</span><div className="tm-bar"><span className="ok" style={{ width: bar(f.first) }} /></div><b>{f.first}</b></div>
            <div className="tm-fr"><span className="lbl">Needed a 2nd attempt</span><div className="tm-bar"><span className="agent" style={{ width: bar(f.second.agent) }} /><span className="thin" style={{ width: bar(f.second.thin) }} /></div><b>{second}</b></div>
            <div className="tm-fr"><span className="lbl">Needed 3 or more</span><div className="tm-bar"><span className="agent" style={{ width: bar(f.third.agent) }} /><span className="thin" style={{ width: bar(f.third.thin) }} /></div><b>{third}</b></div>
          </div>
          <div className="tm-legend">
            <span><i style={{ background: "var(--ok)" }} />Met first try</span>
            <span><i style={{ background: "var(--agent)" }} />Agent missed it</span>
            <span><i style={{ background: "var(--warn)" }} />Requirement was thin</span>
          </div>
          {t.suggestions.length === 0 ? (
            <p className="tm-note">No recurring brief or agent issues detected for this repository yet.</p>
          ) : (
            <ul className="tm-sug">
              {t.suggestions.map((s) => (
                <li key={s.text}>
                  <span className={`chip ${s.cause === "agent-missed" ? "agent" : "warn"}`}>{s.cause === "agent-missed" ? "Agent" : "Brief"}</span>
                  <div>
                    {s.text}
                    <div className="tm-ev">
                      {(s.public_ids ?? []).length > 0
                        ? s.public_ids!.map((pid, idx) => <a key={pid} href={`#/pr/${pid}`}>{s.prs[idx] ? `PR #${s.prs[idx]}` : "View analysis"}</a>)
                        : s.prs.map((n) => <a key={n} href="#/pr">PR #{n}</a>)}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Same decision, decided differently" sub="Across repositories, same decision type">
          {consistency.length === 0 ? (
            <p className="tm-note">No cross-repository decision conflicts recorded yet.</p>
          ) : (
            <div className="tm-cons">
              {consistency.map((c) => (
                <div key={c.id} className="tm-cc">
                  <div className="tm-cc-top"><TypeChip t={c.type} /><span className="panel-sub">{c.rows.reduce((s, r) => s + r.prs, 0)} PRs</span></div>
                  <h3>{c.question}</h3>
                  {c.rows.map((r) => (
                    <div key={r.team} className={`tm-ct ${r.team === t.id ? "me" : ""}`}>
                      <span className="tn">{names[r.team] ?? r.team}</span>
                      <span>{r.approach}</span>
                      <span className="n">{r.prs} PRs</span>
                    </div>
                  ))}
                  <a className="btn sm tm-cta" href="#/govern">Make this a policy <ArrowRight size={14} /></a>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="Decision mix" sub={`${t.mix.reduce((s, m) => s + m.agent + m.human, 0)} decisions · agent vs human`} aside={src(t.sources.mix)}>
          <div className="tm-mix">
            {t.mix.map((m) => (
              <div className="tm-mr" key={m.type}>
                <TypeChip t={m.type} />
                <div className="tm-split" style={{ width: `${((m.agent + m.human) / maxMix) * 100}%` }} title={`${m.agent} agent, ${m.human} human`}>
                  <span className="a" style={{ flex: m.agent }} /><span className="h" style={{ flex: m.human }} />
                </div>
                <b>{m.agent}/{m.human}</b>
              </div>
            ))}
          </div>
          <div className="tm-legend">
            <span><i style={{ background: "var(--agent)" }} />Agent decided</span>
            <span><i style={{ background: "var(--human)" }} />Human decided</span>
          </div>
        </Panel>

        <Panel title="Where the agent spends effort" sub="Tool use across the team's agents" aside={<>{src(t.sources.tools)} <Seg value={tool} onChange={setTool} options={[{ id: "calls", label: "Calls" }, { id: "tokens", label: "Tokens" }]} /></>}>
          {t.tools.map((x) => (
            <div className="tm-tool" key={x.name}>
              <span>{x.name}</span>
              <span className="tm-track"><i style={{ width: `${(x[tool] / maxTool) * 100}%` }} /></span>
              <b>{tool === "tokens" ? fmtTok(x.tokens) : x.calls.toLocaleString()}</b>
            </div>
          ))}
          {t.sources.tools === "sample" && <p className="tm-note">Token counts are illustrative until the hook keeps them.</p>}
        </Panel>
      </div>

      <Panel
        title="Recent PRs"
        sub={`${prs.length} of ${t.prs.length}`}
        aside={sel && (
          <div className="tm-filter">
            <span className="chip human">{sel.area}{sel.week !== null && ` · wk ${labels[sel.week]}`}</span>
            <button className="tm-clear" onClick={() => setSel(null)}>Clear</button>
          </div>
        )}
      >
        <div className="tm-scroll">
          <table className="table tm-table">
            <thead><tr><th>PR / Commit</th><th>Agent</th><th>Decisions</th><th>Overrules</th><th>Attempts</th><th>Flags</th><th /></tr></thead>
            <tbody>
              {prs.length === 0 && <tr><td colSpan={7} className="tm-none">No PRs for that selection.</td></tr>}
              {prs.map((p) => {
                const ghUrl = p.pr_url ?? p.commit_url;
                return (
                  <tr key={p.public_id ?? p.number ?? p.title} onClick={() => { location.hash = prHref(p); }}>
                    <td>
                      <span className="num">{p.number != null ? `#${p.number}` : (p.short_sha ?? "push")}</span>
                      {p.source === "measured" && <span className="chip ok" style={{ marginRight: 6 }}>Measured</span>}
                      <a href={prHref(p)} onClick={(e) => e.stopPropagation()}>{p.title}</a>
                      <span className="ar">{p.area}</span>
                    </td>
                    <td>{p.agent}</td>
                    <td>
                      <div className="tm-dm">
                        <div className="tm-split"><span className="a" style={{ flex: p.agent_decisions }} /><span className="h" style={{ flex: p.human_decisions }} /></div>
                        {p.agent_decisions}/{p.human_decisions}
                      </div>
                    </td>
                    <td className="mono">{p.overrules}</td>
                    <td className="mono">{p.attempts.toFixed(2)}</td>
                    <td>
                      {p.flags.length === 0 ? <span className="tm-none">none</span> : (
                        <div className="tm-flags">{p.flags.map((fl) => <span key={fl} className={`chip ${fl === "unsupported" ? "bad" : "warn"}`}>{FLAG_LABEL[fl]}</span>)}</div>
                      )}
                    </td>
                    <td>
                      {ghUrl && (
                        <a className="btn sm" href={ghUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>
                          {p.pr_url ? "View PR" : "View PR"} <ExternalLink size={12} />
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

export default function Team() {
  const { repos, repo, setRepo } = useSelectedRepo();
  const q = useRepoDashboard(repo);
  const displayName = q.data?.full_name ?? repo;
  return (
    <main className="wrap page tm">
      <PageHead
        crumbs={<>Org <b>›</b> Repositories <b>›</b> <span>{displayName}</span></>}
        title={q.data?.name ?? repo}
        sub="Where rework piles up, whether the agent or the brief caused it, and recent agent sessions for this repository."
        meta={<>
          <RepoSelect repos={repos} value={repo} onChange={setRepo} />
          <span className="chip">Last 8 weeks</span>
          {q.data && (Object.values(q.data.sources).every((s) => s === "measured")
            ? <span className="chip ok">Measured</span>
            : Object.values(q.data.sources).includes("measured")
              ? <span className="chip warn" title="Sections marked Sample data have no measured source yet">Partly measured</span>
              : <span className="chip sim">Illustrative data</span>)}
        </>}
      />
      <DataGate q={q}>
        {(t) => <TeamBody key={t.id} t={t} consistency={t.consistency ?? []} names={{}} />}
      </DataGate>
    </main>
  );
}
