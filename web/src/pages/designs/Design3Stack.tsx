import { useState } from "react";

/* Approach 3: Exploded 2.5D Architectural Stack ("Four Planes of Truth").
   Pure CSS 3D preserve-3d wrapping four crisp, real HTML/SVG planes:
   L4 Policy & AGENTS.md -> L3 Human Steering -> L2 Agent Sessions -> L1 Code & Test Graph. */

type LayerId = 4 | 3 | 2 | 1;

const STEP_FOCUS: Record<number, LayerId | "all"> = {
  0: "all",
  1: 2,
  2: 3,
  3: 1,
  4: 3,
  5: 4,
  6: "all",
};

const STEP_CAPTION: Record<number, string> = {
  0: "One verified thread from function call graph → agent turn → human overrule → org policy.",
  1: "Plane L2 active · Every agent & human turn typed and pinned to the session record.",
  2: "Plane L3 active · Human overrule “Don't add a library” overrides agent turn T16.",
  3: "Plane L1 active · Claims checked statically against the code & test reachability graph.",
  4: "Plane L3 active · 11 identical overrules across 3 teams stack into a policy candidate.",
  5: "Plane L4 active · Tech lead locks scope, enforcement, and expiry for Policy P-12.",
  6: "Loop closed · P-12 publishes from L4 back down into every agent's session context (11 → 3).",
};

export default function Design3Stack({ step }: { step: number }) {
  const [manualFocus, setManualFocus] = useState<LayerId | "all" | null>(null);
  const [prevStep, setPrevStep] = useState(step);

  if (prevStep !== step) {
    setPrevStep(step);
    setManualFocus(null);
  }

  const focus = manualFocus ?? STEP_FOCUS[step] ?? "all";
  const isFlat = focus !== "all";
  const closedLoop = step === 6 || (step === 0 && focus === "all");

  const toggleLayer = (id: LayerId) => {
    setManualFocus((cur) => (cur === id ? "all" : id));
  };

  return (
    <div className="d3-root" data-step={step} data-focus={focus} data-loop={closedLoop}>
      <div className="d3-bar">
        <span className="mono d3-bar-k">ARCHITECTURAL STACK · CLICK ANY PLANE</span>
        <div className="d3-layer-btns">
          {([4, 3, 2, 1] as LayerId[]).map((id) => (
            <button
              key={id}
              type="button"
              className={focus === id ? "on" : ""}
              onClick={() => toggleLayer(id)}
            >
              L{id}
            </button>
          ))}
          <button
            type="button"
            className={focus === "all" ? "on" : ""}
            onClick={() => setManualFocus("all")}
          >
            All
          </button>
        </div>
      </div>

      <div className="d3-viewport">
        <div className={`d3-stack ${isFlat ? "is-focused" : ""}`}>
          {/* Vertical evidence beam piercing all 4 planes */}
          <div className="d3-beam" aria-hidden="true" />
          {closedLoop && <div className="d3-return-arc" aria-hidden="true" />}

          {/* L4: Policy & AGENTS.md */}
          <button
            type="button"
            className={`d3-plane d3-l4 ${focus === 4 ? "active" : focus === "all" ? "idle" : "dim"}`}
            onClick={() => toggleLayer(4)}
          >
            <div className="d3-plane-head">
              <span className="d3-idx human">L4 · POLICY &amp; AGENTS.MD</span>
              <span className="chip ok">11 → 3 / 100</span>
            </div>
            <div className="d3-plane-body d3-policy">
              <div className="d3-rule-line">
                <span className="d3-pid">P-12</span>
                <span>Add no new runtime dependency without approval.</span>
              </div>
              <div className="d3-meta-row">
                <span>scope: <b>org</b></span>
                <span>enforce: <b>PR check</b></span>
                <span>expires: <b>2027-03</b></span>
              </div>
            </div>
          </button>

          {/* L3: Human Steering */}
          <button
            type="button"
            className={`d3-plane d3-l3 ${focus === 3 ? "active" : focus === "all" ? "idle" : "dim"}`}
            onClick={() => toggleLayer(3)}
          >
            <div className="d3-plane-head">
              <span className="d3-idx human">L3 · HUMAN STEERING</span>
              <span className="chip human">{step >= 4 ? "11 sessions · 3 teams" : "redirect · T18"}</span>
            </div>
            <div className="d3-plane-body d3-human">
              <p className="d3-quote">“Don't add a library for this. Use stdlib backoff.”</p>
              <div className="d3-pins">
                {Array.from({ length: 11 }, (_, i) => (
                  <i key={i} className={step >= 4 || step === 0 ? "lit" : i === 0 ? "lit" : ""} />
                ))}
              </div>
            </div>
          </button>

          {/* L2: Agent Sessions */}
          <button
            type="button"
            className={`d3-plane d3-l2 ${focus === 2 ? "active" : focus === "all" ? "idle" : "dim"}`}
            onClick={() => toggleLayer(2)}
          >
            <div className="d3-plane-head">
              <span className="d3-idx">L2 · AGENT SESSIONS</span>
              <span className="chip agent">Gemini CLI · Claude Code</span>
            </div>
            <div className="d3-plane-body d3-turns">
              <div className="d3-turn"><b>T14</b><span>wrap send() with retry</span><em>arch</em></div>
              <div className="d3-turn struck"><b>T16</b><span>pip install tenacity</span><em>overruled</em></div>
              <div className="d3-turn"><b>T22</b><span>exponential backoff ×5</span><em>retries</em></div>
            </div>
          </button>

          {/* L1: Code & Test Reachability Graph */}
          <button
            type="button"
            className={`d3-plane d3-l1 ${focus === 1 ? "active" : focus === "all" ? "idle" : "dim"}`}
            onClick={() => toggleLayer(1)}
          >
            <div className="d3-plane-head">
              <span className="d3-idx">L1 · CODE &amp; TEST GRAPH</span>
              <span className="chip bad">1 claim unsupported</span>
            </div>
            <div className="d3-plane-body d3-graph">
              <div className="d3-node ok"><b>Client.send</b><span>✓ 2 tests</span></div>
              <i className="d3-edge" />
              <div className="d3-node ok"><b>_send_single</b><span>✓ 2 tests</span></div>
              <i className="d3-edge bad" />
              <div className="d3-node bad"><b>Async._send</b><span>✕ 0 tests</span></div>
            </div>
          </button>
        </div>
      </div>

      <div className="d3-foot">
        <span>{STEP_CAPTION[step]}</span>
      </div>
    </div>
  );
}
