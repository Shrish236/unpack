import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import Scene from "./story4/Scene";
import Figure from "./story4/Figure";
import "../styles/story4.css";

const STEPS = [
  { n: "01 · The same record", h: "The same record", p: "Three people sit in three seats and worry about the same agents. Unpack keeps one record they can all trust: every decision the agent made and every correction a human made, pinned to the turn that caused it.", cap: ["agent decisions", "human corrections", "pinned to a turn"], links: [["Open the governance inbox", "#/govern"]] },
  { n: "02 · The developer", h: "The developer: stop repeating yourself", p: "You told the agent “no new library” on Monday. You told another one on Tuesday. Unpack hears the correction once, sees it come back, and offers it as a rule every agent reads.", cap: ["your correction", "becomes a candidate", "lands in AGENTS.md"], links: [["See a PR Unpacked", "#/pr"]] },
  { n: "03 · The tech lead", h: "The tech lead: are agents following the rules?", p: "You should not have to read forty PRs to know. Adherence is a number per rule, and the rules that keep being broken wait for you in one inbox: approve, edit or reject.", cap: ["adherence per rule", "scope · enforcement · expiry"], links: [["Open the governance inbox", "#/govern"], ["Manager view", "#/team"]] },
  { n: "04 · The executive", h: "The executive: can we trust more?", p: "Trust is earned in numbers. When the same override stops coming back, an agent can move from a gate to a check. When it does not, it stays on the short leash. It is reversible either way.", cap: ["repeat overrides", "reversible autonomy", "associated with, not proven"], links: [["Executive view", "#/exec"]] },
  { n: "05 · No one ranked", h: "One record, no one ranked", p: "Unpack measures agents, areas and code. It never scores or ranks individual people, so a correction is a contribution, not a mark against anyone.", cap: ["agents", "areas", "code"], links: [] },
];

export default function Story4() {
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
      <section className="wrap s4-hero">
        <div className="s4-herotext">
          <span className="eyebrow">Agent decision governance</span>
          <h1 className="display s4-h1">One record. <em>Everyone gets what they need.</em></h1>
          <p>Developers stop repeating themselves, leads see whether agents follow the rules, and executives see whether the programme can be trusted, from the same record of decisions.</p>
          <div className="s4-cta">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR Unpacked</a>
          </div>
          <ul className="s4-chips">
            <li className="chip agent">Agent decided</li><li className="chip human">Human decided</li>
            <li className="chip ok">Became policy</li><li className="chip sim">Illustrative data</li>
          </ul>
        </div>
        <Scene />
      </section>

      <section className="wrap s4-story">
        <div className="s4-figcol"><Figure step={step} /></div>
        <div className="s4-steps">
          {STEPS.map((s, i) => (
            <article key={i} className="s4-step" data-i={i} data-active={step === i} ref={(el) => { refs.current[i] = el; }}>
              <span className="s4-num">{s.n}</span>
              <h2 className="display">{s.h}</h2>
              <p>{s.p}</p>
              <ul className="s4-caps">{s.cap.map((c) => <li key={c} className="mono">{c}</li>)}</ul>
              {s.links.length > 0 && <div className="s4-links-row">{s.links.map(([t, h]) => <a key={t} href={h}>{t} <ArrowRight size={14} /></a>)}</div>}
            </article>
          ))}
        </div>
      </section>

      <section className="s4-final">
        <div className="wrap">
          <span className="eyebrow">Governance, not just a log</span>
          <h2 className="display">Make every correction <em>count once.</em></h2>
          <div className="s4-cta s4-center">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR Unpacked</a>
          </div>
        </div>
      </section>

      <footer className="wrap s4-foot-bar"><span>Unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative.</span></footer>
    </main>
  );
}
