import { ExternalLink } from "lucide-react";
import PrLive from "../pr/PrLive";
import PrMock from "./PrMock";
import { useAnalyses } from "../queries";
import { DataGate, PageHead, Panel, RepoSelect, useSelectedRepo } from "../ui";
import type { AnalysisListItem, Flag } from "../api";
import "../styles/team.css";

const FLAG_LABEL: Record<Flag, string> = {
  unsupported: "Unsupported claim",
  "new-dependency": "New dependency",
  "skipped-test": "Skipped test",
  "async-gap": "Async gap",
};

// The base link of the PR, never a single commit: the PR itself when there is one, otherwise the PRs for this branch.
function prBaseUrl(p: AnalysisListItem): string {
  const repo = `https://github.com/${p.repo.owner}/${p.repo.name}`;
  if (p.pr_url) return p.pr_url;
  if (p.pr_number != null) return `${repo}/pull/${p.pr_number}`;
  return `${repo}/pulls?q=${encodeURIComponent(`is:pr head:${p.branch}`)}`;
}

function PrListBody({ rows }: { rows: AnalysisListItem[] }) {
  return (
    <Panel title="Analyzed PRs" sub={`${rows.length} ${rows.length === 1 ? "analysis" : "analyses"}`}>
      <div className="tm-scroll">
        <table className="table tm-table">
          <colgroup>
            <col style={{ width: "40%" }} /><col style={{ width: "12%" }} /><col style={{ width: "13%" }} />
            <col style={{ width: "9%" }} /><col style={{ width: "9%" }} /><col style={{ width: "12%" }} /><col style={{ width: "10%" }} />
          </colgroup>
          <thead>
            <tr><th>PR / Commit</th><th>Agent</th><th>Decisions</th><th>Overrules</th><th>Attempts</th><th>Flags</th><th>GitHub</th></tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={7} className="tm-none">No analyzed PRs in the database for this repository yet. Push a branch with the Unpack hook installed to see it here.</td></tr>
            )}
            {rows.map((p) => {
              const href = `#/pr/${p.public_id}`;
              const ghUrl = prBaseUrl(p);
              return (
                <tr key={p.public_id} onClick={() => { location.hash = href; }}>
                  <td>
                    <span className="num">{p.pr_number != null ? `#${p.pr_number}` : p.short_sha}</span>
                    <span className="chip" style={{ marginRight: 6 }}>{p.pr_number != null ? (p.pr_state ?? "PR") : "commit"}</span>
                    <a href={href} onClick={(e) => e.stopPropagation()}>{p.title}</a>
                    <span className="ar">{p.area}</span>
                  </td>
                  <td>{p.agent}</td>
                  <td>
                    <div className="tm-dm">
                      <div className="tm-split">
                        <span className="a" style={{ flex: p.agent_decisions }} />
                        <span className="h" style={{ flex: p.human_decisions }} />
                      </div>
                      {p.agent_decisions}/{p.human_decisions}
                    </div>
                  </td>
                  <td className="mono">{p.overrules}</td>
                  <td className="mono">{p.attempts.toFixed(2)}</td>
                  <td>
                    {p.flags.length === 0 ? <span className="tm-none">none</span> : (
                      <div className="tm-flags">
                        {p.flags.map((fl) => <span key={fl} className={`chip ${fl === "unsupported" ? "bad" : "warn"}`}>{FLAG_LABEL[fl]}</span>)}
                      </div>
                    )}
                  </td>
                  <td>
                    <a
                      className="btn sm"
                      href={ghUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      title={p.pr_number != null ? `Open PR #${p.pr_number} on GitHub` : `Find the PRs for branch ${p.branch} on GitHub`}
                    >
                      View PR <ExternalLink size={12} />
                    </a>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function PrIndex() {
  const { repos, repo, setRepo } = useSelectedRepo();
  const q = useAnalyses(repo);
  return (
    <main className="wrap page tm">
      <PageHead
        crumbs={<>Org <b>›</b> <span>PR analyses</span>{repo && <> <b>›</b> <span>{repo}</span></>}</>}
        title="PR analyses"
        sub="Real analyzed pushes and pull requests from the database. Select any row to open its code graph, reasons, flow, and diff."
        meta={<><RepoSelect repos={repos} value={repo} onChange={setRepo} /><span className="chip ok">Live DB</span></>}
      />
      <DataGate q={q}>
        {(d) => <PrListBody rows={d.analyses} />}
      </DataGate>
    </main>
  );
}

// #/pr -> live list of analyzed PRs from the DB, #/pr/<public_id> -> that analysis, #/pr/mock -> illustrative page.
export default function PrPage({ id }: { id?: string }) {
  if (id === "mock") return <PrMock />;
  if (!id) return <PrIndex />;
  return <PrLive key={id} id={id} />;
}
