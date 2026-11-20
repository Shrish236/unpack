// The change graph. It shows only what this commit touched, at the level of detail that fits its size:
//   folders   -> one card per folder (counts, a change bar, risk badges); click to open
//   files     -> one card per file, compact; the riskiest start expanded
//   functions -> every file expanded to its changed functions
// "Auto" picks the level from the number of files in view. Opening a folder keeps the other folders as folded cards
// around it. Unchanged neighbours of the selected function can be shown on demand as faded ghost rows.
//
// Performance is the design constraint. Moving the selection must touch only what changes:
//   - node data and edge objects keep their identity unless their own content changed, so React Flow skips the rest
//   - dimming is a CSS class on the canvas, not per-card state
//   - positions are recomputed only when the set or size of the cards changes, never on selection
//   - the camera moves only when the selected row is out of view
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import {
  Background, BackgroundVariant, Controls, Handle, MarkerType, MiniMap, Panel, Position, ReactFlow, ReactFlowProvider,
  useNodesState, useReactFlow, useStore, type Edge, type Node, type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AlignLeft, ChevronDown, ChevronRight, FileCode2, FlaskConical, Folder, Minus, Pencil, Plus, SlidersHorizontal, type LucideIcon } from "lucide-react";
import type { GNode } from "../api";
import { CHANGE_KINDS, CHANGE_STYLE, cardKind, changeKindOf, isUntested, type ChangeKind, type Graph } from "./model";
import { layoutFiles, layoutGrid } from "./layout";

export type Detail = "auto" | "folders" | "files" | "functions";
type Level = Exclude<Detail, "auto">;

const W = 292;
const FOLDER_W = 300;
const HEAD = 64;
const ROW = 42;
const CHIP = 30;
const PAD = 14;
const BAR_BLOCK = 40;
const FOLDER_H = 132;
const UNRANKED = 1e9;

const GLYPH: Record<ChangeKind, LucideIcon> = { added: Plus, functional: Pencil, signature: SlidersHorizontal, deleted: Minus, text_only: AlignLeft };

interface Row { id: string; label: string; kind: "changed" | "ghost" | "context" | "test"; change: ChangeKind | null; outside: boolean; untested: boolean; rank: number }
interface Chip { id: string; text: string }
interface Tally { counts: Record<ChangeKind, number>; changed: number; untested: number; outside: number; findings: number }
interface FileModel extends Tally { path: string; folder: string; rows: Row[]; chips: Chip[]; ghost: boolean; risk: number; rank: number; ordinal: number }
interface FolderModel extends Tally { id: string; name: string; files: FileModel[]; rank: number }
interface Opts { tests: boolean; context: boolean; chips: boolean }

const emptyTally = (): Tally => ({ counts: { added: 0, functional: 0, signature: 0, text_only: 0, deleted: 0 }, changed: 0, untested: 0, outside: 0, findings: 0 });
const folderOf = (path: string) => path.split("/").slice(0, -1).join("/") || ".";

// A model per file that holds a change, ordered by the chosen reading order. Tests and unchanged neighbours join only when asked for.
function buildFiles(g: Graph, o: Opts, extra: Set<string>, rank: Map<string, number>): FileModel[] {
  const touched = new Set(g.nodes.filter((n) => n.change).map((n) => n.path));
  const wanted = (n: GNode, kind: ReturnType<typeof cardKind>) => kind === "changed" || kind === "ghost" || extra.has(n.id) || (kind === "context" && o.context && touched.has(n.path)) || (kind === "test" && o.tests);
  const byPath = new Map<string, GNode[]>();
  for (const n of g.nodes) {
    const k = cardKind(n);
    if (k === "container" || !wanted(n, k)) continue;
    (byPath.get(n.path) ?? byPath.set(n.path, []).get(n.path)!).push(n);
  }

  const files: FileModel[] = [];
  for (const [path, members] of byPath) {
    const t = emptyTally();
    const rows: Row[] = members.map((n) => {
      const k = cardKind(n);
      const ck = changeKindOf(n);
      const untested = k === "changed" && isUntested(n);
      const outside = n.change?.source === "outside_session";
      if (ck) { t.counts[ck] += 1; t.changed += 1; }
      if (untested) t.untested += 1;
      if (outside) t.outside += 1;
      t.findings += n.finding_ids.length;
      return { id: n.id, label: n.label, kind: k as Row["kind"], change: ck, outside, untested, rank: rank.get(n.id) ?? UNRANKED };
    }).sort((a, b) => a.rank - b.rank || (g.byId[a.id].start_line ?? 0) - (g.byId[b.id].start_line ?? 0));
    const here = new Set(rows.map((r) => r.id));
    const chips = o.chips ? g.collapsed.filter((c) => here.has(c.anchor) && (c.direction !== "tests" || o.tests)).map((c) => ({ id: c.id, text: `${c.count} ${c.direction} in ${c.file.split("/").pop()}` })) : [];
    files.push({ path, folder: folderOf(path), rows, chips, ghost: !touched.has(path), ...t, risk: t.untested * 3 + t.findings * 3 + t.outside * 2 + t.changed * 0.25, rank: Math.min(...rows.map((r) => r.rank)), ordinal: 0 });
  }
  files.sort((a, b) => Number(a.ghost) - Number(b.ghost) || a.rank - b.rank || a.path.localeCompare(b.path));
  let i = 0;
  for (const f of files) if (!f.ghost) f.ordinal = ++i;
  return files;
}

