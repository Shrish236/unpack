import type { ReactNode } from "react";
import { ApiError } from "./api";
import { TYPE_LABEL, type DType } from "./data";

// Shared primitives so every product page uses identical markup and type sizes.
export function Panel({ title, sub, aside, children, className = "" }: { title?: ReactNode; sub?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      {(title || aside) && (
        <div className="panel-h">
          <div><h2 className="panel-title">{title}</h2>{sub && <div className="panel-sub">{sub}</div>}</div>
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kpi({ value, label, sub, tone }: { value: ReactNode; label: string; sub?: ReactNode; tone?: "hot" | "bad" | "ok" | "agent" }) {
  return (
    <div className="kpi">
      <b className={`kpi-num ${tone ?? ""}`}>{value}</b>
      <span className="kpi-label">{label}</span>
      {sub && <small className="kpi-sub">{sub}</small>}
    </div>
  );
}

export function TypeChip({ t }: { t: DType }) {
  return <span className={`chip t-${t}`}><i />{TYPE_LABEL[t]}</span>;
}

export function PageHead({ crumbs, title, sub, meta }: { crumbs?: ReactNode; title: string; sub?: ReactNode; meta?: ReactNode }) {
  return (
    <>
      {crumbs && <div className="crumbs mono">{crumbs}</div>}
      <header className="page-head">
        <div>
          <h1 className="page-title">{title}</h1>
          {sub && <p className="page-sub">{sub}</p>}
          {meta && <div className="meta">{meta}</div>}
        </div>
      </header>
    </>
  );
}

export function Seg<T extends string>({ value, options, onChange }: { value: T; options: { id: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="seg" role="tablist">
      {options.map((o) => (
        <button key={o.id} className={value === o.id ? "on" : ""} onClick={() => onChange(o.id)} role="tab" aria-selected={value === o.id}>{o.label}</button>
      ))}
    </div>
  );
}

// Loading and error states for a dashboard page. Children render only with data.
export function DataGate<T>({ q, children }: { q: { data: T | undefined; error: Error | null; isError: boolean }; children: (data: T) => ReactNode }) {
  if (q.data !== undefined) return <>{children(q.data)}</>;
  if (q.isError && q.error) {
    const login = q.error instanceof ApiError && q.error.kind === "login";
    return (
      <Panel title={login ? "Log in to see this page" : "This page could not load"} sub={q.error.message}
        aside={login ? <a className="btn primary" href="/auth/login">Log in with GitHub</a> : undefined}>
        {null}
      </Panel>
    );
  }
  return <Panel><p className="panel-sub">Loading…</p></Panel>;
}
