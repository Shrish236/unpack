// The whole change, file by file, with each hunk tied to the graph node that owns it.
// Select a function (in the graph, the decisions or the findings) and its hunks light up; click an owner chip on a hunk
// and the graph selects that function. Changes outside any function (imports, config, docs, deleted code) are here too.
import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisResponse, DiffFile, FileHunk, GNode } from "../api";
import { Panel } from "../ui";
import "../styles/diff.css";

const STATUS: Record<string, string> = { A: "added", M: "modified", D: "deleted", R: "renamed" };
const OWNER_WORDS: Record<string, string> = { class: "class body", module: "module level", file: "whole file", none: "no patch" };
const MAX_LINES = 300; // a hunk longer than this shows its first lines until asked
const short = (id: string) => id.split("::").slice(1).join("::") || id;

interface Row { kind: "add" | "del" | "ctx" | "hh"; old: number | null; neu: number | null; text: string }

// Number each line from the hunk header: " " moves both counters, "+" the new one, "-" the old one.
export function rowsOf(patch: string): Row[] {
  const rows: Row[] = [];
  let o = 0, n = 0;
  for (const line of patch.split("\n")) {
    const m = /^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(line);
    if (m) { o = Number(m[1]); n = Number(m[2]); rows.push({ kind: "hh", old: null, neu: null, text: line }); continue; }
    if (line.startsWith("\\")) { rows.push({ kind: "hh", old: null, neu: null, text: line }); continue; }
    if (line.startsWith("+")) rows.push({ kind: "add", old: null, neu: n++, text: line.slice(1) });
    else if (line.startsWith("-")) rows.push({ kind: "del", old: o++, neu: null, text: line.slice(1) });
    else rows.push({ kind: "ctx", old: o++, neu: n++, text: line.slice(1) });
  }
  return rows;
}

function Hunk({ h, hot, nodes, onSelect }: { h: FileHunk; hot: boolean; nodes: Record<string, GNode>; onSelect: (id: string) => void }) {
  const [all, setAll] = useState(false);
  const rows = useMemo(() => rowsOf(h.patch), [h.patch]);
  const shown = all ? rows : rows.slice(0, MAX_LINES);
  return (
    <div className={`df-hunk ${hot ? "hot" : ""}`} data-hunk={h.id}>
      <div className="df-hunk-h">
        <span className="mono df-range">lines {h.new_start}–{h.new_end}</span>
        <span className="df-owners">
          {h.owners.length === 0 && <span className="chip">{OWNER_WORDS[h.owner_kind] ?? h.owner_kind}</span>}
          {h.owners.map((o) => {
            const n = nodes[o];
            const pick = n && (n.layer === "changed" || n.layer === "ghost") && (n.kind === "function" || n.kind === "method");
            return pick
              ? <button key={o} className="chip df-owner" onClick={() => onSelect(o)} title={`Select ${o} in the graph`}>{short(o)}{n.layer === "ghost" ? " (deleted)" : ""}</button>
              : <span key={o} className="chip">{OWNER_WORDS[h.owner_kind] ?? h.owner_kind}{n ? ` · ${n.label}` : ""}</span>;
          })}
        </span>
        <span className="df-count mono"><b className="add">+{h.added}</b> <b className="del">−{h.removed}</b></span>
      </div>
      <pre className="df-patch">
        {shown.map((r, i) => (
          <span key={i} className={`df-row ${r.kind}`}>
            <i className="ln">{r.old ?? ""}</i><i className="ln">{r.neu ?? ""}</i>
            <span className="tx">{r.kind === "hh" ? r.text : (r.kind === "add" ? "+" : r.kind === "del" ? "-" : " ") + r.text}</span>
          </span>
        ))}
      </pre>
      {rows.length > MAX_LINES && !all && <button className="btn sm df-more" onClick={() => setAll(true)}>Show all {rows.length} lines</button>}
    </div>
  );
}

function File({ f, sel, nodes, onSelect, only }: { f: DiffFile; sel: string | null; nodes: Record<string, GNode>; onSelect: (id: string) => void; only: boolean }) {
  const hunks = only && sel ? f.hunks.filter((h) => h.owners.includes(sel)) : f.hunks;
  if (only && sel && hunks.length === 0) return null;
  return (
    <section className="df-file" data-file={f.path}>
      <header className="df-file-h">
        <span className={`chip df-st ${f.status}`}>{STATUS[f.status] ?? f.status}</span>
        <span className="mono df-path">{f.old_path && f.old_path !== f.path ? `${f.old_path} → ${f.path}` : f.path}</span>
        <span className="df-count mono"><b className="add">+{f.added}</b> <b className="del">−{f.removed}</b></span>
      </header>
      {f.no_patch && <p className="lv-muted df-none">{f.is_binary ? "Binary file: there is no text to show." : "Too large to send: the patch was not kept."}</p>}
      {!f.no_patch && f.hunks.length === 0 && <p className="lv-muted df-none">No line changes (a mode change or a pure rename).</p>}
      {hunks.map((h) => <Hunk key={h.id} h={h} hot={!!sel && h.owners.includes(sel)} nodes={nodes} onSelect={onSelect} />)}
    </section>
  );
}

export default function DiffFiles({ a, sel, onSelect }: { a: AnalysisResponse; sel: string | null; onSelect: (id: string) => void }) {
  const files = a.diff_files ?? [];
  const nodes = useMemo(() => Object.fromEntries(a.graph.nodes.map((n) => [n.id, n])) as Record<string, GNode>, [a]);
  const [only, setOnly] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // bring the selected function's first hunk into view inside this panel only: the page itself does not scroll
  useEffect(() => {
    const el = sel ? box.current?.querySelector<HTMLElement>(".df-hunk.hot") : null;
    if (el && box.current) box.current.scrollTo({ top: el.offsetTop - box.current.offsetTop - 8, behavior: "smooth" });
  }, [sel, only]);

  if (files.length === 0) {
    return (
      <Panel title="Files changed" sub="every hunk, tied to the function that owns it">
        <p className="lv-muted">{a.diff_hunks && Object.keys(a.diff_hunks).length ? "This analysis was stored before the file diff existed. The selected function's diff is in the graph panel." : "No file changes were recorded."}</p>
      </Panel>
    );
  }
  const added = files.reduce((s, f) => s + f.added, 0), removed = files.reduce((s, f) => s + f.removed, 0);
  const loose = files.reduce((s, f) => s + f.hunks.filter((h) => h.owner_kind !== "function").length, 0);
  return (
    <Panel
      title="Files changed"
      sub={`${files.length} file${files.length === 1 ? "" : "s"} · +${added} −${removed}${loose ? ` · ${loose} hunk${loose === 1 ? "" : "s"} outside any function` : ""}`}
      aside={<label className="gl-check"><input type="checkbox" checked={only} disabled={!sel} onChange={(e) => setOnly(e.target.checked)} /> Selected function only</label>}
    >
      <div ref={box} className="df-box">
        {files.map((f) => <File key={f.path} f={f} sel={sel} nodes={nodes} onSelect={onSelect} only={only} />)}
      </div>
    </Panel>
  );
}
