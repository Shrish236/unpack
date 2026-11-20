import { useEffect, useRef, useState } from "react";
import { ArrowRight, Ban, CornerUpRight, ListPlus, MessagesSquare, ShieldX, Undo2 } from "lucide-react";
import Stage from "./Stage";
import StepViz from "./StepViz";
import "../styles/home.css";
import "../styles/viz.css";

const STEPS = [
  { n: "", h: null, p: "Unpack reads agent sessions, types every decision, checks claims against evidence, and feeds approved human corrections back to every agent." },
  { n: "01 · Session", h: "Read the session, not the diff.", p: "Every choice in the transcript, the agent's and yours, becomes a typed decision pinned to the turn that caused it: architecture, dependency, retries, test, design, scope." },
  { n: "02 · Who decided", h: "Agent or human. Then check the rules.", p: "Each decision is attributed. Agent decisions are checked against the skills it was given, so adherence is a number, not a feeling." },
  { n: "03 · Overrules", h: "Keep the “no”.", p: "When you say “don't add a library”, that is the most valuable line in the session. Unpack records the proposal, your choice and your exact words." },
  { n: "04 · Iterations", h: "Was it the agent, or the brief?", p: "Every acceptance criterion, from your prompt or the ticket, gets a ladder. Needed a second try? Unpack tells you whether the agent missed it or the requirement was too thin." },
  { n: "05 · Evidence", h: "Check the claim, not the story.", p: "“Full test coverage” is checked against the code graph and the test runs. The model extracts. Code decides." },
  { n: "06 · Patterns", h: "Notice what keeps happening.", p: "The same overrule across sessions and teams becomes a policy candidate. A tech lead approves, edits or rejects it." },
  { n: "07 · Loop", h: "Feed it back.", p: "Approved decisions publish into the skills and context every agent reads. Then Unpack measures whether the override stopped." },
];

const KINDS = [
  { icon: CornerUpRight, name: "Redirect", quote: "Instead of tenacity, write the backoff with what we already have.", records: "The agent's proposal, your choice, your reason, the area of code.", where: ["PR story", "Governance inbox"] },
  { icon: Ban, name: "Reject", quote: "No skipping tests. Find out why it times out.", records: "The proposal, the rejection and the exact turn it happened.", where: ["PR story", "Skill adherence"] },
  { icon: ShieldX, name: "Permission denied", quote: "Allow `pip install tenacity`?  →  Denied", records: "The denied tool call and its arguments. No interpretation needed.", where: ["Governance inbox", "Skill check"] },
  { icon: Undo2, name: "Revert or edit", quote: "− 14 lines by the agent, + 6 by you, same function", records: "The reverted function and how many edits it took to land.", where: ["PR story", "Rework by area"] },
  { icon: ListPlus, name: "Requirement added", quote: "This has to work for AsyncClient as well.", records: "A new acceptance criterion the prompt and ticket lacked, and who added it.", where: ["Criteria ladder", "Manager view"] },
  { icon: MessagesSquare, name: "Discussion decision", quote: "Option B. Retry in the transport layer, not per call.", records: "The options discussed before any code, the choice, and your rationale.", where: ["PR story", "Decision ledger"] },
];

