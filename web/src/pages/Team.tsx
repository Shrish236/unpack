import { useState } from "react";
import { Kpi, PageHead, Panel, RepoSelect, Seg, TypeChip, DataGate, useSelectedRepo } from "../ui";
import { type Source, type TeamPage } from "../api";
import { useRepoDashboard } from "../queries";
import { shortDay } from "../format";
import "../styles/team.css";

const fmtTok = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : `${Math.round(n / 1e3)}k`);

// The team page: where rework piles up, whether the agent or the brief caused it, and how the team's agents work.
// Individual PRs live on the PR analyses page, so this page links to them only where a finding needs it.
function TeamBody({ t }: { t: TeamPage }) {
  const [metric, setMetric] = useState<"attempts" | "overrules">("attempts");
  const [tool, setTool] = useState<"calls" | "tokens">("calls");

  const k = t.kpis;
  // the heatmap shows the last four weeks only; the weeks before were mostly empty
  const from = Math.max(0, t.weeks.length - 4);
  const labels = t.weeks.slice(from).map(shortDay);
  const maxTool = Math.max(1, ...t.tools.map((x) => x[tool]));
  const maxMix = Math.max(1, ...t.mix.map((m) => m.agent + m.human));
  const f = t.funnel;
  const bar = (n: number) => `${f.total ? (n / f.total) * 100 : 0}%`;
  const second = f.second.agent + f.second.thin;
  const third = f.third.agent + f.third.thin;

  const mixed = Object.values(t.sources).includes("measured");
  // when the page mixes measured and sample sections, each sample one says so
  const src = (s: Source) => (mixed && s === "sample" ? <span className="chip sim">Sample data</span> : undefined);

  const maxAttempts = Math.max(2.6, ...t.areas.flatMap((a) => a.attempts));
  const maxOverrules = Math.max(6, ...t.areas.flatMap((a) => a.overrules));
  const heat = (v: number) => (metric === "attempts" ? Math.min(1, Math.max(0, (v - 1) / Math.max(0.5, maxAttempts - 1))) : Math.min(1, v / maxOverrules));

  // where rework concentrates: each area's human overrules across all the weeks, most first, with its average attempts per criterion
  const ranked = t.areas
    .map((a) => {
      const withCriteria = a.attempts.filter((v) => v > 0);
      return {
        path: a.path,
        overrules: a.overrules.reduce((s, v) => s + v, 0),
        attempts: withCriteria.length ? withCriteria.reduce((s, v) => s + v, 0) / withCriteria.length : null,
      };
    })
    .sort((x, y) => y.overrules - x.overrules || (y.attempts ?? 0) - (x.attempts ?? 0));
  const maxRank = Math.max(1, ...ranked.map((r) => r.overrules));

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
        title="Rework by area"
        sub={`${metric === "attempts" ? "Attempts per criterion" : "Human overrules"}, by area and week`}
        aside={<>{src(t.sources.areas)} <Seg value={metric} onChange={setMetric} options={[{ id: "attempts", label: "Attempts" }, { id: "overrules", label: "Overrules" }]} /></>}
      >
        <div className="tm-heat" role="table" aria-label="Rework by area and week">
          <span />
          {labels.map((w) => <span key={w} className="hd">{w}</span>)}
          {t.areas.map((a) => {
            const vals = (metric === "attempts" ? a.attempts : a.overrules).slice(from);
            return (
              <div key={a.path} style={{ display: "contents" }} role="row">
                <span className="tm-rowlbl" title={a.path}><span className="pre">{a.path.split("/")[0]}/</span>{a.path.split("/")[1]}</span>
                {vals.map((v, w) => {
                  const empty = a.attempts[w + from] === 0;
                  return (
                    <span
                      key={w}
                      className={`tm-cell ${empty ? "empty" : ""}`}
                      style={empty ? undefined : { ["--p" as string]: `${Math.round(8 + heat(v) * 62)}%` }}
                      title={empty ? `${a.path}, week of ${labels[w]}: no criteria` : `${a.path}, week of ${labels[w]}: ${metric === "attempts" ? `${v.toFixed(1)} attempts per criterion` : `${v} overrules`}`}
                    >
                      {empty ? "·" : metric === "attempts" ? v.toFixed(1) : v}
                    </span>
                  );
                })}
              </div>
            );
          })}
        </div>
        <div className="tm-scale">{metric === "attempts" ? "1.0" : "0"} <i /> {metric === "attempts" ? `${maxAttempts.toFixed(1)} attempts` : `${maxOverrules} overrules`} <span>· dots mean no sessions that week</span></div>
      </Panel>

      <div className="grid-7-5">
        <Panel title="Criteria quality" sub="Was it the agent, or the brief?" aside={src(t.sources.funnel)}>
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
                  <div>{s.text}</div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Where rework concentrates" sub="Areas ranked by human overrules, last 8 weeks" aside={src(t.sources.areas)}>
          <ol className="tm-rank">
            {ranked.map((r) => (
              <li key={r.path}>
                <span className="tm-rank-p" title={r.path}>{r.path}</span>
                <b>{r.overrules}</b>
                <span className="tm-rank-bar"><i style={{ width: `${(r.overrules / maxRank) * 100}%` }} /></span>
                <span className="tm-rank-a">{r.attempts === null ? "no criteria" : `${r.attempts.toFixed(1)} attempts per criterion`}</span>
              </li>
            ))}
          </ol>
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
        sub="Where rework piles up, whether the agent or the brief caused it, and how the team's agents spend their effort."
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
        {(t) => <TeamBody key={t.id} t={t} />}
      </DataGate>
    </main>
  );
}
