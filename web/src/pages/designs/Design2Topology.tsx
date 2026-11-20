import { useEffect, useRef, useState } from "react";

/* Approach 2: Living Signal Topology (Canvas 2D physics simulation + Geist Mono HUD overlays).
   Live agent session streams traverse an architectural coordinate grid. Repeated human overrules
   spark in signal yellow; engaging Policy Gate P-12 bends future trajectories cleanly around violations. */

interface Stream {
  id: number;
  team: 0 | 1 | 2;
  baseY: number; // 0..1 normalized lane
  phase: number;
  speed: number;
  violates: boolean;
}

interface Spark {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  maxLife: number;
}

const STREAMS: Stream[] = Array.from({ length: 15 }, (_, i) => ({
  id: i,
  team: (i % 3) as 0 | 1 | 2,
  baseY: 0.16 + ((i % 3) * 0.28) + (Math.floor(i / 3) - 2) * 0.038,
  phase: (i * 0.37) % 1,
  speed: 0.12 + (i % 4) * 0.022,
  violates: i % 3 !== 2 || i === 5 || i === 11,
}));

const TEAM_LABELS = ["payments", "auth", "core"];

function readTokens() {
  const cs = getComputedStyle(document.documentElement);
  const g = (v: string, fb: string) => cs.getPropertyValue(v).trim() || fb;
  return {
    bg: g("--surface", "#fafbfc"),
    sunken: g("--sunken", "#eaedf1"),
    ink: g("--ink", "#1e293b"),
    ink2: g("--ink-2", "#475569"),
    ink3: g("--ink-3", "#64748b"),
    line: g("--line", "rgba(30,41,59,0.12)"),
    line2: g("--line-2", "rgba(30,41,59,0.22)"),
    agent: g("--agent", "#475569"),
    human: g("--human", "#f5b301"),
    humanLine: g("--human-line", "#c98f00"),
    ok: g("--ok", "#1f7a4d"),
    bad: g("--bad", "#b4232f"),
  };
}