export default function HomeV1() {
  const [step, setStep] = useState(0);
  const story = useRef<HTMLDivElement>(null);
  const refs = useRef<(HTMLElement | null)[]>([]);

  // which step is "current": the one crossing a band of the viewport (lower band on phones, where the figure is pinned on top)
  useEffect(() => {
    const phone = matchMedia("(max-width: 900px)").matches;
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && setStep(Number((e.target as HTMLElement).dataset.i))),
      { rootMargin: phone ? "-66% 0px -26% 0px" : "-42% 0px -42% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  // scroll progress drives the slight parallax of the figure
  useEffect(() => {
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = story.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        const p = Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - innerHeight)));
        el.style.setProperty("--sp", p.toFixed(3));
      });
    };
    addEventListener("scroll", on, { passive: true });
    return () => { removeEventListener("scroll", on); cancelAnimationFrame(raf); };
  }, []);

  // hash routes own the URL hash, so in-page links scroll by hand
  const jump = (id: string) => (e: React.MouseEvent) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); };

  return (
    <main>
      <section className="wrap story" ref={story}>
        <div className="stage-col"><div className="stage-tilt"><Stage step={step} /></div></div>
        <div className="steps">
          {STEPS.map((s, i) => (
            <article key={i} className="step" data-i={i} data-active={step === i} ref={(el) => { refs.current[i] = el; }}>
              {i === 0 ? (
                <>
                  <span className="eyebrow">Agent decision observability</span>
                  <h1 className="display hero-h">Every decision your agents made. <em>And every one you overruled.</em></h1>
                  <p>{s.p}</p>
                  <div className="cta">
                    <a className="btn primary" href="#/pr">See a PR Unpacked <ArrowRight size={16} /></a>
                    <a className="btn" href="#humans" onClick={jump("humans")}>How it reads</a>
                  </div>
                  <ul><li className="chip agent">Agent decided</li><li className="chip human">Human overruled</li><li className="chip sim">Illustrative data</li></ul>
                </>
              ) : (
                <>
                  <span className="num">{s.n}</span>
                  <h2 className="display">{s.h}</h2>
                  <p>{s.p}</p>
                  <StepViz i={i} />
                </>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="section" id="humans">
        <div className="wrap">
          <span className="eyebrow">Where human decisions come from</span>
          <h2 className="display">Six ways you steer an agent. <em>All of them get recorded.</em></h2>
          <p className="lede">Most of the signal is not in the code. It is in what you said, refused or changed while the agent worked.</p>
          <div className="flow" aria-label="How a human decision flows through Unpack">
            <span>Session turns + ticket and PR comments</span><b>›</b>
            <span>Classified: who · type · kind</span><b>›</b>
            <span>PR story</span><b>›</b>
            <span>Governance inbox</span><b>›</b>
            <span>Skill</span>
          </div>
          <div className="hkinds">
            {KINDS.map(({ icon: Icon, name, quote, records, where }) => (
              <article className="hkind" key={name}>
                <header><Icon size={16} aria-hidden="true" /><h3>{name}</h3></header>
                <blockquote>{quote}</blockquote>
                <p><span>Records</span>{records}</p>
                <ul>{where.map((w) => <li className="chip" key={w}>{w}</li>)}</ul>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section" id="views">
        <div className="wrap">
          <span className="eyebrow">One record, every altitude</span>
          <h2 className="display">From the boardroom to <em>a single turn.</em></h2>
          <p className="lede">The same verified record answers different questions at each level. Click down from the company to the exact quote that started it.</p>
          <div className="drill" aria-label="Drill-down path">
            <span>Company</span><b>›</b><span>Team</span><b>›</b><span>PR</span><b>›</b><span>Session</span><b>›</b><span>Decision</span>
          </div>
          <div className="alt">
            <a className="alt-card" href="#/exec">
              <span className="chip">Leadership</span>
              <h3>Are agents following our rules?</h3>
              <p>Adherence to skills, repeat overrides and decision mix. No names, no rankings.</p>
              <div className="alt-viz">
                <div className="big">86<small>% adherence</small></div>
                <svg className="spark" viewBox="0 0 200 56" preserveAspectRatio="none"><path d="M0 46 C 30 44, 40 38, 70 34 S 120 26, 150 16 S 185 8, 200 6" /></svg>
              </div>
            </a>
            <a className="alt-card" href="#/team">
              <span className="chip">Engineering managers</span>
              <h3>Where does rework pile up?</h3>
              <p>Iterations per criterion by area, and whether the cause was the agent or the brief.</p>
              <div className="alt-viz">
                {[["payments", 78, 14], ["auth", 50, 9], ["search", 22, 4]].map(([n, w, c]) => (
                  <div className="hbar" key={n as string}><span>{n}</span><i style={{ ["--w" as string]: `${w}%` }} /><span>{c}</span></div>
                ))}
              </div>
            </a>
            <a className="alt-card" href="#/govern">
              <span className="chip">Governance</span>
              <h3>What should every agent learn?</h3>
              <p>Policy candidates with their evidence. Approve, edit or reject. Set scope, enforcement and expiry.</p>
              <div className="alt-viz inbox">
                <div>No new runtime dependency <span className="chip human">11 sessions</span></div>
                <div>Never skip a failing test <span className="chip human">8 sessions</span></div>
                <div>Async parity in retries <span className="chip warn">3 sessions</span></div>
              </div>
            </a>
          </div>
          <p className="eyebrow" style={{ marginTop: "var(--sp-4)" }}>Illustrative data</p>
        </div>
      </section>

      <section className="section">
        <div className="wrap">
          <span className="eyebrow">Neutral by design</span>
          <h2 className="display">Reads the agent you <em>already use.</em></h2>
          <p className="lede">One adapter per agent, one common session format. Everything downstream sees the same record.</p>
          <div className="agents">
            <span className="chip ok">Gemini CLI · built</span>
            <span className="chip">Claude Code · next</span>
            <span className="chip">Codex</span>
            <span className="chip">Cursor</span>
            <span className="chip">Copilot</span>
          </div>
        </div>
      </section>

      <section className="section final">
        <div className="wrap">
          <span className="eyebrow">See it on a real PR</span>
          <h2 className="display">Decisions, overrules and claims, <em>on the record.</em></h2>
          <div className="cta"><a className="btn primary" href="#/pr">Open the example PR <ArrowRight size={16} /></a></div>
        </div>
      </section>

      <footer className="wrap foot"><span>Unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative.</span></footer>
    </main>
  );
}
