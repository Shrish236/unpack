import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import Scene from "./story2/Scene";
import "../styles/story2.css";

const STEPS = [
  { n: "01 · Months", h: "Months of small corrections", p: "Every week, someone senior says the same quiet things to an agent. No new library. Cap the retries. Never skip a failing test. It takes patience, and nobody writes it down.",
    f: [["Captured", "each correction is a human decision: redirect, reject, requirement"], ["Pinned to", "the turn and the exact words"]] },
  { n: "02 · One head", h: "The rules live in one head", p: "It works, as long as that person is in the room. Everyone else just feels that the agents behave better when they are around.",
    f: [["Without a record", "one person, one memory, no way to check"]] },
  { n: "03 · Gone", h: "Then they leave", p: "A new job, a new team, a long holiday. The judgement walks out with them, and the next agent starts from zero.",
    f: [["The risk", "the same mistakes, made again, by people who never heard the rule"]] },
  { n: "04 · Recorded", h: "But every correction was recorded", p: "Unpack kept each one, with who said it, when, and why. What repeated became a candidate, and a tech lead approved it as a rule with an owner and an expiry.",
    f: [["Kept", "decision, turn, quote, kind"], ["Became policy", "candidate → approved, owner and expiry set"]] },
  { n: "05 · Relief", h: "The new hire's agent already knows", p: "Their first week, the agent says “following: cap retries at 5” before anyone has to explain. The worry fades, and the team's judgement stays.",
    f: [["Published to", "AGENTS.md and skill files, for any agent"], ["Measured", "repeat overrides fall"]] },
];

export default function Story2() {
  const [step, setStep] = useState(1);
  const refs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const phone = matchMedia("(max-width: 900px)").matches;
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && setStep(Number((e.target as HTMLElement).dataset.i))),
      { rootMargin: phone ? "-60% 0px -26% 0px" : "-42% 0px -42% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <main>
      <section className="wrap s2-hero">
        <div>
          <span className="eyebrow">Agent decision governance</span>
          <h1 className="display">Your team's judgement, <em>kept when people move on.</em></h1>
          <p>Unpack records every correction your people make to agents and turns the ones that matter into rules every agent follows, including the agents your next hire brings.</p>
          <div className="s2-cta">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR Unpacked</a>
          </div>
          <ul className="s2-chips">
            <li className="chip agent">Agent decided</li><li className="chip human">Human decided</li>
            <li className="chip ok">Became policy</li><li className="chip sim">Illustrative data</li>
          </ul>
        </div>
        <div className="s2-frame"><Scene mode="loop" /></div>
      </section>

      <section className="wrap s2-story">
        <div className="s2-figure"><div className="s2-frame"><Scene mode="step" step={step} /></div></div>
        <div className="s2-steps">
          {STEPS.map((s, k) => (
            <article key={s.n} className="s2-step" data-i={k + 1} data-active={step === k + 1} ref={(el) => { refs.current[k] = el; }}>
              <span className="s2-num">{s.n}</span>
              <h2 className="display">{s.h}</h2>
              <p>{s.p}</p>
              <div className="s2-facts">{s.f.map(([a, b]) => <div key={a}><b>{a}</b><span>{b}</span></div>)}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="s2-section">
        <div className="wrap">
          <span className="eyebrow">Governance, not just a log</span>
          <h2 className="display">Make every correction <em>count once.</em></h2>
          <div className="s2-cta">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR Unpacked</a>
          </div>
        </div>
      </section>

      <footer className="wrap s2-foot"><span>Unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative.</span></footer>
    </main>
  );
}
