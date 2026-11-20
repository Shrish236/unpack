import { ArrowRight } from "lucide-react";
import OrbitSection from "./cast1/Orbit";
import "../styles/cast1.css";

export default function Cast1() {
  return (
    <main>
      <section className="wrap c1-top">
        <div className="c1-metric">
          <span className="mono c1-m-lbl">SAME CORRECTION · REPEATED 11× → SAID ONCE</span>
          <div className="c1-m-bar" aria-hidden="true">{Array.from({ length: 11 }, (_, i) => <i key={i} data-first={i === 0} />)}</div>
          <div className="c1-m-row mono"><span>without Unpack: 11 repeats</span><span><b>with Unpack: 1</b></span></div>
          <span className="chip sim">Illustrative cast</span>
        </div>
        <div className="c1-head">
          <span className="eyebrow">Agent decision governance</span>
          <h1 className="display c1-h1">Agents decide. Humans overrule. <em>Governance makes it stick.</em></h1>
          <p>Unpack records every decision an agent makes and every correction you make, checks them against your rules, and turns what repeats into policy every agent follows.</p>
          <div className="c1-cta">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR unpacked</a>
          </div>
        </div>
      </section>

      <OrbitSection />

      <section className="c1-final">
        <div className="wrap">
          <span className="eyebrow">Governance, not just a log</span>
          <h2 className="display">Make every correction <em>count once.</em></h2>
          <div className="c1-cta c1-cta-c">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR unpacked</a>
          </div>
        </div>
      </section>
      <footer className="wrap c1-foot"><span>unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative. The cast is fictional.</span></footer>
    </main>
  );
}
