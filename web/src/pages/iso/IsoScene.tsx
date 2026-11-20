import { useId, useMemo, useRef, type CSSProperties, type ReactNode } from "react";
import {
  AGENT, CONV, CUBE, CUBES, COLS, GATE, H, MICRO_TILES, P, PAD, PILE, ROWS, SKILL, SLAB, W,
  T, faces, pts, px, py, quad, type Callout, type Cube, type XY,
} from "./iso";
import "../../styles/iso.css";

/* The single figure of the home page: an isometric diorama of the decision record and its governance.
   Everything is SVG + CSS. Default styles are the finished state; animations only play under [data-step]. */

const css = (o: Record<string, string | number>) => o as CSSProperties;
const px0 = (n: number) => `${n.toFixed(1)}px`;

function Faces({ w, d, h }: { w: number; d: number; h: number }) {
  const f = faces(w, d, h);
  return (<><polygon className="fl" points={f.l} /><polygon className="fr" points={f.r} /><polygon className="ft" points={f.t} /></>);
}

/** A group placed at a world point (min corner of its base). */
function At({ x, y, z = 0, className, style, children }: { x: number; y: number; z?: number; className?: string; style?: CSSProperties; children?: ReactNode }) {
  const [sx, sy] = P(x, y, z);
  return <g className={className} style={{ transform: `translate(${px0(sx)}, ${px0(sy)})`, ...style }}>{children}</g>;
}

const diamond = ([cx, cy]: XY, rx = 6, ry = 3.2) => pts([[cx, cy - ry], [cx + rx, cy], [cx, cy + ry], [cx - rx, cy]]);

// step 3: the gate passes a cube when its x is reached, over 3 s
const gateDelay = (c: Cube) => 0.3 + ((c.tx + 0.5 - GATE.start) / (GATE.rest - GATE.start)) * 3.2;

function cubePos(c: Cube, bumped: boolean): XY {
  const [bx, by] = bumped && c.bump ? c.bump : [0, 0];
  return P(c.tx + CUBE.inset + bx, c.ty + CUBE.inset + by, CUBE.base);
}

function callouts(step: number): Callout[] {
  const a2 = P(1.5, 1.5, 0.68), h1 = P(2.5, 1.5, 0.68);
  const gate = P(GATE.rest, 2, 1.6), pad = P(PAD.cx, PAD.cy, 0.3), skill = P(SKILL.x + SKILL.w / 2, SKILL.y + SKILL.d / 2, SKILL.h);
  switch (step) {
    case 1: return [
      { key: "c1", ax: 205, ay: 84, side: "r", tx: a2[0], ty: a2[1] },
      { key: "c2", ax: 352, ay: 70, side: "l", tx: h1[0], ty: h1[1], sec: true },
    ];
    case 2: return [{ key: "c1", ax: 352, ay: 74, side: "l", tx: h1[0], ty: h1[1] }];
    case 3: return [{ key: "c1", ax: 420, ay: 130, side: "b", tx: gate[0], ty: gate[1] }];
    case 4: return [{ key: "c1", ax: 205, ay: 330, side: "r", tx: pad[0] - 24, ty: pad[1] + 4 }];
    case 5: return [{ key: "c1", ax: 212, ay: 322, side: "r", tx: pad[0] - 30, ty: pad[1] - 12 }];
    case 6: return [{ key: "c1", ax: 205, ay: 440, side: "r", tx: skill[0] - 34, ty: skill[1] + 14 }];
    default: return [];
  }
}

function CalloutBody({ step, k }: { step: number; k: string }) {
  if (step === 1 && k === "c1") return <><span className="iso-k">T16 · agent · Dependency</span><span>Adds tenacity, nobody asked</span></>;
  if (step === 1 && k === "c2") return <><span className="iso-k iso-k-h">T18 · you · Redirect</span><span>“Don't add a library”</span></>;
  if (step === 2) return <><span className="iso-k iso-k-h"><i className="chip human">redirect</i> T18</span><span className="iso-q">“Don't add a library for this.”</span><span className="iso-dim">The agent's choice is struck. Yours is on the record.</span></>;
  if (step === 3) return <><span className="iso-k">Skill check</span><span className="iso-row"><b>2 of 5</b> rules followed</span><span className="iso-row"><i className="iso-tk ok">✓</i>2 <i className="iso-tk bad">✕</i>3</span></>;
  if (step === 4) return <><span className="iso-k iso-k-h">Same overrule</span><span className="iso-row"><b>11</b> sessions</span><span className="iso-dim">3 teams · 7 developers</span><i className="chip human">candidate</i></>;
  if (step === 5) return (
    <>
      <span className="iso-k iso-k-h">Policy P-12</span>
      <span className="iso-form"><em>scope</em> org</span>
      <span className="iso-form"><em>enforce</em> PR check</span>
      <span className="iso-form"><em>expires</em> 2027-03</span>
      <span className="iso-btn">Approve</span>
    </>
  );
  if (step === 6) return <><span className="iso-k">Overrides per 100 sessions</span><span className="iso-row iso-big"><b className="was">11</b> → <b className="now">3</b></span><span className="iso-dim">Published to every agent's skills</span></>;
  return null;
}

