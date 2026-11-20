// Live / Mock switch shown on both PR pages.
export default function PrMode({ mode }: { mode: "live" | "mock" }) {
  return (
    <span className="seg" role="group" aria-label="Data source">
      <a className={mode === "live" ? "on" : ""} href="#/pr">Live</a>
      <a className={mode === "mock" ? "on" : ""} href="#/pr/mock">Mock</a>
    </span>
  );
}
