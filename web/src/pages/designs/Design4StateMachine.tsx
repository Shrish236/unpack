import { useEffect, useRef, useState } from "react";

/* Approach 4: Bespoke Editorial Vector State Machine (Rive-style procedural state machine).
   Extends Unpack's own <Mark /> motif (overlapping slate & signal-yellow rounded planes) into
   a spring-interpolated geometric motion illustration with continuous state blending, mechanical
   overrule recoil, 11-tile magnetic flocking into seal P-12, and interactive state inputs. */

interface SMRenderState {
  stepBlend: number;
  recoil: number;       // 0..1 human overrule stamp impact
  scanPos: number;      // 0..1 verification sweep
  clusterPull: number;  // 0..1 11 micro-marks flocking to center
  sealLock: number;     // 0..1 policy P-12 embossed seal
  loopFlow: number;     // continuous phase for ribbon flow
  px: number;
  py: number;
  heroPhase: number;    // 0..3 continuous hero choreography
}

const MICRO_SEEDS = Array.from({ length: 11 }, (_, i) => {
  const angle = (i / 11) * Math.PI * 2 - Math.PI / 2;
  const dist = 122 + (i % 3) * 18;
  return {
    id: i,
    sx: 220 + Math.cos(angle) * dist,
    sy: 200 + Math.sin(angle) * dist * 0.78,
    tx: 220 + ((i % 4) - 1.5) * 20,
    ty: 200 + (Math.floor(i / 4) - 1) * 20,
  };
});

