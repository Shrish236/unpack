// Tiny neutral people (head circle + rounded body, no face or gender cues), a sigh cloud and a coffee cup.
export function Person({ kind = "dev", lean = false, size = 28 }: { kind?: "dev" | "lead"; lean?: boolean; size?: number }) {
  return (
    <svg className={`s1-person ${kind} ${lean ? "lean" : ""}`} width={size} height={size} viewBox="0 0 28 28" aria-hidden="true">
      <circle cx="14" cy="7" r="5" />
      <path d="M5 27v-4a9 9 0 0 1 18 0v4z" />
    </svg>
  );
}

export function Sigh({ s = 1, show = true }: { s?: number; show?: boolean }) {
  return (
    <svg className="s1-sigh" data-show={show} viewBox="0 0 28 16" width={22} height={13} style={{ ["--s" as string]: s }} aria-hidden="true">
      <path d="M7 14a4.5 4.5 0 0 1 0-9 6 6 0 0 1 11-1.5 4.5 4.5 0 0 1 3.5 10.5z" />
      <path d="M9 9.5h2M13 9.5h2M17 9.5h2" className="dots" />
    </svg>
  );
}

export function Cup() {
  return (
    <svg className="s1-cup" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path d="M3 6h9v5a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4z" /><path d="M12 7.5h1.5a2 2 0 0 1 0 4H12" className="h" />
      <path d="M6 1.5v2M9 1.5v2" className="steam" />
    </svg>
  );
}
