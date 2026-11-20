import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowRight, Ban, CornerUpRight, ListPlus, MessagesSquare, ShieldX, Undo2 } from "lucide-react";
import StepViz2 from "./StepViz2";
import "../styles/home2.css";
import "../styles/viz2.css";
import "../styles/designs.css";

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

const DESIGN_LINKS = [
  { id: 0, label: "Original", href: "#/" },
  { id: 1, label: "1 · Morph UI", href: "#/home-4" },
  { id: 2, label: "2 · Topology", href: "#/home-5" },
  { id: 3, label: "3 · 2.5D Stack", href: "#/home-6" },
  { id: 4, label: "4 · State Machine", href: "#/home-7" },
  { id: 5, label: "5 · Motion Film", href: "#/home-8" },
];

const STEP_SHORT = ["Overview", "01 Record", "02 Overrule", "03 Check", "04 Patterns", "05 Approve", "06 Publish"];

export interface HomeShellProps {
  activeDesign: 1 | 2 | 3 | 4 | 5;
  designName: string;
  designTag: string;
  hideStepVizDesktop?: boolean;
  renderStage: (step: number, setStep: (s: number) => void) => ReactNode;
}

export default function HomeShell({ activeDesign, designName, designTag, hideStepVizDesktop, renderStage }: HomeShellProps) {
  const [step, setStep] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const phone = matchMedia("(max-width: 900px)").matches;
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && setStep(Number((e.target as HTMLElement).dataset.i))),
      { rootMargin: phone ? "-66% 0px -26% 0px" : "-42% 0px -42% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  const jumpToStep = (i: number) => {
    setStep(i);
    refs.current[i]?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <main className={hideStepVizDesktop ? "ds-page ds-clean-left" : "ds-page"}>
      <div className="ds-switcher-bar">
        <div className="wrap ds-switcher-in">
          <div className="ds-switcher-meta">
            <span className="chip human">Design {activeDesign}/5</span>
            <strong>{designName}</strong>
            <span className="ds-switcher-tag">{designTag}</span>
          </div>
          <nav className="ds-switcher-links" aria-label="Home design approaches">
            {DESIGN_LINKS.map((d) => (
              <a key={d.id} href={d.href} className={d.id === activeDesign ? "on" : ""}>
                {d.label}
              </a>
            ))}
          </nav>
        </div>
      </div>

      <section className="wrap hx-story ds-story">
        <div className="hx-stage-col ds-stage-col">
          <div className="ds-stage-wrap">
            <div className="ds-stage-box">{renderStage(step, jumpToStep)}</div>
            <div className="ds-step-pills" role="tablist" aria-label="Story steps">
              {STEP_SHORT.map((label, i) => (
                <button
                  key={label}
                  type="button"
                  role="tab"
                  aria-selected={step === i}
                  className={step === i ? "on" : ""}
                  onClick={() => jumpToStep(i)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

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
                    <a className="btn" href="#/pr">See a PR Unpacked</a>
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
                  <div className="ds-stepviz-slot">
                    <StepViz2 i={i} />
                  </div>
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
            <a className="btn" href="#/pr">See a PR Unpacked</a>
          </div>
        </div>
      </section>

      <footer className="wrap hx-foot"><span>Unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative.</span></footer>
    </main>
  );
}
