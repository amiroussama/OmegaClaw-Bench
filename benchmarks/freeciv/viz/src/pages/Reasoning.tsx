import { useCatalog, useRunDetail } from "../lib/data";
import RunPicker, { currentRun } from "../components/RunPicker";
import TurnSlider from "../components/TurnSlider";
import MovesTable from "../components/MovesTable";
import { Page, Card, Loading, ErrorNote, Empty } from "../design/components";
import { useSelection } from "../lib/nav";
import { armStyle, contrastArms } from "../lib/arms";

export default function Reasoning() {
  const { data: cat, error, loading } = useCatalog();
  const { runId, game, turn, set } = useSelection();
  const run = cat ? currentRun(cat, runId, "moves") : null;
  const detail = useRunDetail(run?.detail);

  if (loading) return <Page title="Reasoning"><Loading what="catalog" /></Page>;
  if (error) return <Page title="Reasoning"><ErrorNote error={error} /></Page>;
  if (!cat) return null;
  if (!cat.runs.some((r) => r.has_moves)) {
    return <Page title="Reasoning explorer"><Empty>No run has recorded per-unit moves / traces yet.</Empty></Page>;
  }

  const g = detail.data?.games?.[game];
  const moves = g?.moves ?? [];
  const turns = moves.map((m) => m.turn);
  const curTurn = turn && turns.includes(turn) ? turn : turns[0] ?? null;
  const mt = moves.find((m) => m.turn === curTurn) ?? null;
  const [a, b] = contrastArms(detail.data?.contrast);
  const slotLabels: [string, string] = [armStyle(a).short, armStyle(b).short];

  return (
    <Page title="Reasoning explorer" sub="Per-move derivation chains: premises → hops → conclusion → recommendation. LLM prose is shown separately from the formal trace.">
      <RunPicker catalog={cat} filter="moves" gameCount={detail.data?.games?.length} />
      {detail.loading && <Loading what="run" />}
      {detail.error && <ErrorNote error={detail.error} />}
      {moves.length > 0 && (
        <div className="controls">
          <TurnSlider turns={turns} value={curTurn ?? turns[0]} onChange={(t) => set({ turn: t })} />
        </div>
      )}
      {mt ? (
        <>
          <Card title={`Turn ${mt.turn} — objective`} note="Derived from this turn's PLN recommendations (the sims carry no authored strategy).">
            {mt.recommendations.length ? (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {mt.recommendations.map((r, i) => (
                  <span className="badge neutral" key={i}>
                    <span className="mono" style={{ fontSize: 11.5 }}>{r.entity}</span> → <b>{r.action}</b>
                  </span>
                ))}
              </div>
            ) : (
              <Empty>No PLN recommendations this turn.</Empty>
            )}
          </Card>
          <div className="section">
            <h2>Moves — click a row for its derivation</h2>
            <div className="note">✓ = PLN-recommended actor · ✗ = rejected pre-submit · LLM-only = no PLN derivation.</div>
            <MovesTable turn={mt} traces={g?.traces ?? {}} slotLabels={slotLabels} />
          </div>
        </>
      ) : (
        !detail.loading && <Empty>Select a run with recorded moves.</Empty>
      )}
    </Page>
  );
}
