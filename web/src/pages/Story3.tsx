import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import HeroScene from "./story3/HeroScene";
import StoryFigure from "./story3/StoryFigure";
import "../styles/story3.css";

const STEPS = [
  { n: "01 · 02:07", h: "The alert", p: "Payments are failing, and you were not in the room when this code was written. Your pulse is up before you open a single file.", fact: "Every agent-written change carries the session that produced it." },
  { n: "02 · The diff", h: "A wall of agent-written diff", p: "1,204 lines. Who wrote them? Who said yes to what? The agent's own summary says all is well, and that is the agent grading its own work.", fact: "Agent narration is shown as unverified. Your words are the anchor." },
  { n: "03 · The question", h: "Who decided this?", p: "The wall unfolds into a handful of decisions: each one typed, each pinned to the turn that caused it, each with who made it, and what a human refused.", fact: "Exact quotes, turn ids, and the overrules that changed the agent's mind." },
  { n: "04 · 02:14", h: "Seven minutes later", p: "“Full test coverage” is checked by code, not by the model. No test reaches the async path. You found it, and you can say why.", fact: "Claims are verified deterministically. The covering test is a static estimate, never measured coverage." },
  { n: "05 · Next morning", h: "It becomes a rule", p: "The lead does not want to be paged for this twice. The cap at five becomes a policy candidate, and one approval means every agent reads it.", fact: "A candidate needs 3 or more sessions and 2 or more developers. The lead sets scope, enforcement and expiry." },
];

export default function Story3() {
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
      <section className="wrap s3-hero">
        <div className="s3-hero-text">
          <span className="eyebrow">Agent decision governance</span>
          <h1 className="display s3-h1">When it breaks, know who decided what, <em>and why.</em></h1>
          <p className="s3-sub">Unpack turns an agent-written change into a short, verified story of every decision: the agent's, and the humans' who overruled it.</p>
          <div className="s3-cta">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR unpacked</a>
          </div>
          <ul className="s3-chips">
            <li className="chip agent">Agent decided</li><li className="chip human">Human decided</li>
            <li className="chip ok">Became policy</li><li className="chip sim">Illustrative data</li>
          </ul>
        </div>
        <HeroScene />
      </section>

      <section className="wrap s3-story">
        <div className="s3-fig-col"><StoryFigure step={step} /></div>
        <div className="s3-steps">
          {STEPS.map((s, i) => (
            <article key={i} className="s3-step" data-i={i} data-active={step === i} ref={(el) => { refs.current[i] = el; }}>
              <span className="s3-num">{s.n}</span>
              <h2 className="display">{s.h}</h2>
              <p>{s.p}</p>
              <small className="s3-fact">{s.fact}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="s3-final">
        <div className="wrap">
          <span className="eyebrow">Governance, not just a log</span>
          <h2 className="display">Make every correction <em>count once.</em></h2>
          <div className="s3-cta s3-center">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR unpacked</a>
          </div>
        </div>
      </section>
      <footer className="wrap s3-foot"><span>unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative.</span></footer>
    </main>
  );
}