function foldersOf(files: FileModel[]): FolderModel[] {
  const map = new Map<string, FolderModel>();
  for (const f of files) {
    if (f.ghost) continue;
    const m = map.get(f.folder) ?? { id: f.folder, name: f.folder, files: [], rank: UNRANKED, ...emptyTally() };
    m.files.push(f);
    for (const k of CHANGE_KINDS) m.counts[k] += f.counts[k];
    m.changed += f.changed; m.untested += f.untested; m.outside += f.outside; m.findings += f.findings;
    m.rank = Math.min(m.rank, f.rank);
    map.set(f.folder, m);
  }
  return [...map.values()].sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
}

function ChangeBar({ t }: { t: Tally }) {
  const total = Math.max(1, t.changed);
  return (
    <div className="cg-bar" role="img" aria-label={`${t.changed} changed`}>
      {CHANGE_KINDS.filter((k) => t.counts[k] > 0).map((k) => <i key={k} style={{ flex: t.counts[k] / total, background: CHANGE_STYLE[k].color }} title={`${t.counts[k]} ${CHANGE_STYLE[k].label.toLowerCase()}`} />)}
    </div>
  );
}

function Badges({ t }: { t: Tally }) {
  return (
    <div className="cg-badges">
      {t.untested > 0 && <span className="cg-b bad"><FlaskConical size={11} /> {t.untested} untested</span>}
      {t.outside > 0 && <span className="cg-b">{t.outside} outside session</span>}
      {t.findings > 0 && <span className="cg-b bad">{t.findings} findings</span>}
    </div>
  );
}

interface FileData extends Record<string, unknown> {
  file: FileModel; expanded: boolean; selRow: string | null; rel: boolean; connectedRows: string[] | null; blast: Record<string, number> | null;
  numbered: boolean; onSelect: (id: string | null) => void; onToggle: (path: string) => void;
}
interface FolderData extends Record<string, unknown> { folder: FolderModel; rel: boolean; numbered: boolean; onOpen: (folder: string) => void }

