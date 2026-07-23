# FreeCiv PLN benchmark dashboard

A multi-page React (Vite + TypeScript) dashboard to explore the benchmark: see the AtomSpace,
inspect PLN reasoning/derivation traces, and read A/B and batch results. The Python generators
turn the on-disk run artifacts into JSON; the app is a pure consumer (works on saved artifacts —
no live game needed).

## Quick start

```bash
bash benchmarks/freeciv/viz/serve.sh          # dev server + live reload at http://localhost:8009
bash benchmarks/freeciv/viz/serve.sh prod     # build, then serve static dist/ with http.server
```

First run installs npm deps. `serve.sh` regenerates the data (`build_index.py` + `dump_atoms.py`
into `public/data/`), then serves. A browser can't `fetch()` over `file://`, so it must be served.

## Pages

- **Overview** — landing: statistical batches (primary-contrast verdict + sign-test p + key
  deltas) and a table of individual runs, each deep-linking into the pages below.
- **AtomSpace** — the PLN player's atoms **per turn** (turn slider over the run's
  `atomspace_turn*.json`): a lint banner, atoms grouped by provenance (observed /
  derived-heuristic / rule / inferred-PLN) with truth values + category, and a
  fact → rule → recommendation graph (green edge = confirmed by the in-container engine).
- **Reasoning** — pick a turn, then click any move for its recorded derivation chain: premises →
  hop-by-hop derived atoms (with truth values, new-atom flags) → conclusions → recommendation.
  LLM prose is rendered in a distinct block, explicitly **not** part of the formal derivation.
  A turn-objective panel summarizes the turn's PLN recommendations.
- **A/B run** — one run, **all arms** (`facts+chaining`, `facts-only`, `plain`,
  `facts+chaining-v2`): territory + activity/reasoning trajectories, per-arm final-state table,
  and links into Reasoning / AtomSpace.
- **Batch** — the statistical view over `aggregate.json`: each contrast (primary
  `facts+chaining-v2` vs `facts+chaining`) with win record + sign-test p, a per-metric mean-Δ plot
  (t / p), a per-seed winner heatmap, and PLN-quality means.

## Data generators (run by `serve.sh`, or standalone)

- `build_index.py` → `public/data/index.json` (light catalog) + `public/data/runs/<id>.json`
  (per-run detail, lazy-loaded) + batch aggregates + the committed sample snapshot. Scans
  `../ab_runs/`, normalizing every layout (A/B `comparison.json`, duel `g{1,2}/duel.jsonl`, old
  committed-only duel, and `batch_<ts>/seed<n>/{ab,duel}`); discovers **all** arm JSONLs (so the
  `facts+chaining-v2` arm shows even though the 3-arm `comparison.json` omits it), loads every
  `atomspace_turn*.json` for the per-turn timeline, and skips legacy (non-contrast-keyed)
  aggregates. Falls back to committed `comparison.json`/`duel_comparison.json` on a fresh checkout.
- `dump_atoms.py` → `public/data/atoms.json` (+ `atomspace_snapshot.json`): offline atom
  reconstruction from a captured state (default `../samples/real_state_turn1.json`).

## Design

Palette + charts follow the repo's `dataviz` skill: a CVD-validated 4-arm categorical palette
(`facts+chaining`=blue, `plain`=orange, `facts-only`=aqua, `facts+chaining-v2`=yellow; validated
both light/dark), one-axis line charts with crosshair+tooltip+legend+direct labels, and tables
alongside every chart (relief rule). Theme toggle persists in `localStorage`.

`node_modules/`, `dist/`, and `public/data/` are **gitignored** — regenerated from run artifacts.
The committed record stays the compact `comparison.json` / `aggregate.json` summaries.

## Truth values

AtomSpace snapshots use `(stv f c)`; PLN traces use `{strength, confidence}`. `src/lib/stv.ts`
normalizes both to one shape for display.
