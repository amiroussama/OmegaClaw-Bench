import { useEffect, useMemo, useState } from "react";

type Arm = "pln" | "plain";
type Metrics = Record<string, number | null | undefined>;
type SideStats = {
  final?: Metrics;
  peak?: Metrics;
  turns?: number;
  plateau_turn?: number;
  avg_proposed?: number;
  avg_conclusions?: number;
  pct_actions_eq_recs?: number;
  illegal_rate?: number;
  avg_llm_ms?: number | null;
  avg_reason_ms?: number | null;
};
type Game = {
  subdir?: string | null;
  trajectory?: Record<string, Array<Record<string, number | null | undefined>>>;
  stats?: Partial<Record<Arm, SideStats>> & Record<string, SideStats | undefined>;
  stats_all?: Record<string, SideStats | undefined>;
  arms?: string[];
  contrast?: string[];
  moves?: Array<Record<string, unknown>>;
  traces?: Record<string, unknown>;
  atomspace?: { counts?: Record<string, number>; lint?: { ok?: boolean; findings?: unknown[] } } | null;
  winner?: string;
  moves_logged?: boolean;
};
type Run = {
  id: string;
  type: string;
  source: string;
  games: Game[];
  verdict?: string;
  has_moves?: boolean;
  pln_wins?: number;
  plain_wins?: number;
  arms?: string[];
  contrast?: string[];
};
type IndexData = { generated?: string; runs: Run[]; fixtures?: Record<string, unknown> };
type AtomGraph = {
  state_file?: string;
  turn?: number;
  source?: string;
  facts?: Array<{ subj?: string; pred?: string; obj?: string; category?: string; stv?: string; statement?: string }>;
  rules?: Array<{ action?: string; rule_class?: string; rationale?: string; sentence?: string }>;
  recommendations?: Array<{ subject?: string; action?: string; confidence?: number; rule?: string; statement?: string }>;
};

type View = "overview" | "runs" | "atomspace" | "moves" | "fixtures";

type LoadState = { index: IndexData | null; atoms: AtomGraph | null; error?: string };

const fmt = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
};

const readMetric = (stats: SideStats | undefined, group: "final" | "peak", metric: string) =>
  stats?.[group]?.[metric];

const armStats = (game: Game, arm: Arm): SideStats | undefined =>
  game.stats?.[arm] ?? game.stats_all?.[arm];

const collectRuns = (index: IndexData | null): Run[] => index?.runs ?? [];

function useVizData(): LoadState {
  const [state, setState] = useState<LoadState>({ index: null, atoms: null });
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch("data/index.json").then((r) => r.ok ? r.json() : Promise.reject(new Error(`${r.status} ${r.statusText}`))),
      fetch("data/atoms.json").then((r) => r.ok ? r.json() : null).catch(() => null),
    ]).then(([index, atoms]) => {
      if (!cancelled) setState({ index, atoms });
    }).catch((error: Error) => {
      if (!cancelled) setState({ index: null, atoms: null, error: error.message });
    });
    return () => { cancelled = true; };
  }, []);
  return state;
}

function Header({ index, run }: { index: IndexData | null; run?: Run }) {
  return <header className="topbar">
    <div className="brand-mark" aria-hidden="true"><span>Ω</span></div>
    <div>
      <div className="eyebrow">FreeCiv / benchmark observability</div>
      <h1>OmegaClaw Decision Observatory</h1>
    </div>
    <div className="run-identity">
      <span className="live-dot streaming" /> replay · static artifacts
      <strong>{run?.id ?? "loading benchmark index"}</strong>
    </div>
    <div className="top-stat"><span>runs</span><strong>{collectRuns(index).length.toLocaleString()}</strong></div>
    <div className="top-stat"><span>generated</span><strong>{index?.generated ?? "—"}</strong></div>
  </header>;
}

function Tile({ label, value, tone }: { label: string; value: unknown; tone?: "pln" | "plain" | "good" | "bad" }) {
  return <div className={`metric-tile ${tone ?? ""}`}>
    <span>{label}</span>
    <strong>{fmt(value)}</strong>
  </div>;
}

function StatDuel({ game }: { game?: Game }) {
  const pln = game ? armStats(game, "pln") : undefined;
  const plain = game ? armStats(game, "plain") : undefined;
  return <div className="stat-duel">
    {(["n_cities", "n_units", "n_techs"] as const).map((metric) => <div className="duel-row" key={metric}>
      <span>{metric.replace("n_", "")}</span>
      <strong className="pln">{fmt(readMetric(pln, "final", metric))}</strong>
      <em>vs</em>
      <strong className="plain">{fmt(readMetric(plain, "final", metric))}</strong>
    </div>)}
  </div>;
}

