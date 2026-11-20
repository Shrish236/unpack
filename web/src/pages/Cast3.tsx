import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import Road, { STATIONS } from "./cast3/Road";
import { BOTS, Bust, CAST } from "./cast3/kit";
import "../styles/cast3.css";

const clamp = (v: number) => Math.min(1, Math.max(0, v));

export default function Cast3() {
  const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [p, setP] = useState(reduced ? 1 : 0);
  const [size, setSize] = useState({ w: 1000, h: 560 });
  const sec = useRef<HTMLElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (reduced) return;
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = sec.current; if (!el) return;
        const top = innerWidth <= 760 ? 92 : 56;
        const r = el.getBoundingClientRect();
        setP(clamp((top - r.top) / Math.max(1, r.height - (innerHeight - top))));
      });
    };
    on();
    addEventListener("scroll", on, { passive: true }); addEventListener("resize", on);
    return () => { removeEventListener("scroll", on); removeEventListener("resize", on); cancelAnimationFrame(raf); };
  }, [reduced]);

  useEffect(() => {
    const el = box.current; if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el); setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const k = Math.min(6, Math.max(0, Math.round(p * 6)));
  const st = STATIONS[k];
  const jump = (i: number) => {
    const el = sec.current; if (!el) return;
    const top = innerWidth <= 760 ? 92 : 56;
    const y = el.getBoundingClientRect().top + scrollY + (i / 6) * (el.offsetHeight - (innerHeight - top)) - top;
    scrollTo({ top: y, behavior: "smooth" });
  };

  return (
    <main className="c3">
      <section className="wrap c3-hero">
        <span className="eyebrow">Agent decision governance</span>
        <h1 className="display c3-h1">Agents decide. Humans overrule. <em>Governance makes it stick.</em></h1>
        <p>Unpack records every decision an agent makes and every correction you make, checks them against your rules, and turns what repeats into policy every agent follows.</p>
        <div className="c3-cta">
          <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
          <a className="btn" href="#/pr">See a PR unpacked</a>
        </div>
        <ul className="c3-chips"><li className="chip agent">Agent decided</li><li className="chip human">Human decided</li><li className="chip ok">Became policy</li><li className="chip sim">Illustrative cast</li></ul>
        <div className="c3-cast" aria-label="Illustrative cast">
          {Object.values(CAST).map((c) => (
            <div key={c.id} className="c3-who"><Bust spec={c} /><b>{c.name}</b><span className="mono">{c.role} · {c.city}</span></div>
          ))}
          <div className="c3-who"><span className="c3-pip">🤖</span><b>{BOTS.pip.name}, {BOTS.bolt.name}, {BOTS.nova.name}</b><span className="mono">Agents on the road</span></div>
        </div>
        <p className="c3-hint mono">Scroll to follow Pip down the road ↓</p>
      </section>

      <section ref={sec} className={`c3-road${reduced ? " static" : ""}`} aria-label="The apprentice's road">
        <div className="c3-pin">
          <div ref={box} className="c3-view"><Road p={p} size={size} live /></div>
          <div className="c3-caption">
            <div className="c3-cap-main">
              <span className="eyebrow">Station {k + 1} of 7 · {st.k}</span>
              <h2>{st.t}</h2>
              <p>{st.d}</p>
              <small className="mono">{st.f}</small>
            </div>
            {st.cast.length > 0 && (
              <div className="c3-cap-cast">{st.cast.map((id) => <span key={id} className="chip human"><i />{CAST[id].name} · {CAST[id].role} · {CAST[id].city}</span>)}</div>
            )}
          </div>
          <div className="c3-prog" role="tablist" aria-label="Stations">
            <i className="c3-prog-fill" style={{ width: `${p * 100}%` }} />
            {STATIONS.map((s, i) => <button key={s.k} role="tab" aria-selected={i === k} className={i <= k ? "on" : ""} onClick={() => jump(i)}><span>{s.k}</span></button>)}
          </div>
        </div>
      </section>

      {reduced && (
        <section className="wrap c3-list">{STATIONS.map((s, i) => <div key={s.k}><span className="eyebrow">Station {i + 1} · {s.k}</span><h3>{s.t}</h3><p>{s.d}</p><small className="mono">{s.f}</small></div>)}</section>
      )}

      <section className="c3-close">
        <div className="wrap">
          <span className="eyebrow">Governance, not just a log</span>
          <h2 className="display">Make every correction <em>count once.</em></h2>
          <div className="c3-cta c3-cta-c">
            <a className="btn primary" href="#/govern">Open the governance inbox <ArrowRight size={16} /></a>
            <a className="btn" href="#/pr">See a PR unpacked</a>
          </div>
        </div>
      </section>
      <footer className="wrap c3-foot"><span>unpack · built at Startup Buildathon India 2026</span><span>All figures on this page are illustrative.</span></footer>
    </main>
  );
}
