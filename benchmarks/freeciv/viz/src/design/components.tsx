import type { ReactNode } from "react";
import { isSig, pval } from "../lib/format";

export function Page({ title, sub, children }: { title: string; sub?: ReactNode; children: ReactNode }) {
  return (
    <div className="page">
      <div className="page-head">
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {children}
    </div>
  );
}

export function Tile({ k, v, sub, hero, color }: { k: string; v: ReactNode; sub?: ReactNode; hero?: boolean; color?: string }) {
  return (
    <div className={"tile" + (hero ? " hero" : "")}>
      <div className="k">{k}</div>
      <div className="v" style={color ? { color: `var(${color})` } : undefined}>{v}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export function Card({ title, note, children }: { title?: ReactNode; note?: ReactNode; children: ReactNode }) {
  return (
    <div className="card">
      {title && <h2>{title}</h2>}
      {note && <div className="note">{note}</div>}
      {children}
    </div>
  );
}

export function Loading({ what = "data" }: { what?: string }) {
  return <div className="spinner">Loading {what}…</div>;
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
export function ErrorNote({ error }: { error: string }) {
  return <div className="lint issues" style={{ marginTop: 12 }}>Could not load data: {error}</div>;
}

export function Legend({ items }: { items: { label: string; cssVar: string }[] }) {
  return (
    <div className="legend">
      {items.map((i) => (
        <span className="item" key={i.label}>
          <span className="sw" style={{ background: `var(${i.cssVar})` }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

export function SigBadge({ p }: { p: number | null | undefined }) {
  const sig = isSig(p);
  return (
    <span className={"badge " + (sig ? "good" : "neutral")} title="two-sided sign-test p-value">
      p={pval(p)} {sig ? "· significant" : "· n.s."}
    </span>
  );
}

export function WinnerBadge({ winner, arms }: { winner?: string | null; arms?: { key: string; cssVar: string; short: string }[] }) {
  if (!winner || winner === "tie") return <span className="badge neutral">tie</span>;
  const a = arms?.find((x) => x.key === winner);
  return (
    <span className="badge good">
      {a && <span className="sw" style={{ background: `var(${a.cssVar})` }} />}
      {a ? a.short : winner} wins
    </span>
  );
}