function Overview({ index, run, game }: { index: IndexData; run: Run; game?: Game }) {
  const pln = game ? armStats(game, "pln") : undefined;
  const plain = game ? armStats(game, "plain") : undefined;
  const plnWins = index.runs.filter((r) => r.verdict?.toLowerCase().includes("pln") || r.pln_wins).length;
  const moveRuns = index.runs.filter((r) => r.has_moves).length;
  return <div className="view-content">
    <div className="view-heading">
      <div><span className="eyebrow">current replay artifact</span><h2>{run.id}</h2></div>
      <p>{run.verdict ?? "No verdict recorded"}. Source: <code>{run.source}</code>; type: <code>{run.type}</code>.</p>
    </div>
    <div className="observatory-grid">
      <Tile label="indexed runs" value={index.runs.length} tone="good" />
      <Tile label="runs with move logs" value={moveRuns} />
      <Tile label="PLN-favorable runs" value={plnWins} tone="pln" />
      <Tile label="selected games" value={run.games.length} />
    </div>
    <section className="panel-grid two">
      <article className="obs-panel">
        <div className="eyebrow">final board state</div>
        <h3>OmegaClaw+PLN vs plain LLM</h3>
        <StatDuel game={game} />
      </article>
      <article className="obs-panel">
        <div className="eyebrow">reasoning controls</div>
        <h3>Activity KPIs</h3>
        <div className="observatory-grid compact">
          <Tile label="PLN avg proposed" value={pln?.avg_proposed} tone="pln" />
          <Tile label="PLN avg conclusions" value={pln?.avg_conclusions} tone="pln" />
          <Tile label="PLN actions = recs" value={pln?.pct_actions_eq_recs == null ? undefined : `${pln.pct_actions_eq_recs}%`} tone="pln" />
          <Tile label="plain avg proposed" value={plain?.avg_proposed} tone="plain" />
        </div>
      </article>
    </section>
  </div>;
}

function RunsView({ runs, selectedRun, onSelect }: { runs: Run[]; selectedRun: string; onSelect: (id: string) => void }) {
  return <div className="view-content">
    <div className="view-heading">
      <div><span className="eyebrow">artifact catalog</span><h2>Benchmark runs</h2></div>
      <p>Imported from <code>build_index.py</code>; select a run to update the observatory.</p>
    </div>
    <div className="artifact-list embedded">
      {runs.map((run) => <button key={run.id} className={run.id === selectedRun ? "loading" : ""} onClick={() => onSelect(run.id)}>
        <span className="artifact-kind">{run.type}</span>
        <span className="artifact-name"><strong>{run.id}</strong><small>{run.verdict ?? "No verdict"}</small></span>
        <span className="artifact-meta"><strong>{run.games.length} game(s)</strong><small>{run.source}</small></span>
        <span className="artifact-action">{run.has_moves ? "moves" : "summary"}</span>
      </button>)}
    </div>
  </div>;
}

function AtomspaceView({ atoms, game }: { atoms: AtomGraph | null; game?: Game }) {
  const counts = game?.atomspace?.counts;
  const lintOk = game?.atomspace?.lint?.ok;
  return <div className="view-content">
    <div className="view-heading">
      <div><span className="eyebrow">Atomspace inspector</span><h2>Facts → rules → recommendations</h2></div>
      <p>Uses the generated <code>atoms.json</code> snapshot and any per-run atomspace counts shipped by the selected artifact.</p>
    </div>
    <div className="observatory-grid">
      <Tile label="facts" value={atoms?.facts?.length} />
      <Tile label="rules" value={atoms?.rules?.length} />
      <Tile label="recommendations" value={atoms?.recommendations?.length} tone="pln" />
      <Tile label="run lint" value={lintOk == null ? "not shipped" : (lintOk ? "OK" : "issues")} tone={lintOk ? "good" : undefined} />
    </div>
    {counts && <pre className="json-card">{JSON.stringify(counts, null, 2)}</pre>}
    <section className="panel-grid two">
      <article className="obs-panel"><div className="eyebrow">facts</div>
        {(atoms?.facts ?? []).slice(0, 12).map((fact, i) => <p className="atom-line" key={`${fact.statement}-${i}`}><b>{fact.category ?? "fact"}</b> {fact.statement ?? `${fact.subj} ${fact.pred} ${fact.obj}`} <small>{fact.stv}</small></p>)}
      </article>
      <article className="obs-panel"><div className="eyebrow">recommendations</div>
        {(atoms?.recommendations ?? []).map((rec, i) => <p className="atom-line" key={i}><b>{rec.action ?? "recommend"}</b> {rec.statement ?? rec.subject} <small>{fmt(rec.confidence)}</small></p>)}
      </article>
    </section>
  </div>;
}

