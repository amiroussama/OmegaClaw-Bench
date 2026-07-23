import { useRef, useState } from "react";
import { cssColor } from "../lib/arms";
import { showTip, hideTip } from "./tooltip";

export interface Series {
  key: string;
  label: string;
  cssVar: string;
  points: { x: number; y: number | null }[];
}

const W = 640;
const H = 220;
const M = { t: 12, r: 64, b: 26, l: 34 };

// Multi-series line chart: 2px lines, recessive grid, crosshair + shared tooltip,
// direct end-labels (≤4 series). One y-axis only.
export default function LineChart({
  title,
  series,
  yInteger = true,
}: {
  title: string;
  series: Series[];
  yInteger?: boolean;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [hoverX, setHoverX] = useState<number | null>(null);

  const xs = series.flatMap((s) => s.points.map((p) => p.x));
  const ys = series.flatMap((s) => s.points.map((p) => p.y).filter((v): v is number => v != null));
  if (xs.length === 0 || ys.length === 0) {
    return (
      <div className="chart">
        <div className="ct">{title}</div>
        <div className="empty">no data</div>
      </div>
    );
  }
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  const ymin = 0;
  const ymax = Math.max(...ys, 1);
  const sx = (x: number) => M.l + ((x - xmin) / Math.max(1, xmax - xmin)) * (W - M.l - M.r);
  const sy = (y: number) => H - M.b - (y / (ymax - ymin)) * (H - M.t - M.b);

  const yticks = niceTicks(ymin, ymax, 4, yInteger);
  const xticks = niceTicks(xmin, xmax, 6, true);

  function onMove(e: React.MouseEvent) {
    const svg = ref.current;
    if (!svg) return;
    const pt = svg.getBoundingClientRect();
    const px = ((e.clientX - pt.left) / pt.width) * W;
    // nearest integer x within domain
    const xv = Math.round(xmin + ((px - M.l) / (W - M.l - M.r)) * (xmax - xmin));
    const xc = Math.min(xmax, Math.max(xmin, xv));
    setHoverX(xc);
    const rows = series
      .map((s) => {
        const p = s.points.find((q) => q.x === xc);
        if (!p || p.y == null) return "";
        return `<div class="row"><span style="color:${cssColor(s.cssVar)}">${s.label}</span><b>${p.y}</b></div>`;
      })
      .join("");
    showTip(`<div class="tt-t">turn ${xc}</div>${rows}`, e.clientX, e.clientY);
  }
  function onLeave() {
    setHoverX(null);
    hideTip();
  }

  return (
    <div className="chart">
      <div className="ct">{title}</div>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} onMouseMove={onMove} onMouseLeave={onLeave} role="img" aria-label={title}>
        <g className="grid-lines">
          {yticks.map((t) => (
            <line key={t} x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} />
          ))}
        </g>
        <g className="axis">
          <line x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b} />
          {yticks.map((t) => (
            <text key={t} x={M.l - 6} y={sy(t) + 3} textAnchor="end">{t}</text>
          ))}
          {xticks.map((t) => (
            <text key={t} x={sx(t)} y={H - M.b + 14} textAnchor="middle">{t}</text>
          ))}
        </g>
        {hoverX != null && (
          <line className="crosshair" x1={sx(hoverX)} x2={sx(hoverX)} y1={M.t} y2={H - M.b} />
        )}
        {series.map((s) => {
          const col = cssColor(s.cssVar);
          const pts = s.points.filter((p) => p.y != null) as { x: number; y: number }[];
          if (!pts.length) return null;
          const d = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
          const last = pts[pts.length - 1];
          return (
            <g key={s.key}>
              <path d={d} fill="none" stroke={col} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {hoverX != null &&
                (() => {
                  const p = pts.find((q) => q.x === hoverX);
                  return p ? <circle cx={sx(p.x)} cy={sy(p.y)} r={4} fill={col} stroke="var(--surface-1)" strokeWidth={2} /> : null;
                })()}
              {series.length <= 4 && (
                <text className="serieslabel" x={sx(last.x) + 6} y={sy(last.y) + 3} fill={col}>
                  {s.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function niceTicks(min: number, max: number, count: number, integer: boolean): number[] {
  if (max <= min) return [min];
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  let step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
  if (integer) step = Math.max(1, Math.round(step));
  const out: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step) {
    out.push(integer ? Math.round(t) : Math.round(t * 100) / 100);
  }
  return out;
}
