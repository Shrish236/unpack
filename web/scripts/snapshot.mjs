// Snapshots every read endpoint the UI uses from a running Unpack server into public/data/*.json,
// so the static GitHub Pages build can show the same dashboard without a backend.
//   node scripts/snapshot.mjs https://unpack-<project-number>.asia-south1.run.app
// The file name for a request comes from snapshotName() in src/staticData.ts; keep the two in step.
import { mkdir, rm, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const base = (process.argv[2] || process.env.UNPACK_API || "").replace(/\/$/, "");
if (!base) { console.error("usage: node scripts/snapshot.mjs <server-url>"); process.exit(1); }

const out = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "data");
const name = (p) => p.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "") + ".json";
let count = 0;

async function get(p) {
  const r = await fetch(base + p, { headers: { accept: "application/json" } });
  if (!r.ok) throw new Error(`${p} -> HTTP ${r.status}`);
  return r.json();
}
async function save(p) {
  const body = await get(p);
  await writeFile(path.join(out, name(p)), JSON.stringify(body));
  count++;
  return body;
}

await rm(out, { recursive: true, force: true });
await mkdir(out, { recursive: true });

await save("/api/dashboard/exec?period=30d");
await save("/api/dashboard/exec?period=90d");
const { repos } = await save("/api/dashboard/repos");
const { teams } = await save("/api/dashboard/teams");
for (const t of teams) await save(`/api/dashboard/teams/${encodeURIComponent(t.id)}`);
await save("/api/governance");
const { analyses } = await save("/api/analyses");
for (const r of repos) {
  const q = encodeURIComponent(r.full_name);
  await save(`/api/dashboard/repo?repo=${q}`);
  await save(`/api/governance?repo=${q}`);
  await save(`/api/analyses?repo=${q}`);
}

// Turns: the PR page asks for the turns its reasons, findings and user requests cite. Store every cited turn once per analysis.
for (const { public_id: id } of analyses) {
  const a = await save(`/api/analyses/${encodeURIComponent(id)}`);
  if (!a.timeline) continue; // queued or failed: nothing to cite
  const ids = new Set(a.timeline.filter((t) => t.kind === "user_request").map((t) => t.turn));
  Object.values(a.reasons ?? {}).forEach((r) => { r.evidence.forEach((e) => ids.add(e.turn)); r.history.forEach((h) => ids.add(h.turn)); });
  (a.findings ?? []).forEach((f) => f.evidence.forEach((e) => ids.add(e.turn)));
  (a.governance?.decisions ?? []).forEach((d) => ids.add(d.turn));
  const list = [...ids];
  const turns = [];
  for (let i = 0; i < list.length; i += 50) {
    const part = await get(`/api/analyses/${encodeURIComponent(id)}/turns?ids=${list.slice(i, i + 50).join(",")}`);
    turns.push(...part.turns);
  }
  await writeFile(path.join(out, name(`/api/analyses/${encodeURIComponent(id)}/turns`)), JSON.stringify({ turns }));
  count++;
}
console.log(`wrote ${count} files to ${out}`);
