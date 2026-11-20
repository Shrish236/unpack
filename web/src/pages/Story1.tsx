import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import HeroScene from "./story1/HeroScene";
import StoryScene from "./story1/StoryScene";
import "../styles/story1.css";

const STEPS = [
  { n: "Monday", h: "You say it", p: "You have told it this before. Today, again: no new library.", c: "Recorded with who said it, which turn, and your exact words." },
  { n: "Tuesday", h: "Someone else says it", p: "A different team, a different agent, the same sigh. Nobody knew you had already said it.", c: "Same correction, second team." },
  { n: "Thursday", h: "It is a pattern", p: "Three teams, one sentence. That is not a preference any more.", c: "Candidate once 3 sessions and 2 developers agree." },
  { n: "Friday", h: "A lead decides once", p: "One person reads the evidence and decides for everyone, one time.", c: "Scope, enforcement, owner and expiry are set here." },
  { n: "Next Monday", h: "Nobody has to say it", p: "The agent already knows. You get your Monday back.", c: "Published to AGENTS.md. Repeat corrections: 3 → 0." },
];

export default function Story1() {
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

  return (
    <main>
      <section className="wrap s1-hero-grid">
        <div className="s1-hero-text">
          <span className="eyebrow">Agent decision governance</span>
          <h1 className="display s1-hero">Say it once. <em>Every agent remembers.</em></h1>
          <p>Unpack records every correction you make to an agent, and turns the ones that repeat into policy every agent follows.</p>
          <div className="s1-cta">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR unpacked</a>
          </div>
          <ul className="s1-chips">
            <li className="chip agent">Agent decided</li><li className="chip human">Human decided</li>
            <li className="chip ok">Became policy</li><li className="chip sim">Illustrative data</li>
          </ul>
        </div>
        <HeroScene />
      </section>

      <section className="wrap s1-story">
        <div className="s1-stage-col"><div className="s1-stage"><StoryScene step={step} /></div></div>
        <div className="s1-steps">
          {STEPS.map((s, i) => (
            <article key={s.n} className="s1-step" data-i={i} data-active={step === i} ref={(el) => { refs.current[i] = el; }}>
              <span className="s1-num">{String(i + 1).padStart(2, "0")} · {s.n}</span>
              <h2 className="display">{s.h}</h2>
              <p>{s.p}</p>
              <small className="s1-capt">{s.c}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="s1-final">
        <div className="wrap">
          <span className="eyebrow">Governance, not just a log</span>
          <h2 className="display">Make every correction <em>count once.</em></h2>
          <div className="s1-cta s1-center">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR unpacked</a>
          </div>
        </div>
      </section>
      <footer className="wrap s1-foot"><span>unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative.</span></footer>
    </main>
  );
}
