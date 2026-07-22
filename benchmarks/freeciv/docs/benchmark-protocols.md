# FreeCiv benchmark protocols — A/B vs duel, metrics, and dashboard export

This is the single reference for the two benchmark protocols, the metrics they emit, and the
machine-readable files the dashboard consumes (Issue #5).

## 1. The two protocols

### A/B (parallel, each arm vs the built-in AI)
Independent games — one per **arm** — each played against the game AI with the same
model/provider/seed/validation. The **only** difference between arms is the state representation
the LLM sees. The arms (`ab_sim.py:ARMS`):
- `plain` — plain state only (control): no facts, no reasoning.
- `facts-only` — plain + adapter∪LLM facts as premises, but **no** PLN.
- `facts+chaining` — the same facts **plus** v1 PLN-derived recommendations (`rules.metta`).
- `facts+chaining-v2` *(optional)* — reasons over the atomspace-v2 KB+engine (`reason_v2`) instead
  of `rules.metta`; needs the v2 scratch dir.

The **primary contrast is `facts+chaining` vs `facts-only`** — it isolates the marginal value of
PLN chaining while holding the extra fact-proposal call constant (`facts-only` vs `plain` isolates
the value of the facts themselves). When the v2 arm is present, the reporters also contrast
`facts+chaining-v2` vs `facts+chaining`. Scripts: `ab_sim.py`, launcher `ab_run.sh` (default runs
the 3 core arms; add v2 via `ARMS_TO_RUN`). Output: `<arm>.jsonl` → `comparison.{md,json}` via
`ab_report.py`; batched via `batch/aggregate.py`.

### Duel (head-to-head mirror pair)
One 1v1 game with PLN on one side and plain-LLM on the other, played twice as a **mirror pair**
(g1: PLN=slot 0; g2: PLN=slot 1) to cancel start-position bias. PLN winning *both* is a real
signal. Scripts: `duel_sim.py`, launcher `duel_run.sh`. Output: `duel.jsonl` per game →
`duel_comparison.{md,json}` via `duel_report.py`.

### When to use which (Ikle / Machiels recommendation)
- **A/B for rapid, single-variable PLN-rule iteration.** It is cheaper (one game per arm/seed —
  the 3 core arms, no opponent-interaction confound) and its per-turn trajectories are directly
  comparable, so it detects a change faster. Use it while iterating on `rules.metta` / the mapping.
- **Duel to confirm a stable A/B delta.** Head-to-head is the harder, adversarial test; run it
  (batched, with the sign test) once A/B suggests PLN helps, to check the effect survives direct
  competition.

### Selecting a mode
```
python3 benchmarks/freeciv/bench_run.py --mode ab   --arm pln --game-id g --out DIR [...]
python3 benchmarks/freeciv/bench_run.py --mode duel --game-id g --pln-side 0 --out DIR [...]
```
`bench_run.py` forwards all other flags to the chosen sim unchanged. In the batch harness, the
`MODES` env selects protocols per seed (default `"duel ab"`; set `"ab"` or `"duel"` to run one).

## 2. Metric definitions (single source of truth)

### Per-turn record (jsonl)
Each turn logs `metrics` = `{turn, score, gold, science, n_cities, n_units, n_techs, tech_names}`
plus `proposed` / `submitted` / `blocked` action counts, `illegal_rate`, `n_conclusions`
(PLN recommendations that turn), `moves[]` (per-move: actor, actor_kind, action_type, target,
valid, pln_recommended), and `recommendations[]` (`{entity, action}`).

> gold/score are read from the per-player block (`players[pid]`) first — the runtime state puts
> the real values there while `economic.gold`/`strategic.score` are often 0.

### Era progression
FreeCiv has no Civ-style eras and the proxy state carries no era field, so era progression is
measured as **tech-milestone progression** (`metrics.era_progression`):
- `turns_to_tech_count[N]` — first turn `n_techs ≥ N`, for N ∈ {2,4,6,8}. `null` = never reached
  (censored — never coerced to 0). **Primary** era metric.
- `turns_to_milestone[T]` — first turn a named milestone tech (Bronze Working, Currency, Writing,
  Monarchy) appears in `tech_names`. Secondary/best-effort (depends on the proxy exposing names).
- `tech_rate` — final `n_techs` ÷ final turn.

### Action metrics
`proposed` / `submitted` / `blocked`, `illegal_rate` (blocked ÷ proposed), and
`avg_actions_per_turn` (proposed ÷ turns).

### PLN recommendation quality (`metrics.pln_quality`)
- `pln_action_success_rate` — valid PLN-recommended moves ÷ all PLN-recommended moves (did acting
  on a recommendation produce a legal action?). `null` if none.
- `rec_adoption_rate` — per turn with ≥1 recommendation, the fraction of recommendations whose
  entity was the actor of ≥1 proposed move, averaged over those turns.

### Win/loss
Territory winner: cities > units > techs (`run_summary.territory_winner`). Batches add an exact
two-sided **sign test** over decisive games and per-metric paired-t deltas (`batch/aggregate.py`).

### Known limits
- `science` is proxy-limited: the runtime state carries no per-player science field, so it is
  often 0 (documented, not a bug in the adapter).
- Milestone-tech names are best-effort — the upstream tech-id→name mapping can be noisy (e.g.
  "Advanced Flight" appearing at turn 1), which is why `turns_to_tech_count` is the primary metric.

## 3. Machine-readable exports (dashboard contract)

### `comparison.json` (A/B) — fields added by Issue #5
```
stats.<arm>.era.turns_to_tech_count.{2,4,6,8}   int|null
stats.<arm>.era.turns_to_milestone.<tech>       int|null
stats.<arm>.era.tech_rate                       float|null
stats.<arm>.avg_actions_per_turn                float|null
stats.<arm>.turns_to_tech_4                     int|null
stats.pln.pln_action_success_rate               float|null
stats.pln.rec_adoption_rate                     float|null
verdict.turns_to_tech_4                          "pln"|"plain"|"tie"
```

### `duel_comparison.json` — per-game `pln`/`plain` payloads gain
`era` (same shape), `pln_action_success_rate`, `rec_adoption_rate` (from `run_summary.summarize_side`).

### `aggregate.json` (batch) — per experiment (`duel`, `ab`)
`era_delta_turns_to_tech.{4,6}` (paired plain−pln Δ, positive favors PLN, censored pairs skipped
with `n` = decisive pairs) and `pln_quality.{mean_pln_action_success_rate, mean_rec_adoption_rate}`.

## 4. Reproduce
```
# one A/B pair
python3 benchmarks/freeciv/bench_run.py --mode ab --arm pln   --game-id demo --out /tmp/ab
python3 benchmarks/freeciv/bench_run.py --mode ab --arm plain --game-id demo --out /tmp/ab
python3 benchmarks/freeciv/ab_report.py /tmp/ab --final       # writes comparison.{md,json}

# a batch aggregate (after batch/batch.sh)
python3 benchmarks/freeciv/batch/aggregate.py <batch_dir>     # writes aggregate.{md,json}
```
