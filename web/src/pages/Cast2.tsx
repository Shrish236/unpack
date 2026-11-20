import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import Studio from "./cast2/Studio";
import { Bot, CAST, Person, type Who } from "./cast2/Kit";
import "../styles/cast2.css";

const STEPS = [
  { n: "Floor 1 · Dev floor", h: "A rookie makes a confident mistake.", p: "Pip adds a library nobody asked for. Priya has said this before, so she says it again.", c: "Unpack records the proposal, her choice, her exact words and the turn." },
  { n: "Floor 2 · The library", h: "The correction is filed, not forgotten.", p: "Lena files every correction. When Tomás and Sofia say the same thing on their teams, the cards stack up.", c: "11 sessions · 3 teams · 7 developers, counted and never ranked." },
  { n: "Floor 3 · Council room", h: "A lead decides once.", p: "Amara and Kenji review the pile, then set the scope, how hard to enforce it and when it expires. Marcus watches the repeat rate.", c: "Scope · enforcement · expiry · owner. Every rule can be retired." },
  { n: "Floor 4 · Training room", h: "The rule goes on the wall.", p: "Every agent, whichever vendor made it, reads the same wall. That is what governance is for.", c: "Published to AGENTS.md and skill files, with a PR check." },
  { n: "Next morning", h: "The rookie gets it right.", p: "Pip reads the wall, writes the helper itself, and earns a little more trust. Priya doesn't have to say it again.", c: "Overrides 11 → 3: associated with the policy, not proven caused by it." },
];
const ROSTER: Who[] = ["priya", "tomas", "amara", "kenji", "sofia", "marcus", "lena"];

export default function Cast2() {
  const [step, setStep] = useState(0);
  const [phone, setPhone] = useState(() => matchMedia("(max-width: 900px)").matches);
  const refs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const mq = matchMedia("(max-width: 900px)");
    const on = () => setPhone(mq.matches);
    mq.addEventListener("change", on);
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && setStep(Number((e.target as HTMLElement).dataset.i))),
      { rootMargin: mq.matches ? "-66% 0px -26% 0px" : "-42% 0px -42% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => { io.disconnect(); mq.removeEventListener("change", on); };
  }, []);

  return (
    <main>
      <section className="wrap c2-hero">
        <div className="c2-hero-text">
          <span className="eyebrow">Agent decision governance</span>
          <h1 className="display c2-h1">Agents decide. Humans overrule. <em>Governance makes it stick.</em></h1>
          <p>Unpack records every decision an agent makes and every correction you make, checks them against your rules, and turns what repeats into policy every agent follows.</p>
          <div className="c2-cta">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR Unpacked</a>
          </div>
          <ul className="c2-chips"><li className="chip agent">Agent decided</li><li className="chip human">Human decided</li><li className="chip ok">Became policy</li><li className="chip sim">Illustrative cast</li></ul>
        </div>
        <div className="c2-portrait" aria-label="The illustrative cast: seven people and three agents">
          <svg viewBox="0 0 520 150">
            <rect x="0" y="118" width="520" height="3" className="c2-slab" />
            {ROSTER.map((w, i) => <Person key={w} look={CAST[w].look} x={34 + i * 62} y={118} s={1.5} mood={i % 3 === 0 ? "pleased" : "neutral"} />)}
            <Bot kind="pip" x={470} y={118} s={1.5} mood="pleased" /><Bot kind="bolt" x={500} y={118} s={0.9} />
          </svg>
          <p className="c2-roster mono">Seven people, three agents. All fictional, all labelled.</p>
        </div>
      </section>

      <section className="wrap c2-story">
        <div className="c2-stage-col"><div className="c2-stage"><Studio step={step} k={phone ? 1.4 : 1} /></div></div>
        <div className="c2-steps">
          {STEPS.map((s, i) => (
            <article key={i} className="c2-step" data-i={i} data-active={step === i} ref={(el) => { refs.current[i] = el; }}>
              <span className="c2-num">{s.n}</span>
              <h2 className="display">{s.h}</h2>
              <p>{s.p}</p>
              <p className="c2-cap mono">{s.c}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="c2-cast-sec">
        <div className="wrap">
          <span className="eyebrow">Illustrative cast</span>
          <h2 className="display">Seven people, three agents.</h2>
          <ul className="c2-cast">
            {ROSTER.map((w) => (
              <li key={w}>
                <svg viewBox="-24 -66 48 74" aria-hidden="true"><Person look={CAST[w].look} x={0} y={0} mood="pleased" /></svg>
                <b>{CAST[w].name}</b><span className="mono">{CAST[w].role} · {CAST[w].city}</span>
              </li>
            ))}
            {(["pip", "bolt", "nova"] as const).map((b) => (
              <li key={b}><svg viewBox="-24 -66 48 74" aria-hidden="true"><Bot kind={b} x={0} y={0} mood="pleased" /></svg><b>{b[0].toUpperCase() + b.slice(1)}</b><span className="mono">Agent</span></li>
            ))}
          </ul>
        </div>
      </section>

      <section className="c2-final">
        <div className="wrap">
          <span className="eyebrow">Governance, not just a log</span>
          <h2 className="display">Make every correction <em>count once.</em></h2>
          <div className="c2-cta c2-cta-c">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR Unpacked</a>
          </div>
        </div>
      </section>
      <footer className="wrap c2-foot"><span>Unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative.</span></footer>
    </main>
  );
}