export default function IsoScene({ step }: { step: number }) {
  const s = Math.max(0, Math.min(6, Math.round(step)));
  const fid = useId().replace(/:/g, "");
  const root = useRef<HTMLDivElement>(null);

  // pointer parallax, fine pointers only, and never with reduced motion
  const fine = useMemo(() => typeof matchMedia === "function" && matchMedia("(hover: hover) and (pointer: fine)").matches && !matchMedia("(prefers-reduced-motion: reduce)").matches, []);
  const move = (e: React.PointerEvent) => {
    if (!fine || !root.current) return;
    const r = root.current.getBoundingClientRect();
    root.current.style.setProperty("--px", (((e.clientX - r.left) / r.width - 0.5) * 2).toFixed(3));
    root.current.style.setProperty("--py", (((e.clientY - r.top) / r.height - 0.5) * 2).toFixed(3));
  };
  const leave = () => { root.current?.style.setProperty("--px", "0"); root.current?.style.setProperty("--py", "0"); };

  const bumpedNow = (c: Cube) => !!c.bump && (c.id === "a2" ? s !== 1 : s >= 2); // a2 in the overview loop starts un-bumped; see css
  const ordered = [...CUBES].sort((a, b) => a.tx + a.ty - (b.tx + b.ty));
  const padPx = P(PAD.cx, PAD.cy), skillPx = P(SKILL.x + SKILL.w / 2, SKILL.y + SKILL.d / 2);
  const gateSweep = P(GATE.start, 0).map((v, i) => v - P(GATE.rest, 0)[i]) as XY;
  const cs = callouts(s).map((c) => { const [ax, ay] = T([c.ax, c.ay]); return { ...c, ax, ay }; });
  const lp = (a: XY) => T(a).map((v) => v.toFixed(1)).join(" ");
  const convS = P(...CONV.s), convE = P(...CONV.e);
  const sk = [SKILL.x, SKILL.y] as const;

  return (
    <div className="iso" data-step={s} ref={root} onPointerMove={move} onPointerLeave={leave}>
      <svg className="iso-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Isometric diagram: decisions from a session are recorded, checked by governance, approved as policy and published back to the agent">
        <defs><filter id={`${fid}b`} x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7" /></filter></defs>

        <g className="ly ly-ground" style={css({ "--d": 1 })} aria-hidden="true">
          <g filter={`url(#${fid}b)`} className="iso-shadow">
            <polygon points={quad([-0.2, -0.2, 0], [6.2, -0.2, 0], [6.2, 4.2, 0], [-0.2, 4.2, 0])} transform="translate(8 12)" />
            <polygon points={quad([SLAB.x - 0.2, SLAB.y - 0.2, 0], [SLAB.x + SLAB.w + 0.3, SLAB.y - 0.2, 0], [SLAB.x + SLAB.w + 0.3, SLAB.y + SLAB.d + 0.3, 0], [SLAB.x - 0.2, SLAB.y + SLAB.d + 0.3, 0])} transform="translate(6 9)" />
            <polygon points={quad([sk[0], sk[1], 0], [sk[0] + SKILL.w, sk[1], 0], [sk[0] + SKILL.w, sk[1] + SKILL.d, 0], [sk[0], sk[1] + SKILL.d, 0])} transform="translate(6 9)" />
            <polygon points={quad([AGENT.x, AGENT.y, 0], [AGENT.x + AGENT.w, AGENT.y, 0], [AGENT.x + AGENT.w, AGENT.y + AGENT.d, 0], [AGENT.x, AGENT.y + AGENT.d, 0])} transform="translate(6 9)" />
          </g>
        </g>

        {/* 1. session plane: one tile per turn */}
        <g className="ly ly-plane" style={css({ "--d": 2 })}>
          {Array.from({ length: ROWS }, (_, ty) => Array.from({ length: COLS }, (_, tx) => {
            const c = CUBES.find((k) => k.tx === tx && k.ty === ty);
            const i = c ? CUBES.indexOf(c) : -1;
            return (
              <At key={`${tx}-${ty}`} x={tx + 0.03} y={ty + 0.03} className={`tile ${c ? `has ${c.who}` : ""}`} style={css({ "--i": i })}>
                <Faces w={0.94} d={0.94} h={0.1} />
                <polygon className="tl-glow" points={faces(0.94, 0.94, 0.1).t} />
              </At>
            );
          }))}
        </g>

        {/* policy pad */}
        <g className="ly ly-pad" aria-hidden="true">
          <polygon className="pad-ring" points={quad([PAD.cx - 0.8, PAD.cy - 0.7, 0.01], [PAD.cx + 0.8, PAD.cy - 0.7, 0.01], [PAD.cx + 0.8, PAD.cy + 0.7, 0.01], [PAD.cx - 0.8, PAD.cy + 0.7, 0.01])} />
        </g>

        {/* 5. skill file, conveyor and agent */}
        <g className="ly ly-skill" aria-hidden="true">
          <At x={SKILL.x} y={SKILL.y} className="skill"><Faces w={SKILL.w} d={SKILL.d} h={SKILL.h} /></At>
          {[1, 2, 3, 4].map((i) => {
            const a = P(SKILL.x + 0.25, SKILL.y + i * 0.42, SKILL.h), b = P(SKILL.x + SKILL.w - 0.25 - (i % 2) * 0.35, SKILL.y + i * 0.42, SKILL.h);
            return <line key={i} className="sk-ln" x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />;
          })}
          <g className="sk-on">
            {[1, 2, 3, 4].map((i) => {
              const a = P(SKILL.x + 0.25, SKILL.y + i * 0.42, SKILL.h), b = P(SKILL.x + SKILL.w - 0.25 - (i % 2) * 0.35, SKILL.y + i * 0.42, SKILL.h);
              return <line key={i} className="sk-ln-on" x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />;
            })}
            <polygon className="sk-edge" points={faces(SKILL.w, SKILL.d, SKILL.h).t} transform={`translate(${P(SKILL.x, SKILL.y, 0)[0].toFixed(1)} ${P(SKILL.x, SKILL.y, 0)[1].toFixed(1)})`} />
          </g>
        </g>
        <g className="ly ly-conv" aria-hidden="true">
          <polygon className="conv" points={quad([CONV.s[0] + 0.28, CONV.s[1] - 0.28, 0.02], [CONV.e[0] + 0.28, CONV.e[1] - 0.28, 0.02], [CONV.e[0] - 0.28, CONV.e[1] + 0.28, 0.02], [CONV.s[0] - 0.28, CONV.s[1] + 0.28, 0.02])} />
          <line className="conv-ln" x1={convS[0]} y1={convS[1]} x2={convE[0]} y2={convE[1]} />
          <line className="conv-pulse" pathLength={100} x1={convS[0]} y1={convS[1]} x2={convE[0]} y2={convE[1]} />
        </g>
        <g className="ly ly-agent" aria-hidden="true">
          <polygon className="ag-ring" points={quad([AGENT.x - 0.3, AGENT.y - 0.3, 0.01], [AGENT.x + AGENT.w + 0.3, AGENT.y - 0.3, 0.01], [AGENT.x + AGENT.w + 0.3, AGENT.y + AGENT.d + 0.3, 0.01], [AGENT.x - 0.3, AGENT.y + AGENT.d + 0.3, 0.01])} />
          <At x={AGENT.x} y={AGENT.y} className="agent-node">
            <Faces w={AGENT.w} d={AGENT.d} h={AGENT.h} />
            <polygon className="visor" points={(() => { const o = [0.14, 0.76]; const z = [0.5, 0.78]; const f = (x: number, z0: number) => { const p = P(AGENT.x + x, AGENT.y + AGENT.d, z0), q = P(AGENT.x, AGENT.y, 0); return [p[0] - q[0], p[1] - q[1]] as XY; }; return pts([f(o[0], z[0]), f(o[1], z[0]), f(o[1], z[1]), f(o[0], z[1])]); })()} />
            <line className="antenna" x1={faces(AGENT.w, AGENT.d, AGENT.h).top[0]} y1={faces(AGENT.w, AGENT.d, AGENT.h).top[1]} x2={faces(AGENT.w, AGENT.d, AGENT.h).top[0]} y2={faces(AGENT.w, AGENT.d, AGENT.h).top[1] - 16} />
            <circle className="antenna-tip" cx={faces(AGENT.w, AGENT.d, AGENT.h).top[0]} cy={faces(AGENT.w, AGENT.d, AGENT.h).top[1] - 17} r="3" />
          </At>
        </g>
        {/* feedback: agents improve, so the loop returns to the session */}
        <g className="ly ly-loop" aria-hidden="true">
          <path className="loop-path" d={`M ${lp([352, 508])} C ${lp([470, 502])}, ${lp([566, 330])}, ${lp([482, 216])}`} />
          <polygon className="loop-head" points={[[482, 216], [493.2, 222.6], [485.2, 228.6]].map((q) => lp(q as XY).replace(" ", ",")).join(" ")} />
        </g>

        {/* 2. decision cubes */}
        <g className="ly ly-cubes" style={css({ "--d": 5 })}>
          {ordered.map((c) => {
            const bumped = bumpedNow(c);
            const [sx, sy] = cubePos(c, bumped);
            const [ux, uy] = cubePos(c, false);
            const f = faces(CUBE.size, CUBE.size, CUBE.h);
            return (
              <g
                key={c.id}
                className={`cube ${c.who} c-${c.id} ${bumped ? "bumped" : ""}`}
                style={css({ transform: `translate(${px0(sx)}, ${px0(sy)})`, "--i": CUBES.indexOf(c), "--bx": px0(ux - sx), "--by": px0(uy - sy) })}
              >
                <Faces w={CUBE.size} d={CUBE.size} h={CUBE.h} />
                <polygon className={`dot td-${c.type}`} points={diamond(f.top)} />
              </g>
            );
          })}
        </g>

        {/* 4. the same overrule in 11 sessions piles up on the pad */}
        <g className="ly ly-pad ly-mc">
          {MICRO_TILES.map(([tx, ty], i) => {
            const from = P(tx + 0.35, ty + 0.35, 0.1), to = P(...PILE[i]);
            return (
              <At key={i} x={PILE[i][0]} y={PILE[i][1]} z={PILE[i][2]} className="mc" style={css({ "--i": i, "--fx": px0(from[0] - to[0]), "--fy": px0(from[1] - to[1]) })}>
                <Faces w={0.3} d={0.3} h={0.3} />
              </At>
            );
          })}
        </g>
        <g className="ly ly-pad ly-slab">
          <At x={SLAB.x} y={SLAB.y} className="slab" style={css({ "--sx": px0(skillPx[0] - padPx[0]), "--sy": px0(skillPx[1] - padPx[1]) })}>
            <Faces w={SLAB.w} d={SLAB.d} h={SLAB.h} />
          </At>
        </g>

        {/* 3. governance gate: sweeps over the plane and checks the agent decisions */}
        <g className="ly ly-gate">
          <g className="gate" style={css({ "--gx": px0(gateSweep[0]), "--gy": px0(gateSweep[1]) })}>
            <polygon className="curtain" points={quad([GATE.rest + 0.08, 0, 0.1], [GATE.rest + 0.08, 4, 0.1], [GATE.rest + 0.08, 4, 1.45], [GATE.rest + 0.08, 0, 1.45])} />
            <At x={GATE.rest} y={-0.35} className="post"><Faces w={0.16} d={0.16} h={1.5} /></At>
            <At x={GATE.rest} y={4.2} className="post"><Faces w={0.16} d={0.16} h={1.5} /></At>
            <At x={GATE.rest} y={-0.35} z={1.5} className="post beam"><Faces w={0.16} d={4.71} h={0.14} /></At>
          </g>
        </g>
        <g className="ly ly-badges" aria-hidden="true">
          {CUBES.filter((c) => c.verdict).map((c) => {
            const [bx, by] = P(c.tx + 0.5 + (c.bump ? c.bump[0] : 0), c.ty + 0.5 + (c.bump ? c.bump[1] : 0), 0.95);
            return (
              <g key={c.id} className={`badge ${c.verdict}`} style={css({ transform: `translate(${px0(bx)}, ${px0(by - 12)})`, "--dl": `${gateDelay(c).toFixed(2)}s` })}>
                <circle r="8" /><text y="3.4" textAnchor="middle">{c.verdict === "ok" ? "✓" : "✕"}</text>
              </g>
            );
          })}
        </g>

        <g className="iso-leaders" key={`ld${s}`} aria-hidden="true">
          {cs.map((c) => <g key={c.key} className={c.sec ? "sec" : ""}><line x1={c.ax} y1={c.ay} x2={c.tx} y2={c.ty} /><circle cx={c.tx} cy={c.ty} r="3" /></g>)}
        </g>
      </svg>

      <div className="iso-cos" key={`co${s}`}>
        {cs.map((c) => (
          <div key={c.key} className={`iso-co side-${c.side} ${c.sec ? "sec" : ""} ${s === 5 ? "form" : ""}`} style={{ left: px(c.ax), top: py(c.ay) }}>
            <CalloutBody step={s} k={c.key} />
          </div>
        ))}
      </div>
    </div>
  );
}