const FileNode = memo(function FileNode({ id, data }: NodeProps<Node<FileData>>) {
  const { file, expanded, selRow, rel, connectedRows, blast, numbered, onSelect, onToggle } = data;
  if (!file) return null;
  const slash = file.path.lastIndexOf("/");
  return (
    <div className={`cg-file ${rel ? "rel" : ""} ${file.ghost ? "ghost" : ""}`} style={{ width: W }}>
      <header className="cg-file-h" onClick={() => onToggle(file.path)} title={expanded ? "Collapse" : "Show changed functions"}>
        <Handle type="target" position={Position.Left} id={`${id}:hin`} className="cg-h" />
        {numbered && !file.ghost ? <span className="cg-n" title="Position in the reading order">{file.ordinal}</span> : <span className="cg-file-ico"><FileCode2 size={16} /></span>}
        <div className="cg-path"><span className="cg-dir">{file.path.slice(0, slash + 1)}</span><b>{file.path.slice(slash + 1)}</b></div>
        <div className="cg-sum">
          {CHANGE_KINDS.filter((k) => file.counts[k]).map((k) => <span key={k} className="cg-sum-i" style={{ color: CHANGE_STYLE[k].text }}>{k === "added" ? "+" : k === "deleted" ? "−" : "~"}{file.counts[k]}</span>)}
        </div>
        <span className="cg-caret">{expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</span>
        <Handle type="source" position={Position.Right} id={`${id}:hout`} className="cg-h" />
      </header>
      {!expanded && <div className="cg-compact"><ChangeBar t={file} /><Badges t={file} /></div>}
      {expanded && (
        <>
          <ul className="cg-rows">
            {file.rows.map((r) => {
              const Icon = r.change ? GLYPH[r.change] : r.kind === "test" ? FlaskConical : null;
              const hop = blast?.[r.id];
              const color = r.change ? CHANGE_STYLE[r.change].color : r.kind === "test" ? "var(--t-test)" : "var(--ink-3)";
              const isRel = connectedRows !== null && connectedRows.includes(r.id);
              return (
                <li key={r.id} className={`cg-row ${r.kind} ${r.id === selRow ? "sel" : ""} ${isRel ? "rel" : ""} ${r.untested ? "untested" : ""}`}
                  style={{ ["--c" as string]: color }} onClick={(e) => { e.stopPropagation(); onSelect(r.id); }}>
                  <Handle type="target" position={Position.Left} id={`${r.id}:in`} className="cg-h" />
                  <span className="cg-glyph">{Icon ? <Icon size={13} strokeWidth={2.4} /> : <i />}</span>
                  <span className="cg-name">{r.label}</span>
                  {numbered && r.rank !== UNRANKED && <span className="cg-rank">{r.rank + 1}</span>}
                  {r.change === "deleted" && <span className="cg-tag">removed</span>}
                  {r.outside && <span className="cg-tag outside">outside session</span>}
                  {hop !== undefined && <span className="cg-tag blast">{hop} hop{hop > 1 ? "s" : ""}</span>}
                  {r.untested && <span className="cg-flask" title="No test reaches this"><FlaskConical size={13} /></span>}
                  <Handle type="source" position={Position.Right} id={`${r.id}:out`} className="cg-h" />
                  <Handle type="target" position={Position.Right} id={`${r.id}:loop`} className="cg-h" />
                </li>
              );
            })}
          </ul>
          {file.chips.map((c) => <div key={c.id} className="cg-chip">{c.text}</div>)}
        </>
      )}
    </div>
  );
});

const FolderNode = memo(function FolderNode({ id, data }: NodeProps<Node<FolderData>>) {
  const { folder, rel, onOpen } = data;
  if (!folder) return null;
  return (
    <div className={`cg-folder ${rel ? "rel" : ""}`} style={{ width: FOLDER_W }} onClick={() => onOpen(folder.id)} role="button" title="Open this folder">
      <Handle type="target" position={Position.Left} id={`${id}:hin`} className="cg-h" />
      <div className="cg-folder-h">
        <span className="cg-file-ico folder"><Folder size={16} /></span>
        <div className="cg-path"><b>{folder.name}</b><span className="cg-dir">{folder.files.length} files · {folder.changed} functions changed</span></div>
        <ChevronRight size={15} className="cg-caret" />
      </div>
      <ChangeBar t={folder} />
      <Badges t={folder} />
      <Handle type="source" position={Position.Right} id={`${id}:hout`} className="cg-h" />
    </div>
  );
});

const nodeTypes = { file: FileNode, folder: FolderNode };

interface Props {
  g: Graph; sel: string | null; blast: boolean; opts: Opts; detail: Detail; focus: string | null; neighbours: boolean; allLinks: boolean;
  order: string[]; numbered: boolean; fitNonce: number; onSelect: (id: string | null) => void; onFocus: (folder: string | null) => void;
}

interface Spec { id: string; type: "file" | "folder"; w: number; h: number; file?: FileModel; folder?: FolderModel; expanded?: boolean }
interface BaseEdge { key: string; n: number; still: Edge; anim: Edge; hot: Edge }

// two records are the same when every field is the same value, or an array with the same content
function sameData(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of keys) {
    const x = a[k], y = b[k];
    if (x === y) continue;
    if (Array.isArray(x) && Array.isArray(y) && x.length === y.length && x.every((v, i) => v === y[i])) continue;
    return false;
  }
  return true;
}