function MovesView({ run, game }: { run: Run; game?: Game }) {
  const moves = game?.moves ?? [];
  return <div className="view-content">
    <div className="view-heading">
      <div><span className="eyebrow">action ancestry</span><h2>Per-unit moves</h2></div>
      <p>{run.has_moves ? "Move traces are available for this run." : "This selected run is committed-summary only; regenerate raw duel/AB artifacts to populate per-unit moves."}</p>
    </div>
    {moves.length === 0 ? <div className="logging-gap"><strong>No per-unit move log for {run.id}</strong><span>Existing committed artifacts still show aggregate KPIs and Atomspace context.</span></div> :
      <div className="proof-grid">{moves.slice(0, 120).map((move, i) => <pre className="json-card" key={i}>{JSON.stringify(move, null, 2)}</pre>)}</div>}
  </div>;
}

function FixturesView({ index }: { index: IndexData }) {
  const fixtures = index.fixtures ?? {};
  return <div className="view-content">
    <div className="view-heading">
      <div><span className="eyebrow">KPI micro-benchmarks</span><h2>Static fixture results</h2></div>
      <p>Compact view of benchmark fixture payloads folded into <code>data/index.json</code>.</p>
    </div>
    <pre className="json-card large">{JSON.stringify(fixtures, null, 2)}</pre>
  </div>;
}

const VIEWS: Array<{ id: View; label: string; key: string }> = [
  { id: "overview", label: "Decision overview", key: "01" },
  { id: "runs", label: "Run catalog", key: "02" },
  { id: "atomspace", label: "Atomspace", key: "03" },
  { id: "moves", label: "Action traces", key: "04" },
  { id: "fixtures", label: "KPI fixtures", key: "05" },
];

export function App() {
  const { index, atoms, error } = useVizData();
  const runs = useMemo(() => collectRuns(index), [index]);
  const [view, setView] = useState<View>("overview");
  const [runId, setRunId] = useState("");
  const [gameIndex, setGameIndex] = useState(0);
  const selectedRun = runs.find((run) => run.id === runId) ?? runs[0];
  const selectedGame = selectedRun?.games[Math.min(gameIndex, Math.max(0, selectedRun.games.length - 1))];

  useEffect(() => {
    if (!runId && runs[0]) setRunId(runs[0].id);
  }, [runId, runs]);
  useEffect(() => { setGameIndex(0); }, [selectedRun?.id]);

  if (error) return <div className="app-shell"><Header index={null} /><main className="view-content"><div className="logging-gap"><strong>Could not load visualization data</strong><span>{error}. Run <code>python3 benchmarks/freeciv/viz/build_index.py</code> first.</span></div></main></div>;
  if (!index || !selectedRun) return <div className="app-shell"><Header index={index} /><main className="view-content"><div className="artifact-state">Loading FreeCiv benchmark artifacts…</div></main></div>;

  return <div className="app-shell">
    <Header index={index} run={selectedRun} />
    <section className="scrubber observatory-controls">
      <label className="scrubber-label"><span>run</span><select aria-label="Run" value={selectedRun.id} onChange={(event) => setRunId(event.target.value)}>{runs.map((run) => <option key={run.id} value={run.id}>{run.id}</option>)}</select></label>
      <div className="trace-source"><span>verdict</span><strong>{selectedRun.verdict ?? "No verdict"}</strong></div>
      <label className="cursor-readout"><span>game</span><select aria-label="Game" value={gameIndex} onChange={(event) => setGameIndex(Number(event.target.value))}>{selectedRun.games.map((game, i) => <option key={i} value={i}>{game.subdir ?? `game ${i + 1}`} · {game.winner ?? "no winner"}</option>)}</select></label>
    </section>
    <div className="workspace">
      <nav className="side-nav" aria-label="Observatory views">
        {VIEWS.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}><span>{item.key}</span>{item.label}</button>)}
        <div className="schema-lock"><span>data</span><strong>index.json</strong><small>{index.generated}</small></div>
      </nav>
      <main>
        {view === "overview" && <Overview index={index} run={selectedRun} game={selectedGame} />}
        {view === "runs" && <RunsView runs={runs} selectedRun={selectedRun.id} onSelect={setRunId} />}
        {view === "atomspace" && <AtomspaceView atoms={atoms} game={selectedGame} />}
        {view === "moves" && <MovesView run={selectedRun} game={selectedGame} />}
        {view === "fixtures" && <FixturesView index={index} />}
      </main>
      <aside className="detail-pane">
        <div className="detail-card"><span className="eyebrow">selected run</span><h3>{selectedRun.id}</h3><p>{selectedRun.verdict}</p></div>
        <div className="detail-card"><span className="eyebrow">source frontend</span><p>Visual shell adapted from <code>machieke/freeciv-omegaclaw</code> Decision Observatory.</p></div>
        <div className="detail-card"><span className="eyebrow">current game JSON</span><pre>{JSON.stringify({ subdir: selectedGame?.subdir, winner: selectedGame?.winner, moves_logged: selectedGame?.moves_logged }, null, 2)}</pre></div>
      </aside>
    </div>
  </div>;
}
