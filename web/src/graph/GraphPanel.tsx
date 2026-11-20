// The change graph as a section of the PR page: controls, the graph, and the reasoning panel for the selected function.
// It takes an analysis and nothing else, so the PR tab and any future surface can mount it the same way.
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisResponse } from "../api";
import { Panel, Seg } from "../ui";
import ChangeGraph, { type Detail } from "./ChangeGraph";
import Inspector from "./Inspector";
import { buildGraph } from "./model";
import { ORDER_HINT, ORDER_LABEL, availableModes, orderFunctions, type OrderMode } from "./order";
import "../styles/graph.css";

// `sel` and `onSelect` are optional: give them and the page owns the selection (so the diff, the decisions and the graph
// move together); leave them out and the panel keeps its own.
export default function GraphPanel({ analysis, sel: selProp, onSelect }: { analysis: AnalysisResponse; sel?: string | null; onSelect?: (id: string | null) => void }) {
  const g = useMemo(() => buildGraph(analysis), [analysis]);
  // two orders only: the model's flow (or the agent's order when there is no flow), and A–Z for lookup
  const modes = useMemo<OrderMode[]>(() => [availableModes(g).includes("ai") ? "ai" : "session", "alphabetical"], [g]);
  const [modeState, setMode] = useState<OrderMode>(() => (analysis.flow?.llm ? "ai" : "session"));
  const mode = modes.includes(modeState) ? modeState : modes[0]; // a new analysis may not offer the mode that was chosen
  const [detail, setDetail] = useState<Detail>("auto");
  const [focus, setFocus] = useState<string | null>(null);
  const [selState, setSelState] = useState<string | null>(null);
  const controlled = selProp !== undefined;
  const sel = controlled ? selProp : selState;
  // stable, because the graph re-lays out when its onSelect changes
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const setSel = useCallback((id: string | null) => { setSelState(id); onSelectRef.current?.(id); }, []);
  const [blast, setBlast] = useState(false);
  const [fitNonce, setFitNonce] = useState(0);
  const [tests, setTests] = useState(false);
  // unchanged rows and collapsed callers are always on; neighbours and all links were noise, so they are gone
  const opts = useMemo(() => ({ tests, context: true, chips: true }), [tests]);
  const order = useMemo(() => orderFunctions(g, mode), [g, mode]);
  // the graph follows the selection at once; the text panel may trail a frame behind during fast stepping
  const inspectorSel = useDeferredValue(sel);

  // keys act only while the panel has focus, so arrows still scroll the page elsewhere
  const root = useRef<HTMLDivElement>(null);
  const orderRef = useRef(order);
  orderRef.current = order;
  const selRef = useRef(sel);
  selRef.current = sel;
  const last = useRef(0);
  const onKeyDown = (e: React.KeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (e.key === "Escape") setSel(null);
    else if (e.key === "b" || e.key === "B") setBlast((b) => !b);
    else if (e.key === "f" || e.key === "F") setFitNonce((x) => x + 1);
    else if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(e.key)) {
      e.preventDefault();
      const now = performance.now();
      if (e.repeat && now - last.current < 45) return; // key-repeat can outrun the screen; skip the extras
      last.current = now;
      const list = orderRef.current;
      if (list.length === 0) return;
      const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1;
      const i = selRef.current ? list.indexOf(selRef.current) : -1;
      setSel(list[(i + step + list.length) % list.length]);
    }
  };
  useEffect(() => { if (!controlled) setSelState(null); setFocus(null); }, [analysis]); // eslint-disable-line react-hooks/exhaustive-deps

  const files = new Set(g.changed.map((n) => n.path)).size;

  return (
    <Panel
      title="What this change touched"
      sub={`${g.changed.length} functions in ${files} files · ${ORDER_HINT[mode].toLowerCase()}`}
      aside={<Seg<OrderMode> value={mode} onChange={setMode} options={modes.map((m) => ({ id: m, label: ORDER_LABEL[m] }))} />}
      className="gp"
    >
      <div ref={root} className="gp-body" tabIndex={0} onKeyDown={onKeyDown} onPointerDown={(e) => { if ((e.target as HTMLElement).closest("input,select,button")) return; root.current?.focus({ preventScroll: true }); }} aria-label="Change graph">
        <div className="gl-toolbar">
          {/* one grouping choice (auto or per function) and one filter; the graph's own controls handle zoom and fit */}
          <Seg<Detail> value={detail} onChange={(d) => { setDetail(d); setFocus(null); }} options={[{ id: "auto", label: "Auto" }, { id: "functions", label: "Functions" }]} />
          {focus && <button className="chip cg-crumb" onClick={() => setFocus(null)} title="Back to all changes">All changes › <b>{focus}</b> ✕</button>}
          <label className="gl-check"><input type="checkbox" checked={tests} onChange={(e) => setTests(e.target.checked)} /> Show tests</label>
          <span className="gl-spacer" />
          <button className={`btn sm ${blast ? "primary" : ""}`} onClick={() => setBlast((b) => !b)} disabled={!sel} aria-pressed={blast}>Blast radius <kbd>B</kbd></button>
        </div>
        <div className="gl-grid">
          <ChangeGraph g={g} sel={sel} blast={blast} opts={opts} detail={detail} focus={focus} neighbours={false} allLinks={false} order={order} numbered={mode !== "alphabetical"} fitNonce={fitNonce} onSelect={setSel} onFocus={setFocus} />
          <Inspector g={g} sel={inspectorSel} order={order} mode={mode} onSelect={setSel} />
        </div>
        <p className="gl-keys"><kbd>←</kbd> <kbd>→</kbd> step through the changes · <kbd>Esc</kbd> clear</p>
      </div>
    </Panel>
  );
}
