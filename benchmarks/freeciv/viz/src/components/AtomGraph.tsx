import type { Snapshot, Atom } from "../lib/schema";
import { fmtStv } from "../lib/stv";
import { showTip, hideTip } from "../charts/tooltip";

// Layered graph: observed/derived facts (left) → rules (middle) → inferred
// recommendations (right). Edges follow each inferred atom's premises[]. An edge is
// "engine-confirmed" (green) when the recommendation came from the real interpreter
// (origin "derive"), else neutral (host-fallback).
export default function AtomGraph({ snap }: { snap: Snapshot }) {
  const byId = new Map(snap.atoms.map((a) => [a.id, a]));
  const inferred = snap.atoms.filter((a) => a.kind === "inferred");
  const usedFactIds = new Set<string>();
  const usedRuleIds = new Set<string>();
  for (const inf of inferred)
    for (const pid of inf.premises ?? []) {
      const a = byId.get(pid);
      if (a?.kind === "rule") usedRuleIds.add(pid);
      else if (a) usedFactIds.add(pid);
    }
  const facts = snap.atoms.filter((a) => (a.kind === "fact" && usedFactIds.has(a.id)));
  const rules = snap.atoms.filter((a) => a.kind === "rule" && usedRuleIds.has(a.id));

  if (!inferred.length) {
    return <div className="empty">No recommendations were derived for this snapshot (no fact fired a rule).</div>;
  }

  const colX = { fact: 20, rule: 300, rec: 560 };
  const boxW = 240;
  const rowH = 42;
  const rows = Math.max(facts.length, rules.length, inferred.length, 1);
  const H = rows * rowH + 40;
  const W = 820;
  const yOf = (list: Atom[], i: number) => 30 + (i + 0.5) * ((rows * rowH) / Math.max(1, list.length));

  const pos = new Map<string, { x: number; y: number }>();
  facts.forEach((a, i) => pos.set(a.id, { x: colX.fact + boxW, y: yOf(facts, i) }));
  rules.forEach((a, i) => pos.set(a.id, { x: colX.rule, y: yOf(rules, i) }));
  inferred.forEach((a, i) => pos.set(a.id, { x: colX.rec, y: yOf(inferred, i) }));

  const edges: { from: string; to: string; confirmed: boolean }[] = [];
  for (const inf of inferred) {
    const confirmed = (inf.origin || "").includes("derive");
    for (const pid of inf.premises ?? []) if (pos.has(pid)) edges.push({ from: pid, to: inf.id, confirmed });
  }

  const tip = (a: Atom) => (e: React.MouseEvent) =>
    showTip(
      `<div class="tt-t">${a.category} · ${a.provenance}</div><div class="mono" style="font-size:11px">${a.statement}</div>${
        a.stv ? `<div class="row"><span>truth</span><b>${fmtStv(a.stv)}</b></div>` : ""
      }${a.kind === "inferred" ? `<div class="row"><span>source</span><b>${a.origin}</b></div>` : ""}`,
      e.clientX,
      e.clientY
    );

  return (
    <div className="chart" style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} role="img" aria-label="atom derivation graph">
        <text className="colhead" x={colX.fact} y={16}>observed facts</text>
        <text className="colhead" x={colX.rule} y={16}>rules</text>
        <text className="colhead" x={colX.rec} y={16}>derived recommendations</text>
        {edges.map((ed, i) => {
          const a = pos.get(ed.from)!;
          const b = pos.get(ed.to)!;
          const mx = (a.x + b.x) / 2;
          return (
            <path key={i} className={"atomedge" + (ed.confirmed ? " confirmed" : "")}
              d={`M${a.x},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}`} />
          );
        })}
        {[
          { list: facts, x: colX.fact, fill: "var(--surface-1)", stroke: "var(--axis)" },
          { list: rules, x: colX.rule, fill: "color-mix(in srgb, var(--arm-chaining) 10%, var(--surface-1))", stroke: "var(--arm-chaining)" },
          { list: inferred, x: colX.rec, fill: "color-mix(in srgb, var(--good) 12%, var(--surface-1))", stroke: "var(--good)" },
        ].map((col) =>
          col.list.map((a) => {
            const p = pos.get(a.id)!;
            const x = col.x;
            const y = p.y - 15;
            return (
              <g key={a.id} className="atomnode" onMouseMove={tip(a)} onMouseLeave={hideTip}>
                <rect x={x} y={y} width={boxW} height={30} rx={6} fill={col.fill} stroke={col.stroke} strokeWidth={1.2} />
                <text className="atom" x={x + 8} y={y + 19} fill="var(--ink)">{trunc(a.statement, 34)}</text>
              </g>
            );
          })
        )}
      </svg>
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        green edge = confirmed by the in-container engine (source “derive”); gray = host-fallback rule match. Hover a node for its truth value.
      </div>
    </div>
  );
}

function trunc(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
