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
  const modes = useMemo(() => availableModes(g), [g]);
  const [modeState, setMode] = useState<OrderMode>(() => (analysis.flow?.llm ? "ai" : "session"));
  const mode = modes.includes(modeState) ? modeState : "session"; // a new analysis may not offer the mode that was chosen
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
  const [context, setContext] = useState(true);
  const [chips, setChips] = useState(true);
  const [neighbours, setNeighbours] = useState(false);
  const [allLinks, setAllLinks] = useState(false);

  const order = useMemo(() => orderFunctions(g, mode), [g, mode]);
  const opts = useMemo(() => ({ tests, context, chips }), [tests, context, chips]);
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
          <Seg<Detail> value={detail} onChange={(d) => { setDetail(d); setFocus(null); }} options={[{ id: "auto", label: "Auto" }, { id: "folders", label: "Folders" }, { id: "files", label: "Files" }, { id: "functions", label: "Functions" }]} />
          {focus && <button className="chip cg-crumb" onClick={() => setFocus(null)} title="Back to all changes">All changes › <b>{focus}</b> ✕</button>}
          <label className="gl-check" title="Unchanged functions the selected function calls or is called by"><input type="checkbox" checked={neighbours} onChange={(e) => setNeighbours(e.target.checked)} /> Neighbours</label>
          <label className="gl-check"><input type="checkbox" checked={tests} onChange={(e) => setTests(e.target.checked)} /> Tests</label>
          <label className="gl-check" title="Large graphs show only the selection's links and the strongest ones"><input type="checkbox" checked={allLinks} onChange={(e) => setAllLinks(e.target.checked)} /> All links</label>
          <label className="gl-check"><input type="checkbox" checked={context} onChange={(e) => setContext(e.target.checked)} /> Unchanged rows</label>
          <label className="gl-check"><input type="checkbox" checked={chips} onChange={(e) => setChips(e.target.checked)} /> Collapsed callers</label>
          <span className="gl-spacer" />
          <button className={`btn sm ${blast ? "primary" : ""}`} onClick={() => setBlast((b) => !b)} disabled={!sel} aria-pressed={blast}>Blast radius <kbd>B</kbd></button>
          <button className="btn sm" onClick={() => setFitNonce((x) => x + 1)}>Fit <kbd>F</kbd></button>
        </div>
        <div className="gl-grid">
          <ChangeGraph g={g} sel={sel} blast={blast} opts={opts} detail={detail} focus={focus} neighbours={neighbours} allLinks={allLinks} order={order} numbered={mode !== "alphabetical"} fitNonce={fitNonce} onSelect={setSel} onFocus={setFocus} />
          <Inspector g={g} sel={inspectorSel} order={order} mode={mode} onSelect={setSel} />
        </div>
        <p className="gl-keys">Click the graph, then <kbd>←</kbd> <kbd>→</kbd> step through the changes · drag cards · scroll to zoom · <kbd>Esc</kbd> clear</p>
      </div>
    </Panel>
  );
}
