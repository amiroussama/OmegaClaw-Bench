import { armStyle } from "../lib/arms";
import { showTip, hideTip } from "./tooltip";

// Per-seed winner matrix: rows = seeds, cols = contrasts. Each cell is colored by
// the winning arm's validated hue (tie = muted). Hover shows the detail; the arm
// legend + the text label under each column carry identity (never color-alone).
export default function Heatmap({
  seeds,
  columns,
  winnerOf,
}: {
  seeds: string[];
  columns: { key: string; label: string }[];
  winnerOf: (seed: string, colKey: string) => string | null; // arm key or "tie"/null
}) {
  const cell = 26;
  const labelW = 120;
  const headH = 40;
  const W = labelW + columns.length * (cell + 4);
  const H = headH + seeds.length * (cell + 4);

  return (
    <div className="chart" style={{ overflowX: "auto" }}>
      <div className="ct">Per-seed winners</div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} role="img" aria-label="per-seed winner matrix">
        {columns.map((c, ci) => (
          <text key={c.key} x={labelW + ci * (cell + 4) + cell / 2} y={headH - 8} textAnchor="end"
            fontSize={10.5} fill="var(--muted)" transform={`rotate(-35 ${labelW + ci * (cell + 4) + cell / 2} ${headH - 8})`}>
            {c.label}
          </text>
        ))}
        {seeds.map((s, ri) => (
          <g key={s}>
            <text x={labelW - 8} y={headH + ri * (cell + 4) + cell / 2 + 4} textAnchor="end" fontSize={10.5} fill="var(--ink-2)" className="tnum">
              {s}
            </text>
            {columns.map((c, ci) => {
              const w = winnerOf(s, c.key);
              const fill = !w || w === "tie" ? "var(--grid)" : `var(${armStyle(w).cssVar})`;
              const x = labelW + ci * (cell + 4);
              const y = headH + ri * (cell + 4);
              return (
                <rect
                  key={c.key}
                  x={x}
                  y={y}
                  width={cell}
                  height={cell}
                  rx={5}
                  fill={fill}
                  stroke="var(--surface-1)"
                  strokeWidth={1}
                  onMouseMove={(e) =>
                    showTip(
                      `<div class="tt-t">seed ${s}</div><div class="row"><span>${c.label}</span><b>${
                        !w || w === "tie" ? "tie" : armStyle(w).short
                      }</b></div>`,
                      e.clientX,
                      e.clientY
                    )
                  }
                  onMouseLeave={hideTip}
                />
              );
            })}
          </g>
        ))}
      </svg>
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        cell color = winning arm (see legend); gray = tie
      </div>
    </div>
  );
}
