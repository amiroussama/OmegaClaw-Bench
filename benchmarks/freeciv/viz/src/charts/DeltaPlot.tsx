import { signed, pval } from "../lib/format";

export interface DeltaItem {
  label: string;
  mean: number | null;
  t?: number | null;
  p?: number | null;
}

// Horizontal diverging lollipop: bar from a centered zero baseline; positive (favors
// arm A) reads success-green, negative critical-red. Every bar is directly labeled
// with its value + p (never color-alone).
export default function DeltaPlot({ items, aLabel, bLabel }: { items: DeltaItem[]; aLabel: string; bLabel: string }) {
  const vals = items.map((i) => i.mean ?? 0);
  const max = Math.max(0.001, ...vals.map((v) => Math.abs(v)));
  const W = 520;
  const rowH = 34;
  const H = items.length * rowH + 20;
  const cx = 150; // zero baseline x
  const scale = (v: number) => (v / max) * (W - cx - 90);

  return (
    <div className="chart">
      <div className="ct">
        Mean Δ per metric <span className="muted">({aLabel} − {bLabel}; positive favors {aLabel})</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="per-metric mean delta">
        <line className="crosshair" x1={cx} x2={cx} y1={8} y2={H - 8} />
        {items.map((it, i) => {
          const y = 18 + i * rowH;
          const v = it.mean ?? 0;
          const pos = v >= 0;
          const col = pos ? "var(--good-text)" : "var(--critical)";
          const x2 = cx + scale(v);
          return (
            <g key={it.label}>
              <text x={cx - 10} y={y + 4} textAnchor="end" fontSize={11.5} fill="var(--ink-2)">{it.label}</text>
              <line x1={cx} x2={x2} y1={y} y2={y} stroke={col} strokeWidth={6} strokeLinecap="round" />
              <circle cx={x2} cy={y} r={4.5} fill={col} />
              <text x={x2 + (pos ? 9 : -9)} y={y + 4} textAnchor={pos ? "start" : "end"} fontSize={11.5} fill="var(--ink)" className="tnum">
                {signed(it.mean)} {it.p != null ? `· p=${pval(it.p)}` : ""}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
