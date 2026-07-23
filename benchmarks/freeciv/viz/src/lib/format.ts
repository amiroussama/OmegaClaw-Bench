export function num(v: unknown, d = 0): string {
  if (v === null || v === undefined || (typeof v === "number" && Number.isNaN(v))) return "—";
  if (typeof v !== "number") return String(v);
  return v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: 0 });
}

export function signed(v: number | null | undefined, d = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = v.toFixed(d);
  return v > 0 ? `+${s}` : s;
}

export function pval(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "—";
  if (p < 0.0001) return "<0.0001";
  return p.toFixed(4);
}

// Significance at alpha=0.05 (two-sided). Used for the significance badge.
export function isSig(p: number | null | undefined): boolean {
  return typeof p === "number" && p < 0.05;
}

export function pct(v: number | null | undefined, d = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(d)}%`;
}
