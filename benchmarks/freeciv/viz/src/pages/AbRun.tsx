import { Link } from "react-router-dom";
import { useCatalog, useRunDetail } from "../lib/data";
import RunPicker, { currentRun } from "../components/RunPicker";
import LineChart, { type Series } from "../charts/LineChart";
import { Page, Card, Loading, ErrorNote, Empty, Legend, WinnerBadge } from "../design/components";
import { useSelection } from "../lib/nav";
import { armStyle } from "../lib/arms";
import { num } from "../lib/format";
import type { Game, TrajPoint, Stats } from "../lib/schema";

const TRAJ = [
  { field: "n_cities", title: "Cities" },
  { field: "n_units", title: "Units" },
  { field: "n_techs", title: "Techs" },
] as const;
const ACT = [
  { field: "n_conclusions", title: "PLN conclusions / turn", int: true },
  { field: "illegal_rate", title: "Illegal-action rate", int: false },
  { field: "reason_ms", title: "Reasoning latency (ms)", int: true },
] as const;

export default function AbRun() {
  const { data: cat, error, loading } = useCatalog();
  const { runId } = useSelection();
  const run = cat ? currentRun(cat, runId, "ab") : null;
  const detail = useRunDetail(run?.detail);

  if (loading) return <Page title="A/B run"><Loading what="catalog" /></Page>;
  if (error) return <Page title="A/B run"><ErrorNote error={error} /></Page>;
  if (!cat) return null;
  if (!cat.runs.some((r) => r.type === "ab")) {
    return <Page title="A/B run"><Empty>No A/B runs found.</Empty></Page>;
  }

  const g = detail.data?.games?.[0];
  const arms = detail.data?.arms ?? [];

  return (
    <Page title="A/B run" sub="Each arm plays its own game vs the built-in AI; only the state representation differs.">
      <RunPicker catalog={cat} filter="ab" />
      {detail.loading && <Loading what="run" />}
      {detail.error && <ErrorNote error={detail.error} />}
      {g && (
        <>
          <div style={{ display: "flex", gap: 12, alignItems: "center", margin: "6px 0 12px", flexWrap: "wrap" }}>
            <WinnerBadge winner={detail.data?.overall} arms={arms.map((a) => armStyle(a))} />
            <span className="muted">{detail.data?.verdict}</span>
            {run?.has_moves && <Link to={`/reasoning?run=${run.safe_id}`}>inspect reasoning →</Link>}
            {run?.has_atoms && <Link to={`/atoms?run=${run.safe_id}`}>inspect atoms →</Link>}
          </div>

          <StatsTable game={g} arms={arms} />

          <Legend items={arms.map((a) => ({ label: armStyle(a).short, cssVar: armStyle(a).cssVar }))} />
          <div className="section">
            <h2>Game state over time</h2>
            <div className="charts-grid">
              {TRAJ.map((m) => (
                <LineChart key={m.field} title={m.title} series={buildSeries(g, arms, m.field)} yInteger />
              ))}
            </div>
          </div>
          <div className="section">
            <h2>Activity &amp; reasoning</h2>
            <div className="charts-grid">
              {ACT.map((m) => (
                <LineChart key={m.field} title={m.title} series={buildSeries(g, arms, m.field)} yInteger={m.int} />
              ))}
            </div>
          </div>
        </>
      )}
    </Page>
  );
}

function buildSeries(g: Game, arms: string[], field: string): Series[] {
  const src = g.series_all ?? {};
  return arms
    .map((arm) => {
      const pts = (src[arm] ?? []) as TrajPoint[];
      const st = armStyle(arm);
      return {
        key: arm,
        label: st.short,
        cssVar: st.cssVar,
        points: pts.map((p) => ({ x: p.turn, y: (p as unknown as Record<string, number | null | undefined>)[field] ?? null })),
      };
    })
    .filter((s) => s.points.some((p) => p.y != null));
}

function StatsTable({ game, arms }: { game: Game; arms: string[] }) {
  const stats = game.stats_all ?? {};
  const fin = (s: Stats | null | undefined) => (s?.final ?? {}) as Record<string, number>;
  return (
    <Card title="Final state by arm">
      <table className="tbl">
        <thead>
          <tr><th>Arm</th><th className="num">cities</th><th className="num">units</th><th className="num">techs</th><th className="num">score</th><th className="num">illegal rate</th><th className="num">avg reason ms</th></tr>
        </thead>
        <tbody>
          {arms.map((a) => {
            const s = stats[a];
            const f = fin(s);
            return (
              <tr key={a}>
                <td><span className="badge neutral"><span className="sw" style={{ background: `var(${armStyle(a).cssVar})` }} />{armStyle(a).short}</span></td>
                <td className="num">{num(f.n_cities)}</td>
                <td className="num">{num(f.n_units)}</td>
                <td className="num">{num(f.n_techs)}</td>
                <td className="num">{num(f.score)}</td>
                <td className="num">{num((s as Stats)?.illegal_rate as number, 2)}</td>
                <td className="num">{num((s as Stats)?.avg_reason_ms as number)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
