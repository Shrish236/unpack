import PrLive from "../pr/PrLive";
import PrMock from "./PrMock";
import { useTeam, useTeams } from "../queries";
import { DataGate, PageHead, Panel } from "../ui";
import type { Flag, TeamPage } from "../api";
import "../styles/team.css";

const FLAG_LABEL: Record<Flag, string> = {
  unsupported: "Unsupported claim",
  "new-dependency": "New dependency",
  "skipped-test": "Skipped test",
  "async-gap": "Async gap",
};

function PrListBody({ prs }: { prs: TeamPage["prs"] }) {
  const realPrs = prs.filter((p) => p.public_id);
  const rows = realPrs.length > 0 ? realPrs : prs;
  return (
    <Panel title="Analyzed PRs" sub={`${rows.length} ${rows.length === 1 ? "analysis" : "analyses"}`}>
      <div className="tm-scroll">
        <table className="table tm-table">
          <thead>
            <tr><th>PR</th><th>Agent</th><th>Decisions</th><th>Overrules</th><th>Attempts</th><th>Flags</th></tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={6} className="tm-none">No analyzed PRs in the database yet. Push a branch with the Unpack hook installed to see it here.</td></tr>
            )}
            {rows.map((p) => {
              const href = p.public_id ? `#/pr/${p.public_id}` : "#/pr/mock";
              return (
                <tr key={p.public_id ?? p.number} onClick={() => { location.hash = href; }}>
                  <td>
                    <span className="num">#{p.number}</span>
                    {p.source === "measured" && <span className="chip ok" style={{ marginRight: 6 }}>Measured</span>}
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
  const index = useTeams();
  const teamId = index.data?.teams[0]?.id ?? "payments";
  const q = useTeam(teamId);
  return (
    <main className="wrap page tm">
      <PageHead
        crumbs={<>Company <b>›</b> <span>PR analyses</span></>}
        title="PR analyses"
        sub="Real analyzed pushes and pull requests from the database. Select any row to open its code graph, reasons, flow, and diff."
        meta={<span className="chip ok">Live DB</span>}
      />
      <DataGate q={q}>
        {(t) => <PrListBody prs={t.prs} />}
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
