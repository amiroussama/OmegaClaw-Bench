import { useState } from "react";
import type { Snapshot, Atom } from "../lib/schema";
import { fmtStv } from "../lib/stv";

const PROV_LABEL: Record<string, string> = {
  observed: "Observed facts",
  "derived-heuristic": "Derived (heuristic) facts",
  rule: "Rules (strategic heuristics)",
  "inferred-pln": "Inferred — PLN recommendations",
  unknown: "Unknown provenance",
};
const PROV_ORDER = ["observed", "derived-heuristic", "rule", "inferred-pln", "unknown"];

// Atoms grouped by provenance, collapsible; each line shows statement · stv · category.
export default function AtomList({ snap, filter }: { snap: Snapshot; filter: string }) {
  const byProv = new Map<string, Atom[]>();
  for (const a of snap.atoms) {
    if (filter && !a.statement.toLowerCase().includes(filter.toLowerCase())) continue;
    const p = a.provenance || "unknown";
    (byProv.get(p) ?? byProv.set(p, []).get(p)!).push(a);
  }
  const provs = PROV_ORDER.filter((p) => byProv.has(p)).concat(
    [...byProv.keys()].filter((p) => !PROV_ORDER.includes(p))
  );
  if (!provs.length) return <div className="empty">no atoms match “{filter}”.</div>;
  return (
    <>
      {provs.map((p) => (
        <ProvGroup key={p} label={PROV_LABEL[p] ?? p} atoms={byProv.get(p)!} />
      ))}
    </>
  );
}

function ProvGroup({ label, atoms }: { label: string; atoms: Atom[] }) {
  const [open, setOpen] = useState(atoms.length <= 30);
  return (
    <details className="provgroup" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>
        {label}
        <span className="count">{atoms.length}</span>
      </summary>
      {atoms.map((a) => (
        <div className="atomline" key={a.id}>
          <span>{a.statement}</span>
          <span className="stv">{a.stv ? fmtStv(a.stv) : a.kind === "inferred" ? "(derived)" : ""}</span>
          <span className="cat">{a.category}</span>
        </div>
      ))}
    </details>
  );
}
