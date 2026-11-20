import Person from "./Person";

// The sticky figure for the scroll story. step 0..4 = alert, wall, who decided, found it, next morning.
const CLOCK = ["02:07", "02:07", "02:07", "02:14", "09:12"];
const wall = Array.from({ length: 9 }, (_, k) => ({ w: 36 + ((k * 53) % 60), kind: k % 4 === 1 ? "del" : k % 3 === 0 ? "ctx" : "add" }));

export default function StoryFigure({ step }: { step: number }) {
  const on = (...s: number[]) => (s.includes(step) ? "s3-blk on" : "s3-blk");
  const ok = step >= 3;
  return (
    <div className="s3-fig" data-step={step} role="img" aria-label={`Story step ${step + 1} of 5`}>
      <i className="s3-moon" />
      <header className="s3-bar">
        <div className="s3-clock mono">{CLOCK[step]}</div>
        <div className={`s3-alert mono ${ok ? "ok" : "bad"}`}>{ok ? "● payments-api · recovered" : "● payments-api · errors 14%"}</div>
      </header>
      <div className="s3-figbody">
        <div className="s3-who">
          <div className="s3-person" data-mood={step === 3 ? "calm" : step === 4 ? "lead" : "worried"}>
            <Person size={34} tone={step === 4 ? "human" : "ink"} />
            {step < 3 && <i className="s3-sweat" />}{step === 3 && <i className="s3-calm">✓</i>}
          </div>
          <span className="s3-role mono">{step === 4 ? "Tech lead" : "On-call"}</span>
        </div>
        <div className="s3-stack">
          <div className={on(0)}>
            <div className="s3-notif"><b className="mono">ALERT · payments-api</b><span>Error rate 14% (normal 0.2%)</span><small className="mono">PR #482 shipped 41 min ago · agent-written</small></div>
          </div>
          <div className={on(1)}>
            <div className="s3-prh mono">PR #482 · +1,204 −311 · 14 files</div>
            <div className="s3-wall tall">{wall.map((b, k) => <i key={k} className={b.kind} style={{ width: `${b.w}%` }} />)}</div>
            <p className="s3-say mono"><span>agent, unverified</span>“All done. Full test coverage.”</p>
          </div>
          <div className={on(2)}>
            <ol className="s3-list">
              <li className="agent struck"><b className="mono">Agent · T22</b><span>retry forever</span></li>
              <li className="human"><b className="mono">You · T33</b><span>“Cap it at 5.”</span></li>
              <li className="agent struck"><b className="mono">Agent · T31</b><span>skip flaky test</span></li>
              <li className="agent claim"><b className="mono">Agent claim · T47</b><span>full coverage</span></li>
            </ol>
          </div>
          <div className={on(3)}>
            <div className="s3-verdict"><b className="mono">CLAIM · “FULL COVERAGE”</b>
              <p><i>✕</i> Tests ran after the last edit? <em className="mono">stale since T38</em></p>
              <p><i>✕</i> A test reaches AsyncClient? <em className="mono">none · static estimate</em></p>
              <span className="s3-found mono">✓ found it · 02:14</span></div>
          </div>
          <div className={on(4)}>
            <div className="s3-policy"><b className="mono">POLICY CANDIDATE</b><span>Cap retries at 5.</span><small className="mono">3 sessions · 2 teams · scope org</small>
              <b className="s3-chip mono">P-13 · cap retries at 5</b></div>
          </div>
        </div>
      </div>
    </div>
  );
}
