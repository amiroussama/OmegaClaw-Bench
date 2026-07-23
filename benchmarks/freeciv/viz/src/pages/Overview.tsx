import { Link } from "react-router-dom";
import { useCatalog } from "../lib/data";
import { Page, Card, Tile, Loading, ErrorNote, Empty, SigBadge } from "../design/components";
import { primaryContrast } from "../lib/agg";
import { armStyle } from "../lib/arms";
import { num, signed } from "../lib/format";
import type { BatchEntry } from "../lib/schema";

export default function Overview() {
  const { data: cat, error, loading } = useCatalog();
  if (loading) return <Page title="Overview"><Loading what="catalog" /></Page>;
  if (error) return <Page title="Overview"><ErrorNote error={error} /></Page>;
  if (!cat) return null;

  return (
    <Page title="FreeCiv PLN Benchmark" sub={<>Atoms, reasoning traces, and A/B / batch results across every run. <span className="muted">generated {cat.generated}</span></>}>
      <div className="section">
        <h2>Statistical batches</h2>
        <div className="note">Each batch runs the arms across many seeds; the primary contrast headlines the verdict.</div>
        {cat.batches.length ? (
          <div className="grid two-col">
            {cat.batches.map((b) => <BatchCard key={b.safe_id} b={b} />)}
          </div>
        ) : (
          <Empty>No batches found. Run <code>benchmarks/freeciv/batch/batch.sh</code>, then rebuild the data.</Empty>
        )}
      </div>

      <div className="section">
        <h2>Individual runs</h2>
        {cat.runs.length ? (
          <Card>
            <table className="tbl">
              <thead><tr><th>Type</th><th>Run</th><th>Verdict</th><th>Inspect</th></tr></thead>
              <tbody>
                {cat.runs.slice(0, 40).map((r) => (
                  <tr key={r.safe_id}>
                    <td>{r.type === "duel" ? "⚔ duel" : "⇄ A/B"}</td>
                    <td className="mono" style={{ fontSize: 11.5 }}>{r.id}</td>
                    <td>{r.verdict}</td>
                    <td>
                      <Link to={`/ab?run=${r.safe_id}`}>A/B</Link>
                      {r.has_atoms && <> · <Link to={`/atoms?run=${r.safe_id}`}>Atoms</Link></>}
                      {r.has_moves && <> · <Link to={`/reasoning?run=${r.safe_id}`}>Reasoning</Link></>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cat.runs.length > 40 && <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>showing 40 of {cat.runs.length} runs</div>}
          </Card>
        ) : (
          <Empty>No runs found under <code>ab_runs/</code>.</Empty>
        )}
      </div>

      {cat.fixtures.length > 0 && (
        <div className="section">
          <h2>Static KPI micro-benchmarks</h2>
          <div className="tiles">
            {cat.fixtures.map((f) => {
              const s = (f.summary ?? {}) as Record<string, unknown>;
              const inv = (s.invalid_action_rate ?? {}) as Record<string, number>;
              return (
                <Tile key={f.id} k={f.label} v={num(s.n_fixtures)} sub={<>fixtures · illegal {inv.candidate != null ? inv.candidate : "—"} vs {inv.baseline != null ? inv.baseline : "—"}</>} />
              );
            })}
          </div>
        </div>
      )}
    </Page>
  );
}

function BatchCard({ b }: { b: BatchEntry }) {
  const c = primaryContrast(b.aggregate);
  return (
    <div className="card">
      <h2 style={{ fontSize: 13.5 }}>{b.id}</h2>
      <div className="note">{b.aggregate.seeds_scanned} seeds scanned</div>
      {c ? (
        <>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
            <span className="badge good">
              <span className="sw" style={{ background: `var(${armStyle(c.a).cssVar})` }} />
              {armStyle(c.a).short} {c.wins[c.a] ?? 0}–{c.wins[c.b] ?? 0} {armStyle(c.b).short}
            </span>
            <SigBadge p={c.sign_test_p} />
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            {Object.entries(c.deltas_pln_minus_plain).map(([k, d]) => (
              <span key={k} style={{ marginRight: 12 }}>{k.replace("n_", "")} {signed(d.mean)}</span>
            ))}
          </div>
          <div style={{ marginTop: 10 }}>
            <Link to={`/batch?batch=${b.safe_id}`}>Open batch →</Link>
          </div>
        </>
      ) : (
        <Empty>No decided contrasts.</Empty>
      )}
    </div>
  );
}
