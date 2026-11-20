import { useEffect, useState } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";

/* Approach 5: Programmatic Motion Film ("Director-Cut Timeline Player", Remotion-style engine).
   A deterministic 60fps composition across 1080 frames (18 seconds = 6 chapters × 180 frames).
   Scroll step 0 plays the full continuous film; steps 1..6 lock and loop their exact chapter.
   Features kinetic typography, animated virtual cursor, and full manual frame scrubbing. */

const FPS = 60;
const CHAPTER_FRAMES = 180; // 3 seconds per chapter
const TOTAL_FRAMES = CHAPTER_FRAMES * 6; // 1080 frames = 18.0s

const CHAPTERS = [
  { id: 1, name: "01 RECORD", start: 0, end: 180 },
  { id: 2, name: "02 OVERRULE", start: 180, end: 360 },
  { id: 3, name: "03 VERIFY", start: 360, end: 540 },
  { id: 4, name: "04 CLUSTER", start: 540, end: 720 },
  { id: 5, name: "05 APPROVE", start: 720, end: 900 },
  { id: 6, name: "06 PUBLISH", start: 900, end: 1080 },
];

const clamp = (v: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
const easeOut = (t: number) => 1 - Math.pow(1 - clamp(t), 3);
const lerp = (a: number, b: number, t: number) => a + (b - a) * clamp(t);

function fmtTime(frame: number) {
  const sec = frame / FPS;
  const s = Math.floor(sec);
  const f = Math.floor(frame % FPS);
  return `00:${String(s).padStart(2, "0")}.${String(f).padStart(2, "0")}`;
}

export default function Design5Film({ step }: { step: number }) {
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(true);

  // Sync playhead when scroll step changes
  useEffect(() => {
    if (step >= 1 && step <= 6) {
      setFrame((step - 1) * CHAPTER_FRAMES);
    }
  }, [step]);

  // 60fps deterministic playback clock
  useEffect(() => {
    if (!playing) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let raf = 0;
    let last = performance.now();
    let acc = 0;

    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      acc += dt * FPS;
      if (acc >= 1) {
        const inc = Math.floor(acc);
        acc -= inc;
        setFrame((f) => {
          if (step >= 1 && step <= 6) {
            const lo = (step - 1) * CHAPTER_FRAMES;
            const hi = lo + CHAPTER_FRAMES;
            const next = f + inc;
            return next >= hi ? lo : next < lo ? lo : next;
          }
          return (f + inc) % TOTAL_FRAMES;
        });
      }
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, step]);

  const chIdx = Math.min(5, Math.floor(frame / CHAPTER_FRAMES));
  const local = (frame % CHAPTER_FRAMES) / CHAPTER_FRAMES; // 0..1 within current 3s chapter

  // Animated virtual cursor for Chapter 5 (Approve)
  const cursorT = easeOut((local - 0.15) / 0.45);
  const cursorX = lerp(310, 118, cursorT);
  const cursorY = lerp(245, 214, cursorT);
  const clicked = local > 0.62;

  // Animated curve reveal for Chapter 6
  const curveDraw = easeOut(local / 0.65);

  return (
    <div className="d5-root">
      {/* Cinema top telemetry bar */}
      <div className="d5-top mono">
        <span className="d5-rec">
          <i className={playing ? "on" : ""} /> {CHAPTERS[chIdx].name}
        </span>
        <span className="d5-tc">
          {fmtTime(frame)} / {fmtTime(TOTAL_FRAMES)} · 60fps
        </span>
      </div>

      {/* 16:11 Director Viewport */}
      <div className="d5-screen">
        {/* Chapter 1: RECORD */}
        {chIdx === 0 && (
          <div className="d5-scene">
            <div className="d5-kicker mono" style={{ opacity: easeOut(local * 5) }}>
              01 · RECORD BOTH VOICES
            </div>
            <div className="d5-feed">
              {[
                { t: "T14", who: "agent", msg: "wrap send() with retry wrapper", tag: "architecture", at: 0.08 },
                { t: "T16", who: "agent", msg: "pip install tenacity for backoff", tag: "dependency", at: 0.24 },
                { t: "T18", who: "human", msg: "“Don't add a library for this.”", tag: "redirect", at: 0.44 },
                { t: "T22", who: "agent", msg: "exponential backoff, max 5 tries", tag: "retries", at: 0.64 },
              ].map((row) => {
                const p = easeOut((local - row.at) / 0.18);
                return (
                  <div
                    key={row.t}
                    className={`d5-feed-row ${row.who}`}
                    style={{ opacity: p, transform: `translateY(${(1 - p) * 14}px)` }}
                  >
                    <b className="mono">{row.t}</b>
                    <span>{row.msg}</span>
                    <em className="mono">{row.tag}</em>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Chapter 2: OVERRULE */}
        {chIdx === 1 && (
          <div className="d5-scene d5-center-scene">
            <div className="d5-kicker mono">02 · CAPTURE THE HUMAN OVERRULE</div>
            <div
              className="d5-code-del mono"
              style={{
                opacity: easeOut(local * 4),
                transform: `scale(${lerp(1, 0.96, easeOut((local - 0.35) * 4))})`,
              }}
            >
              <span>−</span> pip install tenacity
              <i style={{ width: `${easeOut((local - 0.28) / 0.25) * 100}%` }} />
            </div>
            <div
              className="d5-quote-hero"
              style={{
                opacity: easeOut((local - 0.36) / 0.24),
                transform: `translateY(${(1 - easeOut((local - 0.36) / 0.24)) * 16}px)`,
              }}
            >
              “Don't add a library for this.”
              <small className="mono">HUMAN REDIRECT · TURN T18 · PINNED TO DIFF</small>
            </div>
          </div>
        )}

        {/* Chapter 3: VERIFY */}
        {chIdx === 2 && (
          <div className="d5-scene">
            <div className="d5-kicker mono">03 · CHECK CLAIMS AGAINST CODE</div>
            <div className="d5-verify-grid">
              <div className="d5-verify-left">
                <div className="d5-score-big">
                  {Math.round(lerp(0, 2, easeOut(local * 2.5)))} <small>/ 5</small>
                </div>
                <span className="mono d5-sub-k">skill rules followed</span>
              </div>
              <div className="d5-verify-right">
                <div className="d5-claim-quote">“All done. Full test coverage.”</div>
                <div
                  className="d5-stamp"
                  style={{
                    opacity: easeOut((local - 0.38) / 0.16),
                    transform: `scale(${lerp(1.5, 1, easeOut((local - 0.38) / 0.16))}) rotate(-3deg)`,
                  }}
                >
                  UNSUPPORTED · Async._send (0 tests)
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Chapter 4: CLUSTER */}
        {chIdx === 3 && (
          <div className="d5-scene d5-center-scene">
            <div className="d5-kicker mono">04 · NOTICE WHAT REPEATS</div>
            <div className="d5-big-counter">
              <strong>{Math.round(lerp(1, 11, easeOut(local / 0.55)))}</strong>
              <span className="mono">identical overrules</span>
            </div>
            <div className="d5-dots-bar">
              {Array.from({ length: 11 }, (_, i) => {
                const p = easeOut((local - i * 0.04) / 0.14);
                return <i key={i} style={{ opacity: p, transform: `scale(${p})` }} />;
              })}
            </div>
            <div
              className="d5-cand-pill mono"
              style={{ opacity: easeOut((local - 0.52) / 0.2), transform: `translateY(${(1 - easeOut((local - 0.52) / 0.2)) * 10}px)` }}
            >
              3 TEAMS · 7 DEVELOPERS → PROMOTED TO POLICY CANDIDATE P-12
            </div>
          </div>
        )}

        {/* Chapter 5: APPROVE (with animated virtual cursor) */}
        {chIdx === 4 && (
          <div className="d5-scene d5-approve-scene">
            <div className="d5-kicker mono">05 · APPROVE ONCE</div>
            <div className="d5-modal">
              <div className="d5-modal-h">Add no new runtime dependency without approval.</div>
              <div className="d5-modal-meta mono">
                <span>scope: <b>org</b></span>
                <span>enforce: <b>PR check</b></span>
                <span>expires: <b>2027-03</b></span>
              </div>
              <div className="d5-modal-foot">
                <span className={`d5-fake-btn ${clicked ? "clicked" : ""}`}>
                  {clicked ? "✓ Approved & Published" : "Approve Policy P-12"}
                </span>
                {clicked && <code className="mono d5-out-tag">→ AGENTS.md updated</code>}
              </div>
            </div>
            {/* Virtual director cursor */}
            <svg
              className="d5-cursor"
              width="20"
              height="20"
              viewBox="0 0 20 20"
              style={{
                transform: `translate(${cursorX}px, ${cursorY}px) scale(${local > 0.58 && local < 0.67 ? 0.85 : 1})`,
              }}
              aria-hidden="true"
            >
              <path d="M3 2 L16 10 L10 11.5 L7.5 17 Z" />
            </svg>
          </div>
        )}

        {/* Chapter 6: PUBLISH & MEASURE */}
        {chIdx === 5 && (
          <div className="d5-scene">
            <div className="d5-kicker mono">06 · PUBLISH, THEN MEASURE</div>
            <div className="d5-final-nums">
              <span className="was">11</span>
              <span className="arr">→</span>
              <span className="now">{Math.round(lerp(11, 3, curveDraw))}</span>
              <small className="mono">overrides per 100 sessions</small>
            </div>
            <svg viewBox="0 0 360 95" className="d5-chart" aria-hidden="true">
              <line x1="165" y1="8" x2="165" y2="88" className="d5-chart-mark" />
              <path
                d="M10 20 L65 24 L118 17 L165 26 L215 56 L266 72 L315 80 L350 83"
                pathLength={1}
                strokeDasharray="1"
                strokeDashoffset={1 - curveDraw}
                className="d5-chart-line"
              />
              {curveDraw > 0.92 && <circle cx="350" cy="83" r="5" className="d5-chart-end" />}
            </svg>
            <div className="d5-final-tag mono">
              MAKE EVERY CORRECTION COUNT ONCE · SYNCED TO EVERY AGENT
            </div>
          </div>
        )}
      </div>

      {/* Director Scrubber & Transport Controls */}
      <div className="d5-transport">
        <button
          type="button"
          className="d5-icon-btn"
          aria-label={playing ? "Pause film" : "Play film"}
          onClick={() => setPlaying((p) => !p)}
        >
          {playing ? <Pause size={14} /> : <Play size={14} />}
        </button>
        <button
          type="button"
          className="d5-icon-btn"
          aria-label="Restart"
          onClick={() => setFrame(step >= 1 ? (step - 1) * CHAPTER_FRAMES : 0)}
        >
          <RotateCcw size={13} />
        </button>

        <div className="d5-scrubber">
          <input
            type="range"
            min={0}
            max={TOTAL_FRAMES - 1}
            value={frame}
            aria-label="Scrub motion film timeline"
            onChange={(e) => {
              setPlaying(false);
              setFrame(Number(e.target.value));
            }}
          />
          <div className="d5-ch-ticks">
            {CHAPTERS.map((c, idx) => (
              <button
                key={c.id}
                type="button"
                className={idx === chIdx ? "on" : ""}
                onClick={() => setFrame(c.start)}
              >
                0{c.id}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