export default function Design4StateMachine({ step }: { step: number }) {
  const [pulseCount, setPulseCount] = useState(0);
  const [smState, setSmState] = useState<SMRenderState>({
    stepBlend: 0,
    recoil: 0,
    scanPos: 0,
    clusterPull: 0,
    sealLock: 0,
    loopFlow: 0,
    px: 0,
    py: 0,
    heroPhase: 0,
  });

  const targetRef = useRef({ step, px: 0, py: 0, recoilKick: 0, sealKick: 0 });
  targetRef.current.step = step;

  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    const cur: SMRenderState = {
      stepBlend: step,
      recoil: 0,
      scanPos: 0,
      clusterPull: 0,
      sealLock: 0,
      loopFlow: 0,
      px: 0,
      py: 0,
      heroPhase: 0,
    };

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const tg = targetRef.current;
      const s = tg.step;

      if (!reduced) {
        cur.heroPhase = (cur.heroPhase + dt * 0.34) % 3;
        cur.loopFlow = (cur.loopFlow + dt * 42) % 100;
        cur.scanPos = (cur.scanPos + dt * 0.55) % 1;
      }

      const heroBeat = Math.floor(cur.heroPhase);
      const wantRecoil = s === 2 || (s === 0 && heroBeat >= 0) ? 1 : 0;
      const wantCluster = s === 4 || (s === 0 && heroBeat >= 1) ? 1 : 0;
      const wantSeal = s === 5 || s === 6 || (s === 0 && heroBeat >= 2) ? 1 : 0;

      const lerp = (a: number, b: number, k: number) => a + (b - a) * Math.min(1, dt * k);
      cur.stepBlend = lerp(cur.stepBlend, s, 6);
      cur.recoil = lerp(cur.recoil, Math.min(1, wantRecoil + tg.recoilKick), 7);
      cur.clusterPull = lerp(cur.clusterPull, wantCluster, 5);
      cur.sealLock = lerp(cur.sealLock, Math.min(1, wantSeal + tg.sealKick), 6);
      cur.px = lerp(cur.px, tg.px, 8);
      cur.py = lerp(cur.py, tg.py, 8);

      tg.recoilKick = Math.max(0, tg.recoilKick - dt * 2.5);
      tg.sealKick = Math.max(0, tg.sealKick - dt * 2.5);

      setSmState({ ...cur });
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    targetRef.current.px = ((e.clientX - r.left) / r.width - 0.5) * 14;
    targetRef.current.py = ((e.clientY - r.top) / r.height - 0.5) * 14;
  };
  const onLeave = () => {
    targetRef.current.px = 0;
    targetRef.current.py = 0;
  };

  const triggerOverrule = () => {
    targetRef.current.recoilKick = 1.4;
    setPulseCount((c) => c + 1);
  };
  const triggerSeal = () => {
    targetRef.current.sealKick = 1.4;
    setPulseCount((c) => c + 1);
  };

  const heroBeat = Math.floor(smState.heroPhase);
  const agentShift = -26 * smState.recoil;
  const humanDrop = (1 - smState.recoil) * -32;

  const caption = (() => {
    if (step === 1) return { k: "STATE: RECORD_TRANSCRIPT", title: "Dual-voice geometric ledger", val: "T14 · T16 · T18 · T22" };
    if (step === 2) return { k: "STATE: OVERRULE_STAMP", title: "Human plane displaces agent proposal", val: "“Don't add a library”" };
    if (step === 3) return { k: "STATE: VERIFY_RULES", title: "Deterministic scanner checks 5 rules", val: "2 ✓ · 3 ✕" };
    if (step === 4) return { k: "STATE: CLUSTER_CONVERGE", title: "11 matching overrules flock to center", val: "3 teams · 7 devs" };
    if (step === 5) return { k: "STATE: SEAL_APPROVE", title: "Tech lead stamps Policy P-12", val: "org · PR check" };
    if (step === 6) return { k: "STATE: PUBLISH_LOOP", title: "Rule prints into AGENTS.md continuously", val: "11 → 3 / 100" };
    return {
      k: `STATE MACHINE · BEAT ${heroBeat + 1}/3`,
      title: heroBeat === 0 ? "Human plane overrides agent choice" : heroBeat === 1 ? "11 repeat overrules cluster" : "Policy P-12 sticks across every agent",
      val: heroBeat === 2 ? "11 → 3 overrides" : "interactive · hover or trigger",
    };
  })();

  return (
    <div className="d4-root" onPointerMove={onMove} onPointerLeave={onLeave}>
      <div className="d4-head">
        <span className="mono d4-sm-badge">
          <i /> {caption.k}
        </span>
        <span className="mono d4-val">{caption.val}</span>
      </div>

      <svg className="d4-svg" viewBox="0 0 440 400" role="img" aria-label="Editorial vector state machine illustrating Unpack's governance loop">
        <defs>
          <pattern id="d4-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M 24 0 L 0 0 0 24" fill="none" className="d4-grid-line" />
          </pattern>
        </defs>

        {/* Precision Swiss grid background */}
        <rect x="0" y="0" width="440" height="400" fill="url(#d4-grid)" />

        {/* Orbital governance feedback track (visible on step 0 beat 2 & step 6) */}
        <g opacity={step === 6 || (step === 0 && heroBeat === 2) ? 0.9 : 0.16}>
          <rect x="44" y="42" width="352" height="316" rx="34" className="d4-orbit" />
          <rect
            x="44"
            y="42"
            width="352"
            height="316"
            rx="34"
            className="d4-orbit-pulse"
            strokeDasharray="48 1200"
            strokeDashoffset={-smState.loopFlow * 12.5}
          />
        </g>

        {/* Step 4 & Hero Beat 1: 11 yellow micro-squares magnetically flocking */}
        <g opacity={step === 4 || (step === 0 && heroBeat >= 1) ? 1 : 0} style={{ transition: "opacity 0.35s" }}>
          {MICRO_SEEDS.map((m) => {
            const k = smState.clusterPull;
            const x = m.sx + (m.tx - m.sx) * k + smState.px * 0.35;
            const y = m.sy + (m.ty - m.sy) * k + smState.py * 0.35;
            return (
              <g key={m.id}>
                <line x1={m.sx} y1={m.sy} x2={x} y2={y} className="d4-flock-line" opacity={1 - k * 0.7} />
                <rect x={x - 7} y={y - 7} width="14" height="14" rx="3.5" className="d4-micro" />
              </g>
            );
          })}
        </g>

        {/* Central overlapping <Mark /> composition (Agent slate plane + Human yellow plane) */}
        <g transform={`translate(${smState.px * 0.5}, ${smState.py * 0.5})`}>
          {/* Agent Plane (Slate) */}
          <g transform={`translate(${126 + agentShift}, 116)`}>
            <rect width="128" height="128" rx="22" className="d4-plane-agent" opacity={step === 2 ? 0.52 : 0.94} />
            <text x="18" y="30" className="d4-mono-sm on-agent">AGENT · T16</text>
            <line x1="18" y1="54" x2="106" y2="54" className="d4-bar on-agent" />
            <line x1="18" y1="72" x2="86" y2="72" className="d4-bar on-agent" />
            <line x1="18" y1="90" x2="96" y2="90" className="d4-bar on-agent" />
            {smState.recoil > 0.4 && (
              <line x1="14" y1="54" x2="112" y2="54" className="d4-strike" />
            )}
            <text x="18" y="114" className="d4-mono-xs on-agent">+ tenacity</text>
          </g>

          {/* Human Plane (Signal Yellow — overlaps like Unpack's logo mark) */}
          <g transform={`translate(${184 + smState.px * 0.35}, ${154 + humanDrop + smState.py * 0.35})`}>
            <rect width="138" height="138" rx="24" className="d4-plane-human" />
            <text x="18" y="30" className="d4-mono-sm on-human">HUMAN · T18</text>
            <text x="18" y="62" className="d4-sans-md on-human">“Don't add</text>
            <text x="18" y="82" className="d4-sans-md on-human">a library.”</text>
            <rect x="18" y="100" width="76" height="22" rx="11" className="d4-pill-ink" />
            <text x="56" y="114.5" textAnchor="middle" className="d4-mono-xs on-pill">REDIRECT</text>
          </g>
        </g>

        {/* Step 3: Mechanical scanner & verdict ticks */}
        {step === 3 && (
          <g>
            <line
              x1={76 + smState.scanPos * 288}
              y1="66"
              x2={76 + smState.scanPos * 288}
              y2="334"
              className="d4-scan-beam"
            />
            {[
              { x: 112, y: 92, ok: false, label: "T16 dep" },
              { x: 220, y: 92, ok: true, label: "T22 retry" },
              { x: 328, y: 92, ok: false, label: "T47 claim" },
            ].map((b) => (
              <g key={b.label} transform={`translate(${b.x}, ${b.y})`}>
                <rect x="-42" y="-15" width="84" height="30" rx="15" className={`d4-vbadge ${b.ok ? "ok" : "bad"}`} />
                <text y="4" textAnchor="middle" className={`d4-mono-xs ${b.ok ? "ok" : "bad"}`}>
                  {b.ok ? "✓" : "✕"} {b.label}
                </text>
              </g>
            ))}
          </g>
        )}

        {/* Steps 5, 6 & Hero Beat 2: Embossed Policy Seal P-12 + AGENTS.md ribbon */}
        <g
          transform={`translate(220, 200) scale(${0.5 + smState.sealLock * 0.5})`}
          opacity={step === 5 || step === 6 || (step === 0 && heroBeat === 2) ? smState.sealLock : 0}
        >
          <circle r="66" className="d4-seal-ring" />
          <circle r="54" className="d4-seal-core" />
          <text y="-10" textAnchor="middle" className="d4-mono-xs on-human">POLICY SEALED</text>
          <text y="16" textAnchor="middle" className="d4-seal-big">P-12</text>
          <text y="34" textAnchor="middle" className="d4-mono-xs on-human">AGENTS.MD</text>
        </g>

        {/* Bottom impact bar on step 6 */}
        {step === 6 && (
          <g transform="translate(88, 312)">
            <rect width="264" height="38" rx="19" className="d4-impact-pill" />
            <text x="132" y="23" textAnchor="middle" className="d4-mono-sm on-impact">
              OVERRIDES / 100 SESSIONS: 11 → 3 (−73%)
            </text>
          </g>
        )}
      </svg>

      {/* Interactive State Machine Inputs Footer */}
      <div className="d4-controls">
        <div className="d4-cap">
          <strong>{caption.title}</strong>
          <span className="mono">inputs: step={step} · pulses={pulseCount}</span>
        </div>
        <div className="d4-btns">
          <button type="button" onClick={triggerOverrule}>Trigger Overrule</button>
          <button type="button" className="primary" onClick={triggerSeal}>Stamp P-12</button>
        </div>
      </div>
    </div>
  );
}
