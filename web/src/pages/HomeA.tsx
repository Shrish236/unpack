import { useEffect, useRef, useState } from "react";
import { ArrowRight, Ban, CornerUpRight, ListPlus, MessagesSquare, ShieldX, Undo2 } from "lucide-react";
import SceneA from "./homea/SceneA";
import "../styles/home2.css";

const STEPS = [
  { n: "", h: "", p: "Unpack records every decision an agent makes and every correction you make, checks them against your rules, and turns what repeats into policy every agent follows." },
  { n: "01 · Record", h: "Record both voices", p: "Every choice in the session, the agent's and yours, becomes a typed decision pinned to the turn that caused it." },
  { n: "02 · Human decision", h: "Capture the human decision", p: "When you say “don't add a library”, that is the most valuable line in the session. Unpack records the proposal, your choice and your exact words." },
  { n: "03 · Check", h: "Check agents against your rules", p: "Agent decisions are checked against the skills they were given and against the evidence, so adherence is a number, not a feeling." },
  { n: "04 · Patterns", h: "Notice what repeats", p: "The same overrule across sessions and teams becomes a policy candidate. One developer is a preference; several is a pattern." },
  { n: "05 · Approve", h: "Approve it", p: "A tech lead approves, edits or rejects. Set the scope, how hard it is enforced, and when it expires." },
  { n: "06 · Publish", h: "Publish, then measure", p: "Approved decisions are published into the skills and context every agent reads. Then Unpack measures whether the override stopped." },
];

const KINDS = [
  { icon: CornerUpRight, name: "Redirect", quote: "Instead of tenacity, write the backoff with what we already have.", records: "The agent's proposal, your choice, your reason, the area of code.", where: ["PR story", "Governance inbox"] },
  { icon: Ban, name: "Reject", quote: "No skipping tests. Find out why it times out.", records: "The proposal, the rejection and the exact turn it happened.", where: ["PR story", "Skill adherence"] },
  { icon: ShieldX, name: "Permission denied", quote: "Allow `pip install tenacity`?  →  Denied", records: "The denied tool call and its arguments. No interpretation needed.", where: ["Governance inbox", "Skill check"] },
  { icon: Undo2, name: "Revert or edit", quote: "− 14 lines by the agent, + 6 by you, same function", records: "The reverted function and how many edits it took to land.", where: ["PR story", "Rework by area"] },
  { icon: ListPlus, name: "Requirement added", quote: "This has to work for AsyncClient as well.", records: "A new acceptance criterion the prompt and ticket lacked, and who added it.", where: ["Criteria ladder", "Manager view"] },
  { icon: MessagesSquare, name: "Discussion decision", quote: "Option B. Retry in the transport layer, not per call.", records: "The options discussed before any code, the choice, and your rationale.", where: ["PR story", "Decision ledger"] },
];

// What Unpack stores at each step. The scene shows the surface; this shows the record.
const FACTS: [string, string][][] = [
  [],
  [["Who", "agent · you"], ["Type", "Dependency"], ["Pinned to", "turns T16 and T18"], ["Source", "the session transcript"]],
  [["Kind", "redirect"], ["Proposal", "add tenacity"], ["Your choice", "stdlib backoff"], ["Evidence", "your words, verbatim, T18"]],
  [["Rules", "2 of 5 followed"], ["Claim", "“full test coverage”: unsupported"], ["Checked by", "code, not the model"]],
  [["Sessions", "11"], ["Teams", "3"], ["Developers", "7 (counted, never ranked)"], ["Threshold", "≥ 3 sessions, ≥ 2 developers"]],
  [["Scope", "org"], ["Enforcement", "PR check"], ["Expires", "2027-03"], ["Owner", "@platform"]],
  [["Published to", "AGENTS.md · skills · PR check"], ["Overrides", "11 → 3 per 100 sessions"], ["Reading", "associated with the policy, not proven caused"]],
];

