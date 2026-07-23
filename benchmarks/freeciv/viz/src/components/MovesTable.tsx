import { useState } from "react";
import type { Move, MoveTurn, Trace } from "../lib/schema";
import TraceView from "./TraceView";

function fmtTarget(t: Move["target"]): string {
  if (!t) return "—";
  if (t.x != null && t.y != null) return `(${t.x}, ${t.y})`;
  if (t.production_type) return String(t.production_type);
  return "—";
}

// Per-turn move table for a game. `slotLabels` name the two slots (contrast arms).
// Clicking a row opens its recorded PLN derivation, or marks it LLM-only.
export default function MovesTable({
  turn,
  traces,
  slotLabels,
}: {
  turn: MoveTurn;
  traces: Record<string, Trace>;
  slotLabels: [string, string];
}) {
  const rows: { side: string; sideVar: string; mv: Move }[] = [
    ...turn.pln.map((mv) => ({ side: slotLabels[0], sideVar: "--arm-chaining", mv })),
    ...turn.plain.map((mv) => ({ side: slotLabels[1], sideVar: "--arm-plain", mv })),
  ];
  const [open, setOpen] = useState<number | null>(null);

  if (!rows.length) return <div className="empty">No unit moves recorded for turn {turn.turn}.</div>;

  return (
    <table className="tbl">
      <thead>
        <tr>
          <th></th><th>Side</th><th>Actor</th><th>Action</th><th>Target</th><th>Valid</th><th>Origin</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const mv = r.mv;
          const isOpen = open === i;
          return (
            <RowGroup
              key={i}
              open={isOpen}
              onToggle={() => setOpen(isOpen ? null : i)}
              side={r.side}
              sideVar={r.sideVar}
              mv={mv}
              trace={mv.trace_id ? traces[mv.trace_id] : undefined}
            />
          );
        })}
      </tbody>
    </table>
  );
}

function RowGroup({
  open,
  onToggle,
  side,
  sideVar,
  mv,
  trace,
}: {
  open: boolean;
  onToggle: () => void;
  side: string;
  sideVar: string;
  mv: Move;
  trace?: Trace;
}) {
  return (
    <>
      <tr className="rowbtn" onClick={onToggle}>
        <td className="muted">{open ? "▾" : "▸"}</td>
        <td>
          <span className="badge neutral"><span className="sw" style={{ background: `var(${sideVar})` }} />{side}</span>
        </td>
        <td className="tnum">{mv.actor}</td>
        <td className="mono">{mv.action_type}</td>
        <td>{fmtTarget(mv.target)}</td>
        <td>{mv.valid ? <span className="pill ok">✓</span> : <span className="pill bad">✗</span>}</td>
        <td>{mv.pln_recommended ? <span className="pill pln">PLN ✓</span> : <span className="pill llm">LLM-only</span>}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={7} style={{ background: "color-mix(in srgb, var(--ink) 3%, transparent)" }}>
            <div style={{ padding: "6px 4px 12px 24px" }}>
              {!mv.valid && (
                <div className="trace-invalid">
                  ✗ rejected pre-submit — {mv.error_code || "invalid"}: {mv.error_message || "no reason recorded"}
                </div>
              )}
              {trace ? (
                <TraceView trace={trace} />
              ) : mv.pln_recommended ? (
                <div className="trace-llm-only">PLN recommended this actor this turn, but the per-derivation trace was not recorded (older run).</div>
              ) : (
                <div className="trace-llm-only">LLM-only decision — no PLN derivation.</div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