export default function Design2Topology({ step }: { step: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [heroPolicyOn, setHeroPolicyOn] = useState(true);
  const [autoCycle, setAutoCycle] = useState(true);
  const [liveOverrides, setLiveOverrides] = useState(3);

  const stateRef = useRef({
    step,
    heroPolicyOn,
    autoCycle,
    gateStrength: 0,
    zoom: 1,
    focusX: 0.5,
    focusY: 0.5,
    scanX: 0,
    sparks: [] as Spark[],
    t: 0,
  });

  stateRef.current.step = step;
  stateRef.current.heroPolicyOn = heroPolicyOn;
  stateRef.current.autoCycle = autoCycle;

  // In hero step 0, smoothly alternate policy OFF (chaos: 11 overrides) -> ON (governed: 3 overrides)
  useEffect(() => {
    if (step !== 0 || !autoCycle) return;
    const id = setInterval(() => setHeroPolicyOn((v) => !v), 5200);
    return () => clearInterval(id);
  }, [step, autoCycle]);

  useEffect(() => {
    const active = step === 6 || (step === 0 && heroPolicyOn);
    setLiveOverrides(active ? 3 : 11);
  }, [step, heroPolicyOn]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let last = performance.now();
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const st = stateRef.current;
      if (!reduced) st.t += dt;

      const W = canvas.clientWidth || 560;
      const H = canvas.clientHeight || 520;
      const tk = readTokens();

      const curStep = st.step;
      const targetGate = curStep === 6 || curStep === 5 || (curStep === 0 && st.heroPolicyOn) ? 1 : 0;
      const targetZoom = curStep === 1 || curStep === 2 ? 1.55 : curStep === 3 ? 1.3 : 1.0;
      const targetFocusX = curStep === 1 ? 0.36 : curStep === 2 ? 0.5 : curStep === 3 ? 0.48 : 0.5;
      const targetFocusY = curStep === 1 || curStep === 2 || curStep === 3 ? 0.44 : 0.5;

      const lerp = (a: number, b: number, k: number) => a + (b - a) * Math.min(1, dt * k);
      st.gateStrength = lerp(st.gateStrength, targetGate, 4.5);
      st.zoom = lerp(st.zoom, targetZoom, 4.0);
      st.focusX = lerp(st.focusX, targetFocusX, 4.0);
      st.focusY = lerp(st.focusY, targetFocusY, 4.0);
      st.scanX = (st.scanX + dt * 0.32) % 1;

      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = tk.bg;
      ctx.fillRect(0, 0, W, H);

      ctx.save();
      // Smooth camera transform
      ctx.translate(W * 0.5, H * 0.5);
      ctx.scale(st.zoom, st.zoom);
      ctx.translate(-W * st.focusX, -H * st.focusY);

      // 1. Subtle architectural grid
      ctx.strokeStyle = tk.line;
      ctx.lineWidth = 1 / st.zoom;
      const cols = 12;
      const rows = 10;
      for (let i = 1; i < cols; i++) {
        const x = (i / cols) * W;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, H);
        ctx.stroke();
      }
      for (let j = 1; j < rows; j++) {
        const y = (j / rows) * H;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(W, y);
        ctx.stroke();
      }

      // Team lane bands on steps 0, 4, 5, 6
      if (curStep === 0 || curStep >= 4) {
        [0.16, 0.44, 0.72].forEach((ly, idx) => {
          ctx.fillStyle = tk.ink3;
          ctx.font = `500 10px "Geist Mono", monospace`;
          ctx.globalAlpha = 0.65;
          ctx.fillText(TEAM_LABELS[idx].toUpperCase(), 14, ly * H - 24);
          ctx.globalAlpha = 1;
        });
      }

      // Violation zone at x = 0.52 (representing "+ pip install tenacity")
      const gateX = W * 0.52;
      const gateY = H * 0.44;

      // Dashed vertical rule axis
      ctx.save();
      ctx.setLineDash([4, 5]);
      ctx.strokeStyle = st.gateStrength > 0.45 ? tk.humanLine : tk.line2;
      ctx.lineWidth = 1.2 / st.zoom;
      ctx.beginPath();
      ctx.moveTo(gateX, 24);
      ctx.lineTo(gateX, H - 24);
      ctx.stroke();
      ctx.restore();

      // Step 3: sweeping verification scanline
      if (curStep === 3) {
        const sx = W * (0.14 + st.scanX * 0.72);
        const grad = ctx.createLinearGradient(sx - 36, 0, sx + 4, 0);
        grad.addColorStop(0, "transparent");
        grad.addColorStop(1, "rgba(245, 179, 1, 0.22)");
        ctx.fillStyle = grad;
        ctx.fillRect(sx - 36, 0, 40, H);
        ctx.strokeStyle = tk.human;
        ctx.lineWidth = 1.5 / st.zoom;
        ctx.beginPath();
        ctx.moveTo(sx, 0);
        ctx.lineTo(sx, H);
        ctx.stroke();
      }

      // 2. Session trajectories
      const focusIdx = 4; // primary hero session
      STREAMS.forEach((s, idx) => {
        const isPrimary = idx === focusIdx;
        const dim = (curStep === 1 || curStep === 2 || curStep === 3) && !isPrimary;
        const y0 = s.baseY * H;

        // Curve path: if violating and gate is OFF -> dips into violation zone & bends sharply;
        // if gate is ON -> deflects smoothly into clean corridor
        const bend = s.violates
          ? st.gateStrength > 0.5
            ? -26 * st.gateStrength
            : 28 * (1 - st.gateStrength * 0.8)
          : 0;

        ctx.beginPath();
        const stepsN = 40;
        for (let k = 0; k <= stepsN; k++) {
          const u = k / stepsN;
          const x = u * W;
          // Gaussian bump centered at u = 0.52
          const d = (u - 0.52) / 0.13;
          const bell = Math.exp(-d * d);
          // Slight wave motion
          const wave = Math.sin(u * 9 + st.t * 1.4 + s.id) * (dim ? 1.5 : 3);
          let y = y0 + wave;

          if (s.violates) {
            if (curStep === 4) {
              // Step 4: pull violating streams toward central cluster point
              y = y * (1 - bell * 0.55) + gateY * (bell * 0.55);
            } else {
              // Before gate: dips down toward hazard; after gate: routes cleanly above
              const after = u > 0.52 ? 1 / (1 + Math.exp(-(u - 0.52) * 24)) : 0;
              y += bell * bend + after * (st.gateStrength > 0.5 ? -8 : 10);
            }
          }
          if (k === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }

        ctx.strokeStyle =
          isPrimary && curStep === 2
            ? tk.humanLine
            : s.violates && st.gateStrength > 0.65 && (curStep === 6 || curStep === 0)
              ? tk.ok
              : tk.agent;
        ctx.globalAlpha = dim ? 0.14 : isPrimary ? 0.92 : s.violates ? 0.58 : 0.28;
        ctx.lineWidth = (isPrimary ? 2.4 : 1.35) / st.zoom;
        ctx.stroke();

        // Moving packet along each stream
        const u = (s.phase + st.t * s.speed) % 1;
        const px = u * W;
        const d = (u - 0.52) / 0.13;
        const bell = Math.exp(-d * d);
        const wave = Math.sin(u * 9 + st.t * 1.4 + s.id) * (dim ? 1.5 : 3);
        let py = y0 + wave;
        if (s.violates) {
          if (curStep === 4) {
            py = py * (1 - bell * 0.55) + gateY * (bell * 0.55);
          } else {
            const after = u > 0.52 ? 1 / (1 + Math.exp(-(u - 0.52) * 24)) : 0;
            py += bell * bend + after * (st.gateStrength > 0.5 ? -8 : 10);
          }
        }

        // Spawn yellow human-overrule sparks when a violating packet crosses x=0.52 with gate OFF
        if (!reduced && !dim && s.violates && st.gateStrength < 0.4 && Math.abs(u - 0.52) < 0.012 && Math.random() < 0.55) {
          for (let sp = 0; sp < 3; sp++) {
            const a = Math.random() * Math.PI * 2;
            const spd = 25 + Math.random() * 55;
            st.sparks.push({ x: px, y: py, vx: Math.cos(a) * spd, vy: Math.sin(a) * spd, life: 0, maxLife: 0.5 + Math.random() * 0.4 });
          }
        }

        // Packet dot
        const pastGate = u > 0.52;
        const isYellow = s.violates && pastGate && st.gateStrength < 0.5;
        const isGreen = s.violates && pastGate && st.gateStrength >= 0.5;
        ctx.globalAlpha = dim ? 0.2 : 1;
        ctx.fillStyle = isYellow ? tk.human : isGreen ? tk.ok : tk.agent;
        ctx.beginPath();
        ctx.arc(px, py, (isPrimary ? 4.4 : 2.8) / st.zoom, 0, Math.PI * 2);
        ctx.fill();

        // Step 1, 2, 3: discrete turn markers on primary stream
        if (isPrimary && (curStep === 1 || curStep === 2 || curStep === 3)) {
          const turns = [
            { u: 0.22, t: "T14", who: "agent", ok: true },
            { u: 0.42, t: "T16", who: "agent", ok: false },
            { u: 0.52, t: "T18", who: "human", ok: true },
            { u: 0.68, t: "T22", who: "agent", ok: true },
            { u: 0.82, t: "T47", who: "agent", ok: false },
          ];
          turns.forEach((tn) => {
            const tx = tn.u * W;
            const td = (tn.u - 0.52) / 0.13;
            const tbell = Math.exp(-td * td);
            const ty = y0 + Math.sin(tn.u * 9 + st.t * 1.4 + s.id) * 3 + tbell * bend;

            if (tn.who === "human") {
              // Pulsing human overrule ring
              const pulse = 10 + Math.sin(st.t * 4) * 3;
              ctx.strokeStyle = tk.human;
              ctx.lineWidth = 1.6 / st.zoom;
              ctx.globalAlpha = 0.5;
              ctx.beginPath();
              ctx.arc(tx, ty, pulse / st.zoom, 0, Math.PI * 2);
              ctx.stroke();
            }

            ctx.globalAlpha = 1;
            ctx.fillStyle =
              curStep === 3
                ? tn.ok
                  ? tk.ok
                  : tk.bad
                : tn.who === "human"
                  ? tk.human
                  : tk.agent;
            ctx.beginPath();
            ctx.arc(tx, ty, (tn.who === "human" ? 6 : 4.6) / st.zoom, 0, Math.PI * 2);
            ctx.fill();

            ctx.fillStyle = tk.ink;
            ctx.font = `600 ${9.5 / st.zoom}px "Geist Mono", monospace`;
            ctx.fillText(tn.t, tx - 9 / st.zoom, ty - 11 / st.zoom);
          });
        }
      });

      // 3. Draw human-overrule sparks
      for (let i = st.sparks.length - 1; i >= 0; i--) {
        const sp = st.sparks[i];
        sp.life += dt;
        if (sp.life >= sp.maxLife) {
          st.sparks.splice(i, 1);
          continue;
        }
        sp.x += sp.vx * dt;
        sp.y += sp.vy * dt;
        const alpha = 1 - sp.life / sp.maxLife;
        ctx.globalAlpha = alpha;
        ctx.fillStyle = tk.human;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, (2.6 * alpha + 0.8) / st.zoom, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      // 4. Policy Gate / Cluster Node at (gateX, gateY)
      if (curStep === 4) {
        // Golden resonance rings pulling 11 sessions together
        for (let r = 0; r < 3; r++) {
          const rr = 18 + ((st.t * 28 + r * 20) % 58);
          ctx.strokeStyle = tk.human;
          ctx.globalAlpha = Math.max(0, 1 - rr / 76) * 0.65;
          ctx.lineWidth = 1.6;
          ctx.beginPath();
          ctx.arc(gateX, gateY, rr, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
        ctx.fillStyle = tk.human;
        ctx.beginPath();
        ctx.arc(gateX, gateY, 16, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#1e293b";
        ctx.font = `600 11px "Geist Mono", monospace`;
        ctx.textAlign = "center";
        ctx.fillText("11×", gateX, gateY + 4);
        ctx.textAlign = "start";
      } else if (st.gateStrength > 0.08) {
        // Crisp Policy Gate pill on the vertical axis
        const r = 18 + st.gateStrength * 6;
        ctx.save();
        ctx.globalAlpha = st.gateStrength;
        ctx.strokeStyle = curStep === 6 || (curStep === 0 && st.heroPolicyOn) ? tk.ok : tk.human;
        ctx.lineWidth = 2 / st.zoom;
        ctx.beginPath();
        ctx.arc(gateX, gateY, r + Math.sin(st.t * 3) * 2.5, 0, Math.PI * 2);
        ctx.stroke();

        ctx.fillStyle = tk.human;
        ctx.beginPath();
        ctx.roundRect(gateX - 24, gateY - 13, 48, 26, 13);
        ctx.fill();
        ctx.fillStyle = "#1e293b";
        ctx.font = `600 11px "Geist Mono", monospace`;
        ctx.textAlign = "center";
        ctx.fillText("P-12", gateX, gateY + 4);
        ctx.textAlign = "start";
        ctx.restore();
      }

      // 5. Feedback loop arc on step 6 & governed hero
      if (st.gateStrength > 0.5 && (curStep === 6 || curStep === 0)) {
        ctx.save();
        ctx.globalAlpha = st.gateStrength * 0.7;
        ctx.strokeStyle = tk.humanLine;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 6]);
        ctx.lineDashOffset = -st.t * 28;
        ctx.beginPath();
        ctx.moveTo(gateX + 26, gateY);
        ctx.bezierCurveTo(W * 0.85, H * 0.94, W * 0.15, H * 0.94, W * 0.08, gateY);
        ctx.stroke();
        ctx.restore();
      }

      ctx.restore();
      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  const hud = (() => {
    switch (step) {
      case 1:
        return { tag: "SESSION #482 · LIVE STREAM", title: "Every agent & human turn pinned", sub: "T14 architecture · T16 dependency · T18 human redirect" };
      case 2:
        return { tag: "T18 · HUMAN DEFLECTION", title: "“Don't add a library for this.”", sub: "Agent path bent off tenacity → stdlib backoff" };
      case 3:
        return { tag: "DETERMINISTIC VERIFICATION", title: "2 of 5 skill rules followed", sub: "T16 violated · T47 “Full test coverage” unsupported" };
      case 4:
        return { tag: "CROSS-TEAM SIGNAL CLUSTER", title: "11 identical overrules detected", sub: "3 teams · 7 developers → promoted to policy candidate" };
      case 5:
        return { tag: "POLICY GATE P-12 · LOCKED", title: "Scope: org · Enforce: PR check", sub: "Ready to publish to AGENTS.md across all repos" };
      case 6:
        return { tag: "CLOSED FEEDBACK LOOP", title: "Overrides dropped 11 → 3 / 100", sub: "Future agent trajectories self-correct at gate P-12" };
      default:
        return heroPolicyOn
          ? { tag: "POLICY P-12 ACTIVE · AGENTS.MD", title: "Trajectories self-correct automatically", sub: "Overrides dropped 11 → 3 per 100 sessions" }
          : { tag: "WITHOUT GOVERNANCE · LIVE DRIFT", title: "Humans repeat the same overrule", sub: "11 yellow friction sparks across 3 teams" };
    }
  })();

  return (
    <div className="d2-root">
      <div className="d2-topbar">
        <span className="d2-dot-live" />
        <span className="mono d2-top-label">{hud.tag}</span>
        {step === 0 ? (
          <button
            type="button"
            className={`d2-toggle ${heroPolicyOn ? "on" : ""}`}
            onClick={() => {
              setAutoCycle(false);
              setHeroPolicyOn((v) => !v);
            }}
          >
            {heroPolicyOn ? "Policy P-12: ON" : "Policy P-12: OFF"}
          </button>
        ) : (
          <span className="mono d2-top-metric">
            <strong className={liveOverrides === 3 ? "ok" : "hot"}>{liveOverrides}</strong> / 100 overrides
          </span>
        )}
      </div>

      <canvas ref={canvasRef} className="d2-canvas" aria-label="Live signal topology showing agent session streams converging into a governance policy gate" />

      <div className="d2-hud-card">
        <div className="d2-hud-main">
          <strong>{hud.title}</strong>
          <span>{hud.sub}</span>
        </div>
        <div className="d2-hud-stat">
          <span className="d2-was">11</span>
          <i>→</i>
          <span className={liveOverrides === 3 ? "d2-now" : "d2-was"}>{liveOverrides}</span>
        </div>
      </div>
    </div>
  );
}