export default function HomeA() {
  const [step, setStep] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]);

  // the current step is the one crossing a band of the viewport (a lower band on phones, where the scene is pinned on top)
  useEffect(() => {
    const phone = matchMedia("(max-width: 900px)").matches;
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && setStep(Number((e.target as HTMLElement).dataset.i))),
      { rootMargin: phone ? "-66% 0px -26% 0px" : "-42% 0px -42% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <main>
      <section className="wrap hx-story">
        <div className="hx-stage-col"><div className="hx-stage"><SceneA step={step} /></div></div>
        <div className="hx-steps">
          {STEPS.map((s, i) => (
            <article key={i} className="hx-step" data-i={i} data-active={step === i} ref={(el) => { refs.current[i] = el; }}>
              {i === 0 ? (
                <>
                  <span className="eyebrow">Agent decision governance</span>
                  <h1 className="display hx-hero">Agents decide. Humans overrule. <em>Governance makes it stick.</em></h1>
                  <p>{s.p}</p>
                  <div className="hx-cta">
                    <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
                    <a className="btn" href="#/pr">See a PR unpacked</a>
                  </div>
                  <ul className="hx-chips">
                    <li className="chip agent">Agent decided</li><li className="chip human">Human decided</li>
                    <li className="chip ok">Became policy</li><li className="chip sim">Illustrative data</li>
                  </ul>
                </>
              ) : (
                <>
                  <span className="hx-num">{s.n}</span>
                  <h2 className="display">{s.h}</h2>
                  <p>{s.p}</p>
                  <dl className="ha-facts">
                    {FACTS[i].map(([k, v], j) => [<dt key={k} style={{ ["--i" as string]: j }}>{k}</dt>, <dd key={k + "v"} style={{ ["--i" as string]: j }}>{v}</dd>])}
                  </dl>
                </>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="hx-section" id="humans">
        <div className="wrap">
          <span className="eyebrow">Where human decisions come from</span>
          <h2 className="display">Six ways you steer an agent. <em>All of them get recorded.</em></h2>
          <p className="hx-lede">Most of the signal is not in the code. It is in what you said, refused or changed while the agent worked.</p>
          <div className="hx-flow" aria-label="How a human decision flows through Unpack">
            <span>Session turns + ticket and PR comments</span><b>›</b><span>Classified: who · type · kind</span><b>›</b>
            <span>PR story</span><b>›</b><span>Governance inbox</span><b>›</b><span>Skill</span>
          </div>
          <div className="hx-kinds">
            {KINDS.map(({ icon: Icon, name, quote, records, where }) => (
              <article className="hx-kind" key={name}>
                <header><Icon size={16} aria-hidden="true" /><h3>{name}</h3></header>
                <blockquote>{quote}</blockquote>
                <p><span>Records</span>{records}</p>
                <ul>{where.map((w) => <li className="chip" key={w}>{w}</li>)}</ul>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="hx-section" id="views">
        <div className="wrap">
          <span className="eyebrow">One record, every altitude</span>
          <h2 className="display">From the boardroom to <em>a single turn.</em></h2>
          <p className="hx-lede">The same verified record answers different questions at each level. Click down from the company to the exact quote that started it.</p>
          <div className="hx-drill" aria-label="Drill-down path">
            <span>Company</span><b>›</b><span>Team</span><b>›</b><span>PR</span><b>›</b><span>Session</span><b>›</b><span>Decision</span>
          </div>
          <div className="hx-alt">
            <a className="hx-card" href="#/exec">
              <span className="chip">Leadership</span>
              <h3>Are agents following our rules?</h3>
              <p>Adherence to skills, repeat overrides and decision mix. No names, no rankings.</p>
              <div className="hx-viz">
                <div className="hx-big">86<small>% adherence</small></div>
                <svg className="hx-spark" viewBox="0 0 200 56" preserveAspectRatio="none"><path d="M0 46 C 30 44, 40 38, 70 34 S 120 26, 150 16 S 185 8, 200 6" /></svg>
              </div>
              <span className="hx-link">Open the executive view <ArrowRight size={14} /></span>
            </a>
            <a className="hx-card" href="#/team">
              <span className="chip">Engineering managers</span>
              <h3>Where does rework pile up?</h3>
              <p>Rework by area, and whether the cause was the agent or the brief.</p>
              <div className="hx-viz">
                {[["payments", 78, 14], ["auth", 50, 9], ["search", 22, 4]].map(([n, w, c]) => (
                  <div className="hx-bar" key={n as string}><span>{n}</span><i style={{ ["--w" as string]: `${w}%` }} /><span>{c}</span></div>
                ))}
              </div>
              <span className="hx-link">Open the manager view <ArrowRight size={14} /></span>
            </a>
            <a className="hx-card" href="#/govern">
              <span className="chip human">Governance</span>
              <h3>What should every agent learn?</h3>
              <p>Policy candidates with their evidence. Approve, edit or reject. Set scope, enforcement and expiry.</p>
              <div className="hx-viz hx-inbox">
                <div>No new runtime dependency <span className="chip human">11 sessions</span></div>
                <div>Never skip a failing test <span className="chip human">8 sessions</span></div>
                <div>Async parity in retries <span className="chip warn">3 sessions</span></div>
              </div>
              <span className="hx-link">Open the governance inbox <ArrowRight size={14} /></span>
            </a>
          </div>
          <p className="hx-note">Illustrative data</p>
        </div>
      </section>

      <section className="hx-section">
        <div className="wrap">
          <span className="eyebrow">Neutral by design</span>
          <h2 className="display">Reads the agent you <em>already use.</em></h2>
          <p className="hx-lede">One adapter per agent, one common session format. Everything downstream sees the same record.</p>
          <div className="hx-agents">
            <span className="chip ok">Gemini CLI · built</span>
            <span className="chip ok">Claude Code · adapter built</span>
            <span className="chip">Codex · next</span>
            <span className="chip">Cursor · next</span>
            <span className="chip">Copilot · next</span>
          </div>
        </div>
      </section>

      <section className="hx-section hx-final">
        <div className="wrap">
          <span className="eyebrow">Governance, not just a log</span>
          <h2 className="display">Make every correction <em>count once.</em></h2>
          <div className="hx-cta hx-center">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR unpacked</a>
          </div>
        </div>
      </section>

      <footer className="wrap hx-foot"><span>unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative.</span></footer>
    </main>
  );
}
