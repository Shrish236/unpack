// Static snapshot mode (GitHub Pages): the build has no API, so reads come from JSON files under public/data/
// that scripts/snapshot.mjs saved from the live server. Set VITE_STATIC=1 to build this way.
export const STATIC = import.meta.env.VITE_STATIC === "1";

// "/api/dashboard/exec?period=30d" -> "api_dashboard_exec_period_30d.json". Keep in step with name() in scripts/snapshot.mjs.
export const snapshotName = (path: string) => path.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "") + ".json";

const TURNS = /^(\/api\/analyses\/[^/?]+\/turns)\?ids=(.*)$/;

// Returns the stored JSON for an API path, or null when the snapshot has no such file.
export async function readSnapshot<T>(path: string): Promise<T | null> {
  const turns = TURNS.exec(path);
  const file = snapshotName(turns ? turns[1] : path);
  const r = await fetch(`${import.meta.env.BASE_URL}data/${file}`, { headers: { accept: "application/json" } });
  // A static host answers a missing file with its 404 page, or with index.html on some hosts: only JSON counts.
  if (!r.ok || !(r.headers.get("content-type") ?? "").includes("json")) return null;
  const body = await r.json();
  if (!turns) return body as T;
  // The snapshot keeps every turn an analysis cites; the page asks for the ones it needs.
  const want = new Set(turns[2].split(",").filter(Boolean));
  return { turns: (body.turns as { turn_id: string }[]).filter((t) => want.has(t.turn_id)) } as T;
}
