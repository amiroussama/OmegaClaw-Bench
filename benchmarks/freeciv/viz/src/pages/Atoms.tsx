import { useState } from "react";
import { useCatalog, useRunDetail } from "../lib/data";
import { currentRun } from "../components/RunPicker";
import RunPicker from "../components/RunPicker";
import TurnSlider from "../components/TurnSlider";
import LintBanner from "../components/LintBanner";
import AtomList from "../components/AtomList";
import AtomGraph from "../components/AtomGraph";
import { Page, Card, Loading, ErrorNote, Empty, Tile } from "../design/components";
import { useSelection } from "../lib/nav";
import type { Snapshot } from "../lib/schema";

export default function Atoms() {
  const { data: cat, error, loading } = useCatalog();
  const { runId, game, turn, set } = useSelection();
  const run = cat ? currentRun(cat, runId, "atoms") : null;
  const detail = useRunDetail(run?.detail);
  const [filter, setFilter] = useState("");

  if (loading) return <Page title="AtomSpace"><Loading what="catalog" /></Page>;
  if (error) return <Page title="AtomSpace"><ErrorNote error={error} /></Page>;
  if (!cat) return null;

  // Fall back to the committed sample when no run carries atoms.
  const hasAtomRuns = cat.runs.some((r) => r.has_atoms);
  if (!hasAtomRuns) {
    return (
      <Page title="AtomSpace inspector" sub="No run carries a snapshot — showing the committed turn-1 sample.">
        {cat.sample_atomspace ? <SnapshotView snap={cat.sample_atomspace} filter={filter} setFilter={setFilter} /> : <Empty>No sample atomspace available.</Empty>}
      </Page>
    );
  }

  const g = detail.data?.games?.[game];
  const timeline = g?.atom_timeline ?? {};
  const turns = Object.keys(timeline).map((t) => parseInt(t, 10)).sort((a, b) => a - b);
  const curTurn = turn && turns.includes(turn) ? turn : turns[turns.length - 1] ?? null;
  const snap: Snapshot | null | undefined =
    (curTurn != null ? timeline[String(curTurn)] : null) ?? g?.atomspace ?? cat.sample_atomspace;

  return (
    <Page title="AtomSpace inspector" sub="The PLN player's atoms — observed facts, rules, and derived recommendations — per turn.">
      <RunPicker catalog={cat} filter="atoms" gameCount={detail.data?.games?.length} />
      {detail.loading && <Loading what="run" />}
      {detail.error && <ErrorNote error={detail.error} />}
      {!snap ? (
        <Empty>No atomspace snapshot for this selection.</Empty>
      ) : (
        <>
          <div className="controls">
            {turns.length > 0 && (
              <TurnSlider turns={turns} value={curTurn ?? turns[turns.length - 1]} onChange={(t) => set({ turn: t })} />
            )}
            <label className="ctl">
              Filter atoms
              <input type="search" placeholder="substring…" value={filter} onChange={(e) => setFilter(e.target.value)} />
            </label>
          </div>
          <SnapshotView snap={snap} filter={filter} setFilter={setFilter} noControls />
        </>
      )}
    </Page>
  );
}

function SnapshotView({ snap, filter, setFilter, noControls }: { snap: Snapshot; filter: string; setFilter: (s: string) => void; noControls?: boolean }) {
  const counts = snap.counts ?? {};
  const src = snap.engine?.recommendation_source;
  return (
    <>
      {!noControls && (
        <div className="controls">
          <label className="ctl">
            Filter atoms
            <input type="search" placeholder="substring…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </label>
        </div>
      )}
      <LintBanner ok={snap.lint?.ok ?? true} findings={snap.lint?.findings ?? []} />
      <div className="tiles" style={{ marginBottom: 14 }}>
        {Object.entries(counts).map(([k, v]) => <Tile key={k} k={k} v={v} />)}
        {src && <Tile k="recommendation source" v={src} sub={src === "derive" ? "in-container engine" : "host rule-match"} />}
      </div>
      <div className="section">
        <Card title="Derivation graph" note="Observed facts → rules → derived recommendations.">
          <AtomGraph snap={snap} />
        </Card>
      </div>
      <div className="section">
        <h2>Atoms by provenance</h2>
        <AtomList snap={snap} filter={filter} />
      </div>
    </>
  );
}
