import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, CornerUpRight, FileCode2, ShieldAlert, Sparkles, X } from "lucide-react";

/* Approach 1: Morphing Product Artifact ("Real UI in Motion") powered by motion/react.
   Uses layoutId shared-element spring transitions so the exact same T16/T18 decision card
   physically transforms from transcript -> overrule diff -> skill check -> 11-session cluster
   -> interactive governance approval -> live AGENTS.md rule & override drop-off. */

const SPRING = { type: "spring" as const, stiffness: 320, damping: 30, mass: 0.9 };

const HERO_BEATS = [
  { id: 0, label: "1 · Overrule" },
  { id: 1, label: "2 · Pattern" },
  { id: 2, label: "3 · Policy sticks" },
];

export default function Design1Morph({ step }: { step: number }) {
  const [heroBeat, setHeroBeat] = useState(0);
  const [heroPaused, setHeroPaused] = useState(false);

  // Interactive controls for step 5
  const [scope, setScope] = useState<"repo" | "team" | "org">("org");
  const [enforce, setEnforce] = useState<"advice" | "PR check" | "gate">("PR check");
  const [approved, setApproved] = useState(false);

  useEffect(() => {
    if (step !== 0 || heroPaused) return;
    const id = setInterval(() => setHeroBeat((b) => (b + 1) % 3), 3200);
    return () => clearInterval(id);
  }, [step, heroPaused]);

  useEffect(() => {
    if (step !== 5) setApproved(false);
  }, [step]);

  return (
    <div
      className="d1-frame"
      onMouseEnter={() => step === 0 && setHeroPaused(true)}
      onMouseLeave={() => step === 0 && setHeroPaused(false)}
    >
      {/* Window chrome */}
      <div className="d1-chrome">
        <div className="d1-dots" aria-hidden="true">
          <i /><i /><i />
        </div>
        <span className="mono d1-path">
          {step === 0 && "unpack · live governance loop"}
          {step === 1 && "session #482 · transcript → typed decisions"}
          {step === 2 && "turn T18 · human overrule captured"}
          {step === 3 && "verifier · skill check + code graph"}
          {step === 4 && "inbox · cross-team pattern cluster"}
          {step === 5 && "policy P-12 · approval drawer"}
          {step === 6 && "AGENTS.md · published & measured"}
        </span>
        <span className="chip human">P-12</span>
      </div>

      {/* Main animated canvas */}
      <div className="d1-stage">
        <AnimatePresence mode="popLayout" initial={false}>
          {step === 0 && (
            <motion.div
              key="s0"
              className="d1-view"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={SPRING}
            >
              {/* Beat pills */}
              <div className="d1-beats">
                {HERO_BEATS.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    className={heroBeat === b.id ? "on" : ""}
                    onClick={() => {
                      setHeroPaused(true);
                      setHeroBeat(b.id);
                    }}
                  >
                    {b.label}
                  </button>
                ))}
              </div>

              {/* Persistent decision artifact morphing through the 3 hero beats */}
              <motion.div layout layoutId="d1-core-card" className="d1-hero-card" transition={SPRING}>
                <div className="d1-card-head">
                  <span className="chip agent">T16 · agent</span>
                  <span className="mono d1-dim">payments-service · PR #482</span>
                </div>

                <div className={`d1-code-row del ${heroBeat >= 0 ? "struck" : ""}`}>
                  <span>−</span>
                  <code>pip install tenacity</code>
                  <em className="mono">agent proposed</em>
                </div>

                <motion.div
                  layout
                  className="d1-code-row human"
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={SPRING}
                >
                  <CornerUpRight size={14} />
                  <span>“Don't add a library for this. Use stdlib backoff.”</span>
                  <em className="mono">you · T18</em>
                </motion.div>

                {heroBeat >= 1 && (
                  <motion.div
                    layout
                    className="d1-cluster-strip"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={SPRING}
                  >
                    <div className="d1-dots-11">
                      {Array.from({ length: 11 }, (_, i) => (
                        <motion.i
                          key={i}
                          initial={{ scale: 0 }}
                          animate={{ scale: 1 }}
                          transition={{ delay: i * 0.03, ...SPRING }}
                        />
                      ))}
                    </div>
                    <span className="mono">
                      <b>11</b> sessions · 3 teams · 7 devs → <strong className="hot">Policy P-12</strong>
                    </span>
                  </motion.div>
                )}

                {heroBeat >= 2 && (
                  <motion.div
                    layout
                    className="d1-published-strip"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={SPRING}
                  >
                    <div className="d1-md-line">
                      <FileCode2 size={14} />
                      <code>AGENTS.md</code>
                      <span className="chip ok">+1 rule · PR check</span>
                    </div>
                    <div className="d1-metric-drop">
                      <span className="was">11</span>
                      <span className="arr">→</span>
                      <span className="now">3</span>
                      <small className="mono">overrides / 100 sessions</small>
                    </div>
                  </motion.div>
                )}
              </motion.div>

              <div className="d1-hero-foot mono">
                <span>Gemini CLI · Claude Code · Cursor</span>
                <span>Every correction counts once</span>
              </div>
            </motion.div>
          )}

          {step === 1 && (
            <motion.div
              key="s1"
              className="d1-view"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={SPRING}
            >
              <div className="d1-section-k mono">SESSION TRANSCRIPT → TYPED RECORD</div>
              <div className="d1-list">
                {[
                  { t: "T14", who: "agent", text: "Wrap send() with retry middleware", tag: "architecture" },
                  { t: "T16", who: "agent", text: "Add tenacity for exponential backoff", tag: "dependency", shared: true },
                  { t: "T18", who: "human", text: "“Don't add a library for this.”", tag: "redirect", shared: false },
                  { t: "T22", who: "agent", text: "Retrying 5× with jittered backoff", tag: "retries" },
                  { t: "T47", who: "agent", text: "“All done. Full test coverage.”", tag: "claim" },
                ].map((r, i) => (
                  <motion.div
                    key={r.t}
                    layout
                    layoutId={r.shared ? "d1-core-card" : undefined}
                    className={`d1-row ${r.who}`}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.06, ...SPRING }}
                  >
                    <b className="mono">{r.t}</b>
                    <span className={`chip ${r.who}`}>{r.who === "agent" ? "agent" : "you"}</span>
                    <span className="d1-row-txt">{r.text}</span>
                    <em className="mono d1-tag">{r.tag}</em>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}

          {step === 2 && (
            <motion.div
              key="s2"
              className="d1-view"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={SPRING}
            >
              <div className="d1-section-k mono">HUMAN OVERRULE · HIGHEST-SIGNAL TURN</div>
              <motion.div layout layoutId="d1-core-card" className="d1-overrule-card" transition={SPRING}>
                <div className="d1-pair">
                  <div className="d1-box agent">
                    <span className="mono">AGENT PROPOSED · T16</span>
                    <code>+ pip install tenacity</code>
                    <p>Added external runtime dependency for HTTP retry loop.</p>
                  </div>
                  <div className="d1-box human">
                    <span className="mono">HUMAN REDIRECT · T18</span>
                    <code>+ delay = min(2 ** attempt, 30)</code>
                    <p>Kept zero new runtime deps; implemented in 6 lines.</p>
                  </div>
                </div>
                <blockquote className="d1-quote">
                  “Don't add a library for this. Write the backoff with what we already have.”
                </blockquote>
                <div className="d1-meta-pills">
                  <span className="chip human">kind: redirect</span>
                  <span className="chip">type: dependency</span>
                  <span className="chip">area: payments/http</span>
                </div>
              </motion.div>
            </motion.div>
          )}

          {step === 3 && (
            <motion.div
              key="s3"
              className="d1-view"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={SPRING}
            >
              <div className="d1-section-k mono">SKILL ADHERENCE + STATIC GRAPH VERIFICATION</div>
              <motion.div layout layoutId="d1-core-card" className="d1-check-card" transition={SPRING}>
                <div className="d1-check-head">
                  <div>
                    <strong className="d1-big-n">2 of 5</strong>
                    <span className="mono d1-dim"> rules followed</span>
                  </div>
                  <span className="chip bad">3 violations</span>
                </div>

                <div className="d1-rules">
                  {[
                    { ok: false, txt: "No new runtime dependency", turn: "T16" },
                    { ok: true, txt: "Exponential backoff, max 5 retries", turn: "T22" },
                    { ok: false, txt: "Never skip a failing test", turn: "T31" },
                  ].map((r, i) => (
                    <motion.div
                      key={r.turn}
                      className="d1-rule"
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.08, ...SPRING }}
                    >
                      <span className={`d1-badge ${r.ok ? "ok" : "bad"}`}>
                        {r.ok ? <Check size={12} /> : <X size={12} />}
                      </span>
                      <span>{r.txt}</span>
                      <b className="mono">{r.turn}</b>
                    </motion.div>
                  ))}
                </div>

                <div className="d1-claim-box">
                  <div className="d1-claim-top">
                    <ShieldAlert size={15} />
                    <span>Agent claimed: “Full test coverage.”</span>
                    <span className="chip bad">unsupported</span>
                  </div>
                  <div className="d1-graph-mini mono">
                    <span className="ok">Client.send ✓</span>
                    <i>→</i>
                    <span className="ok">_send_single ✓</span>
                    <i>→</i>
                    <span className="bad">Async._send ✕ 0 tests</span>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}

          {step === 4 && (
            <motion.div
              key="s4"
              className="d1-view"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={SPRING}
            >
              <div className="d1-section-k mono">CROSS-SESSION PATTERN DETECTION</div>
              <motion.div layout layoutId="d1-core-card" className="d1-pattern-card" transition={SPRING}>
                <div className="d1-pattern-top">
                  <div>
                    <span className="chip human">policy candidate</span>
                    <h4>Add no new runtime dependency without approval</h4>
                  </div>
                  <div className="d1-count-box">
                    <strong>11</strong>
                    <span className="mono">sessions</span>
                  </div>
                </div>

                <div className="d1-team-grid">
                  {[
                    { team: "payments", sessions: 5, devs: 3, quote: "“Don't add tenacity...”" },
                    { team: "auth", sessions: 4, devs: 2, quote: "“Use built-in jose, no extra pkg”" },
                    { team: "core", sessions: 2, devs: 2, quote: "“Denied pip install httpx-retry”" },
                  ].map((t, i) => (
                    <motion.div
                      key={t.team}
                      className="d1-team-row"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.08, ...SPRING }}
                    >
                      <span className="mono d1-team-name">{t.team}</span>
                      <span className="d1-team-q">{t.quote}</span>
                      <span className="chip human">{t.sessions}× · {t.devs} devs</span>
                    </motion.div>
                  ))}
                </div>

                <div className="d1-threshold mono">
                  Threshold met: ≥ 3 sessions &amp; ≥ 2 developers → queued for tech lead
                </div>
              </motion.div>
            </motion.div>
          )}

          {step === 5 && (
            <motion.div
              key="s5"
              className="d1-view"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={SPRING}
            >
              <div className="d1-section-k mono">INTERACTIVE GOVERNANCE DRAWER · TRY IT</div>
              <motion.div layout layoutId="d1-core-card" className="d1-approve-card" transition={SPRING}>
                <div className="d1-approve-head">
                  <span className="chip human">P-12</span>
                  <span className="mono d1-dim">11 sessions · 3 teams · 7 devs</span>
                </div>
                <h4>Add no new runtime dependency without approval.</h4>

                <div className="d1-ctl">
                  <span className="mono">scope</span>
                  <div className="d1-seg">
                    {(["repo", "team", "org"] as const).map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        className={scope === opt ? "on" : ""}
                        onClick={() => setScope(opt)}
                      >
                        {scope === opt && <motion.i layoutId="d1-scope-pill" transition={SPRING} />}
                        <span>{opt}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="d1-ctl">
                  <span className="mono">enforce</span>
                  <div className="d1-seg">
                    {(["advice", "PR check", "gate"] as const).map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        className={enforce === opt ? "on" : ""}
                        onClick={() => setEnforce(opt)}
                      >
                        {enforce === opt && <motion.i layoutId="d1-enf-pill" transition={SPRING} />}
                        <span>{opt}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="d1-ctl">
                  <span className="mono">expires</span>
                  <span className="mono d1-date-pill">2027-03 · owner @platform</span>
                </div>

                <div className="d1-approve-actions">
                  <button
                    type="button"
                    className={`d1-approve-btn ${approved ? "done" : ""}`}
                    onClick={() => setApproved(true)}
                  >
                    {approved ? (
                      <>
                        <Check size={15} /> Published to AGENTS.md ({scope} · {enforce})
                      </>
                    ) : (
                      <>
                        <Sparkles size={15} /> Approve &amp; Publish P-12
                      </>
                    )}
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}

          {step === 6 && (
            <motion.div
              key="s6"
              className="d1-view"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={SPRING}
            >
              <div className="d1-section-k mono">PUBLISHED TO EVERY AGENT · MEASURED IMPACT</div>
              <motion.div layout layoutId="d1-core-card" className="d1-publish-card" transition={SPRING}>
                <div className="d1-md-box mono">
                  <div className="d1-md-head">
                    <span>skills/dependencies.md</span>
                    <span className="chip ok">synced to 5 agents</span>
                  </div>
                  <div className="d1-md-diff">
                    <span>+</span>
                    <div>
                      <b>## P-12 · No unapproved runtime dependencies</b>
                      <p>Prefer stdlib or existing repo packages. Require @platform approval before adding packages.</p>
                    </div>
                  </div>
                </div>

                <div className="d1-chart-box">
                  <div className="d1-chart-head">
                    <div>
                      <span className="was">11</span>
                      <span className="arr">→</span>
                      <span className="now">3</span>
                    </div>
                    <span className="mono d1-dim">overrides per 100 sessions</span>
                  </div>
                  <svg viewBox="0 0 320 90" className="d1-curve-svg" aria-hidden="true">
                    <line x1="150" y1="6" x2="150" y2="84" className="d1-mark" />
                    <motion.path
                      d="M8 18 L52 22 L98 15 L150 24 L192 52 L236 68 L278 76 L312 79"
                      className="d1-curve-path"
                      initial={{ pathLength: 0 }}
                      animate={{ pathLength: 1 }}
                      transition={{ duration: 1.1, ease: [0.2, 0.8, 0.2, 1] }}
                    />
                    <motion.circle
                      cx="312"
                      cy="79"
                      r="4.5"
                      className="d1-curve-end"
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ delay: 0.95, ...SPRING }}
                    />
                  </svg>
                  <div className="d1-chart-foot mono">
                    <span>before P-12</span>
                    <span className="hot">P-12 published</span>
                    <span className="ok">−73% repeat overrides</span>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