function Inner({ g, sel, blast, opts, detail, focus, neighbours, allLinks, order, numbered, fitNonce, onSelect, onFocus }: Props) {
  const rf = useReactFlow();
  const dom = useStore((s) => s.domNode);
  const [open, setOpen] = useState<Set<string>>(new Set());
  useEffect(() => setOpen(new Set()), [g]);

  const rank = useMemo(() => new Map(order.map((id, i) => [id, i] as const)), [order]);
  // depends on the selection only while neighbours are shown, so an ordinary selection change cannot invalidate the layout chain
  const extraFor = neighbours ? sel : null;
  const extra = useMemo(() => {
    const s = new Set<string>();
    if (!extraFor) return s;
    for (const e of g.edges) { if (e.source === extraFor) s.add(e.target); if (e.target === extraFor) s.add(e.source); }
    return s;
  }, [g, extraFor]);
  const files = useMemo(() => buildFiles(g, opts, extra, rank), [g, opts, extra, rank]);
  const real = useMemo(() => files.filter((f) => !f.ghost), [files]);
  const scope = useMemo(() => (focus ? real.filter((f) => f.folder === focus) : real), [real, focus]);

  const level: Level = detail !== "auto" ? detail : scope.length <= 8 ? "functions" : scope.length <= 24 ? "files" : "folders";
  const top = useMemo(() => new Set([...scope].sort((a, b) => b.risk - a.risk).slice(0, 4).map((f) => f.path)), [scope]);

  const fileOfRow = useMemo(() => Object.fromEntries(files.flatMap((f) => f.rows.map((r) => [r.id, f] as const))), [files]);
  const selFile = sel ? fileOfRow[sel]?.path : undefined;

  // a file is drawn as a file when its folder is in focus, or the level is files/functions with no focus; otherwise it folds into its folder
  const shownAsFile = useCallback((f: FileModel) => {
    if (f.ghost) return level !== "folders" || !!focus;
    if (focus) return f.folder === focus;
    return level !== "folders";
  }, [level, focus]);
  const baseExpanded = useCallback((f: FileModel) => level === "functions" || open.has(f.path) || f.ghost || (level === "files" && top.has(f.path)), [level, open, top]);
  // a selection inside a collapsed card expands just that card; selecting inside an open one changes nothing here
  const selExpand = useMemo(() => {
    const f = selFile ? files.find((x) => x.path === selFile) : undefined;
    return f && shownAsFile(f) && !baseExpanded(f) ? f.path : null;
  }, [selFile, files, shownAsFile, baseExpanded]);

  const specs: Spec[] = useMemo(() => {
    const out: Spec[] = [];
    for (const f of files) if (shownAsFile(f)) {
      const expanded = baseExpanded(f) || f.path === selExpand;
      out.push({ id: f.path, type: "file", file: f, expanded, w: W, h: HEAD + (expanded ? f.rows.length * ROW + f.chips.length * CHIP + PAD : BAR_BLOCK + 14) });
    }
    for (const fo of foldersOf(files.filter((f) => !shownAsFile(f)))) out.push({ id: `folder:${fo.id}`, type: "folder", folder: fo, w: FOLDER_W, h: FOLDER_H });
    return out;
  }, [files, shownAsFile, baseExpanded, selExpand]);
  const specById = useMemo(() => new Map(specs.map((s) => [s.id, s] as const)), [specs]);

  const nodeOfFile = useMemo(() => {
    const m: Record<string, { node: string; rows: boolean }> = {};
    for (const s of specs) {
      if (s.file) m[s.file.path] = { node: s.id, rows: !!s.expanded };
      if (s.folder) for (const f of s.folder.files) m[f.path] = { node: s.id, rows: false };
    }
    return m;
  }, [specs]);

  const edgesAll = useMemo(() => g.edges.filter((e) => (e.kind === "CALLS" || e.kind === "REACHES") && fileOfRow[e.source] && fileOfRow[e.target]), [g, fileOfRow]);

  // edge objects are built once per layout; selection only picks which already-built object to hand to React Flow
  const { base, incident, pairs } = useMemo(() => {
    const agg = new Map<string, { source: string; target: string; sh: string; th: string; n: number; tier: string; reach: boolean }>();
    const incident = new Map<string, string[]>();
    for (const e of edgesAll) {
      const a = nodeOfFile[fileOfRow[e.source].path], b = nodeOfFile[fileOfRow[e.target].path];
      if (!a || !b) continue;
      const sh = a.rows ? `${e.source}:out` : `${a.node}:hout`;
      const same = a.node === b.node;
      if (same && !(a.rows && b.rows)) continue;
      const th = b.rows ? `${e.target}:${same ? "loop" : "in"}` : `${b.node}:hin`;
      const key = `${a.node}|${sh}>${b.node}|${th}`;
      const tier = e.tier ?? "AMBIGUOUS";
      const prev = agg.get(key);
      if (prev) { prev.n += 1; if (tier === "EXTRACTED") prev.tier = tier; prev.reach = prev.reach && e.kind === "REACHES"; }
      else agg.set(key, { source: a.node, target: b.node, sh, th, n: 1, tier, reach: e.kind === "REACHES" });
      for (const id of [e.source, e.target]) (incident.get(id) ?? incident.set(id, []).get(id)!).push(key);
    }
    const make = (key: string, e: NonNullable<ReturnType<typeof agg.get>>, hot: boolean, animated: boolean): Edge => ({
      id: key, source: e.source, target: e.target, sourceHandle: e.sh, targetHandle: e.th,
      label: e.n > 1 ? String(e.n) : undefined, animated,
      className: `cg-e ${e.tier.toLowerCase()} ${e.reach ? "reach" : ""} ${hot ? "hot" : ""}`,
      style: e.n > 1 ? { strokeWidth: Math.min(3.2, 1.5 + Math.log2(e.n) * 0.6) } : undefined,
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 }, zIndex: hot ? 10 : 0,
    });
    const base: BaseEdge[] = [...agg.entries()].map(([key, e]) => ({
      key, n: e.n,
      still: make(key, e, false, false), anim: make(key, e, false, e.reach || e.tier !== "AMBIGUOUS"), hot: make(key, e, true, true),
    }));
    const pairs = [...new Set([...agg.values()].map((e) => `${e.source}\n${e.target}`))].map((p) => { const [source, target] = p.split("\n"); return { source, target }; });
    return { base, incident, pairs };
  }, [edgesAll, nodeOfFile, fileOfRow]);

  const rfEdges: Edge[] = useMemo(() => {
    const hotKeys = new Set(sel ? incident.get(sel) ?? [] : []);
    const crowded = base.length > 10 && !allLinks;
    const animateAll = base.length <= 24; // many flowing dashes cost frames; only the selection animates on big graphs
    return base.filter((b) => !crowded || b.n >= 4 || hotKeys.has(b.key)).map((b) => (hotKeys.has(b.key) ? b.hot : animateAll ? b.anim : b.still));
  }, [base, incident, sel, allLinks]);

  const connected = useMemo(() => {
    const s = new Set<string>();
    if (!sel) return s;
    s.add(sel);
    for (const e of edgesAll) { if (e.source === sel) s.add(e.target); if (e.target === sel) s.add(e.source); }
    return s;
  }, [sel, edgesAll]);
  const blastMap = useMemo(() => (sel && blast ? Object.fromEntries((g.analysis.impact.by_node[sel] ?? []).map((h) => [h.id, h.depth])) : null), [g, sel, blast]);

  const toggle = useCallback((path: string) => setOpen((s) => { const n = new Set(s); if (n.has(path)) n.delete(path); else n.add(path); return n; }), []);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);

  // positions: only when the cards or their sizes change. Unmoved cards keep their object, so they are not re-rendered.
  useEffect(() => {
    const sized = specs.map((s) => ({ id: s.id, w: s.w, h: s.h }));
    const pos = specs.length > 4 ? layoutGrid(sized) : layoutFiles(sized, pairs);
    setNodes((prev) => {
      const old = new Map(prev.map((n) => [n.id, n] as const));
      return specs.map((s) => {
        const o = old.get(s.id), p = pos[s.id];
        if (o && o.type === s.type && o.position.x === p.x && o.position.y === p.y) return o;
        return o ? { ...o, position: p } : { id: s.id, type: s.type, position: p, data: {} };
      });
    });
  }, [specs, pairs, setNodes]);

  // data: handed over per card, and only replaced when that card's own content changed
  useEffect(() => {
    const relatedNodes = new Set<string>();
    const rowsByFile = new Map<string, string[]>();
    for (const id of connected) {
      const f = fileOfRow[id];
      if (!f) continue;
      const node = nodeOfFile[f.path]?.node;
      if (node) relatedNodes.add(node);
      (rowsByFile.get(f.path) ?? rowsByFile.set(f.path, []).get(f.path)!).push(id);
    }
    setNodes((ns) => {
      let changed = false;
      const next = ns.map((n) => {
        const s = specById.get(n.id);
        if (!s) return n;
        let d: Record<string, unknown>;
        if (s.file) {
          const path = s.file.path;
          d = {
            file: s.file, expanded: !!s.expanded, selRow: sel && fileOfRow[sel]?.path === path ? sel : null, rel: relatedNodes.has(s.id),
            connectedRows: sel ? (rowsByFile.get(path) ?? []) : null, blast: blastMap, numbered, onSelect, onToggle: toggle,
          } satisfies FileData;
        } else if (s.folder) d = { folder: s.folder, rel: relatedNodes.has(s.id), numbered, onOpen: onFocus } satisfies FolderData;
        else return n;
        if (n.data && sameData(n.data, d)) return n;
        changed = true;
        return { ...n, data: d };
      });
      return changed ? next : ns;
    });
  }, [specById, sel, connected, blastMap, numbered, fileOfRow, nodeOfFile, onSelect, toggle, onFocus, setNodes]);

  const fitKey = `${level}|${focus}|${g.analysis.analysis.public_id}|${fitNonce}`;
  useEffect(() => {
    const t = setTimeout(() => rf.fitView({ duration: 450, padding: 0.06, maxZoom: 1.15 }), 120);
    return () => clearTimeout(t);
  }, [fitKey, rf]);

  // a selection inside a folded folder opens that folder
  useEffect(() => {
    const f = sel ? fileOfRow[sel] : undefined;
    if (f && !shownAsFile(f)) onFocus(f.folder);
    // only a new selection matters here
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel]);

  // the camera moves only when the selected row is out of view, so stepping through functions stays still and smooth
  useEffect(() => {
    if (!sel || !selFile || !dom) return;
    const nodeId = nodeOfFile[selFile]?.node;
    const n = nodeId ? rf.getNode(nodeId) : undefined;
    if (!n) return;
    const spec = specById.get(nodeId!);
    const idx = spec?.file && spec.expanded ? spec.file.rows.findIndex((r) => r.id === sel) : -1;
    const { x, y, zoom } = rf.getViewport();
    const w = n.measured?.width ?? W;
    const rowTop = n.position.y + (idx >= 0 ? HEAD + idx * ROW : 0);
    const rowH = idx >= 0 ? ROW : (n.measured?.height ?? 120);
    const left = n.position.x * zoom + x, top = rowTop * zoom + y;
    const m = 56;
    if (left >= m && top >= m && left + w * zoom <= dom.clientWidth - m && top + rowH * zoom <= dom.clientHeight - m) return;
    rf.setCenter(n.position.x + w / 2, rowTop + rowH / 2, { zoom, duration: 300 });
    // only a new selection moves the camera, not later layout changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel]);

  if (specs.length === 0) return <div className="cg-empty">This analysis has no changed functions to draw.</div>;

  return (
    <ReactFlow nodes={nodes} edges={rfEdges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onPaneClick={() => onSelect(null)}
      fitView fitViewOptions={{ padding: 0.06, maxZoom: 1.15 }} minZoom={0.1} maxZoom={1.6} nodesConnectable={false} elementsSelectable={false}
      onlyRenderVisibleElements autoPanOnNodeDrag={false} zoomOnDoubleClick={false} selectNodesOnDrag={false} elevateNodesOnSelect={false} elevateEdgesOnSelect={false}
      proOptions={{ hideAttribution: true }}>
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.4} className="cg-bg" />
      <Controls showInteractive={false} position="bottom-right" />
      {specs.length <= 80 && <MiniMap pannable zoomable position="bottom-left" className="cg-mini" style={{ width: 150, height: 96 }} nodeStrokeWidth={0} nodeColor="var(--line-2)" maskColor="transparent" />}
      <Panel position="top-left" className="cg-legend">
        {CHANGE_KINDS.map((k) => <span key={k} className="cg-leg"><i style={{ background: CHANGE_STYLE[k].color }} />{CHANGE_STYLE[k].label.toLowerCase()}</span>)}
        <span className="cg-leg"><FlaskConical size={12} className="bad" />no test reaches it</span>
      </Panel>
      <Panel position="top-right" className="cg-level">
        {focus ? <>Folder <b>{focus}</b> open · others folded</> : <>{scope.length} files · showing <b>{level}</b></>}
        {level === "folders" && !focus && <span> · click a folder to open it</span>}
      </Panel>
    </ReactFlow>
  );
}

export default function ChangeGraph(props: Props) {
  return <div className={`cg-canvas ${props.sel ? "has-sel" : ""}`}><ReactFlowProvider><Inner {...props} /></ReactFlowProvider></div>;
}
