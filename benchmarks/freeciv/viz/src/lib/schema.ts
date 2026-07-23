// Types for the JSON the Python generators emit. Kept permissive (optional fields)
// so the app degrades gracefully across the several on-disk run layouts.

export type Stv = { f: number; c: number } | null;

// ---- AtomSpace snapshot (atomspace_export.py) ----
export interface Atom {
  id: string;
  kind: "fact" | "rule" | "inferred";
  type: string; // link constructor: Inheritance | Evaluation | Implication | Recommend
  statement: string;
  sentence?: string;
  stv: { f: number; c: number } | null;
  category: string;
  provenance: string; // observed | derived-heuristic | rule | inferred-pln | unknown
  origin?: string;
  subj?: string;
  pred?: string;
  obj?: string;
  action?: string;
  form?: string;
  fires_on_host_engine?: boolean;
  is_game_law?: boolean;
  premises?: string[];
  trace_id?: string | null;
}
export interface LintFinding {
  check: string;
  severity: "error" | "warn" | "info";
  message: string;
  atom_ids: string[];
}
export interface Snapshot {
  schema_version: number;
  generated_from?: { state_file?: string | null; state_hash?: string; turn?: number; player_perspective?: number };
  engine?: { recommendation_source?: string };
  atoms: Atom[];
  groups: Record<string, string[]>;
  counts: Record<string, number>;
  lint: { ok: boolean; findings: LintFinding[] };
}

// ---- PLN reasoning trace (pln_trace.py) ----
export interface TraceDerived { atom: string; stv: { strength: number; confidence: number } | null; new: boolean }
export interface TraceHop { hop: number; n_premises: number; n_new: number; derived: TraceDerived[] }
export interface TraceConclusion {
  atom: string;
  stv: { strength: number; confidence: number } | null;
  rule_id?: string;
  premises?: string[];
}
export interface Trace {
  schema: string;
  trace_id: string;
  query?: string;
  engine?: { cmd?: string; available?: boolean; latency_ms?: number };
  context?: Record<string, unknown>;
  inputs?: { facts?: string[] };
  hops: TraceHop[];
  conclusions: TraceConclusion[];
  recommendations: string[];
  status: string; // ok | no_conclusions | interpreter_unavailable | error | pending
  error?: string | null;
  latency_ms?: number | null;
  llm_explanation?: string; // optional NL prose, kept separate from the formal trace
}

// ---- Per-turn moves ----
export interface Move {
  actor: number | string;
  actor_kind?: string;
  action_type: string;
  target?: { x?: number; y?: number; production_type?: string } | null;
  valid: boolean;
  error_code?: string | null;
  error_message?: string | null;
  pln_recommended?: boolean;
  trace_id?: string | null;
}
export interface MoveTurn {
  turn: number;
  pln: Move[];
  plain: Move[];
  recommendations: { entity: string; action: string }[];
}

// ---- Trajectory / stats ----
export interface TrajPoint {
  turn: number;
  n_cities?: number | null;
  n_units?: number | null;
  n_techs?: number | null;
  proposed?: number | null;
  submitted?: number | null;
  blocked?: number | null;
  n_conclusions?: number | null;
  reason_ms?: number | null;
  llm_ms?: number | null;
}
export type Stats = Record<string, unknown> & {
  final?: { n_cities?: number; n_units?: number; n_techs?: number; score?: number };
  illegal_rate?: number;
  avg_llm_ms?: number | null;
  avg_reason_ms?: number | null;
};

export interface Game {
  subdir?: string | null;
  pln_side?: number | null;
  arms?: string[];
  contrast?: string[];
  trajectory: { pln: TrajPoint[]; plain: TrajPoint[] };
  trajectory_all?: Record<string, TrajPoint[]>;
  series_all?: Record<string, TrajPoint[]>;
  stats: { pln: Stats | null; plain: Stats | null };
  stats_all?: Record<string, Stats | null>;
  winner?: string | null;
  moves: MoveTurn[];
  moves_logged?: boolean;
  traces?: Record<string, Trace>;
  atomspace?: Snapshot | null;
  atom_timeline?: Record<string, Snapshot>; // turn -> snapshot (NEW)
}

// ---- Catalog + detail ----
export interface RunCatalogEntry {
  id: string;
  safe_id: string;
  type: "ab" | "duel";
  source: string;
  arms?: string[];
  contrast?: string[];
  verdict: string;
  has_moves: boolean;
  has_atoms: boolean;
  detail: string; // relative path under data/, e.g. "runs/<safe_id>.json"
  overall?: string | null;
  batch?: string | null;
  seed?: string | null;
}
export interface RunDetail {
  id: string;
  type: "ab" | "duel";
  source: string;
  arms?: string[];
  contrast?: string[];
  verdict: string;
  overall?: string | null;
  games: Game[];
}

// ---- Batch aggregate (batch/aggregate.py) ----
export interface PairedT { n: number; mean: number | null; sd?: number | null; t?: number | null; p_approx?: number | null }
export interface ContrastSummary {
  label: string;
  a: string;
  b: string;
  n_games: number;
  wins: Record<string, number>;
  sign_test_p: number | null;
  deltas_pln_minus_plain: Record<string, PairedT>;
  era_delta_turns_to_tech?: Record<string, PairedT>;
  pln_quality?: { n: number; mean_pln_action_success_rate?: number | null; mean_rec_adoption_rate?: number | null };
}
export interface Aggregate {
  batch: string;
  seeds_scanned: number;
  duel?: ContrastSummary;
  ab: Record<string, ContrastSummary>;
  per_seed: Array<Record<string, string>>;
}
export interface BatchEntry {
  id: string;
  safe_id: string;
  aggregate: Aggregate;
}

export interface Fixture {
  id: string;
  label: string;
  summary?: Record<string, unknown>;
  rows?: Array<Record<string, unknown>>;
}

export interface Catalog {
  generated: string;
  runs: RunCatalogEntry[];
  batches: BatchEntry[];
  fixtures: Fixture[];
  sample_atomspace?: Snapshot | null;
}
