import { useSearchParams } from "react-router-dom";
import { useCatalog } from "../lib/data";
import { Page, Card, Loading, ErrorNote, Empty, SigBadge, Legend } from "../design/components";
import DeltaPlot from "../charts/DeltaPlot";
import Heatmap from "../charts/Heatmap";
import { contrastsWithGames } from "../lib/agg";
import { armStyle } from "../lib/arms";
import { num, signed, pval } from "../lib/format";
import type { Aggregate, ContrastSummary } from "../lib/schema";

export default function Batch() {
  const { data: cat, error, loading } = useCatalog();
  const [sp, setSp] = useSearchParams();
  if (loading) return <Page title="Batch"><Loading what="catalog" /></Page>;
  if (error) return <Page title="Batch"><ErrorNote error={error} /></Page>;
  if (!cat) return null;
  if (!cat.batches.length) return <Page title="Batch"><Empty>No batches found.</Empty></Page>;

  const sel = sp.get("batch");
  const batch = cat.batches.find((b) => b.safe_id === sel) ?? cat.batches[0];
  const agg = batch.aggregate;
  const contrasts = contrastsWithGames(agg);

  return (
    <Page title="Batch results" sub={`${batch.id} · ${agg.seeds_scanned} seeds`}>
      <div className="controls">
        <label className="ctl">
          Batch
          <select value={batch.safe_id} onChange={(e) => setSp({ batch: e.target.value }, { replace: true })}>
            {cat.batches.map((b) => <option key={b.safe_id} value={b.safe_id}>{b.id}</option>)}
          </select>
        </label>
      </div>

      {contrasts.length === 0 && <Empty>No contrast has decided games in this batch.</Empty>}

      {contrasts.map((c) => <ContrastCard key={`${c.a}_vs_${c.b}`} c={c} />)}

      <div className="section">
        <PerSeed agg={agg} contrasts={contrasts} />
      </div>
    </Page>
  );
}

function ContrastCard({ c }: { c: ContrastSummary }) {
  const A = armStyle(c.a), B = armStyle(c.b);
  const deltas = Object.entries(c.deltas_pln_minus_plain).map(([k, d]) => ({
    label: k.replace("n_", ""), mean: d.mean, t: d.t, p: d.p_approx,
  }));
  return (
    <div className="card section">
      <h2>{A.short} vs {B.short}</h2>
      <div className="note">{c.label}</div>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
        <span className="badge good">
          <span className="sw" style={{ background: `var(${A.cssVar})` }} />
          {A.short} {c.wins[c.a] ?? 0}
        </span>
        <span className="muted">–</span>
        <span className="badge neutral">
          <span className="sw" style={{ background: `var(${B.cssVar})` }} />
          {B.short} {c.wins[c.b] ?? 0}
        </span>
        {c.wins.tie ? <span className="badge neutral">{c.wins.tie} tie</span> : null}
        <span className="muted">· {c.n_games} games</span>
        <SigBadge p={c.sign_test_p} />
      </div>
      <div className="grid two-col">
        <DeltaPlot items={deltas} aLabel={A.short} bLabel={B.short} />
        <div>
          <table className="tbl">
            <thead><tr><th>metric</th><th className="num">mean Δ</th><th className="num">t</th><th className="num">p≈</th></tr></thead>
            <tbody>
              {Object.entries(c.deltas_pln_minus_plain).map(([k, d]) => (
                <tr key={k}>
                  <td>{k.replace("n_", "")}</td>
                  <td className="num">{signed(d.mean)}</td>
                  <td className="num">{d.t != null ? d.t.toFixed(2) : "—"}</td>
                  <td className="num">{pval(d.p_approx)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {c.pln_quality && (
            <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
              PLN quality (mean over {c.pln_quality.n} runs): action success {num(c.pln_quality.mean_pln_action_success_rate ? c.pln_quality.mean_pln_action_success_rate * 100 : null)}% ·
              rec adoption {num(c.pln_quality.mean_rec_adoption_rate ? c.pln_quality.mean_rec_adoption_rate * 100 : null)}%
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PerSeed({ agg, contrasts }: { agg: Aggregate; contrasts: ContrastSummary[] }) {
  const seeds = agg.per_seed.map((r) => r.seed).filter(Boolean);
  const columns = contrasts.map((c) => ({ key: `${c.a}_vs_${c.b}`, label: `${armStyle(c.a).short}÷${armStyle(c.b).short}` }));
  const bySeed = new Map(agg.per_seed.map((r) => [r.seed, r]));
  // arm legend from the arms that appear across contrasts
  const armKeys = Array.from(new Set(contrasts.flatMap((c) => [c.a, c.b])));
  return (
    <Card title="Per-seed winners" note="Each cell = the winning arm for that seed & contrast.">
      <Legend items={armKeys.map((k) => ({ label: armStyle(k).short, cssVar: armStyle(k).cssVar }))} />
      <Heatmap
        seeds={seeds}
        columns={columns}
        winnerOf={(seed, colKey) => {
          const row = bySeed.get(seed);
          return (row?.[`ab:${colKey}`] as string) ?? null;
        }}
      />
    </Card>
  );
}
