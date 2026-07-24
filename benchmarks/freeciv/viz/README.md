# FreeCiv benchmark visualization

A React/Vite adaptation of the **Decision Observatory** frontend from
`machieke/freeciv-omegaclaw`, wired to this repository's FreeCiv benchmark artifacts.

The data contract stays local to OmegaClaw-Bench:

- `build_index.py` → `data/index.json`: run catalog, per-run stats, duel/A-B summaries, optional
  per-unit move traces, and KPI fixture results.
- `dump_atoms.py` → `data/atoms.json` and `data/atomspace_snapshot.json`: representative
  Atomspace facts, rules, recommendations, and lint metadata.

## Quick start

```bash
bash benchmarks/freeciv/viz/serve.sh          # regenerates data, builds UI, serves http://localhost:8009
```

For frontend development:

```bash
cd benchmarks/freeciv/viz
npm install
python3 build_index.py && python3 dump_atoms.py
npm run dev                                  # Vite at http://127.0.0.1:4178
```

## What it shows

- **Decision overview** — selected run verdict, final PLN-vs-plain city/unit/tech stats, and
  activity KPIs.
- **Run catalog** — all benchmark artifacts indexed from `ab_runs/`.
- **Atomspace** — generated facts, rules, recommendations, and per-run snapshot counts when
  shipped with the selected artifact.
- **Action traces** — per-unit moves/traces when raw logs exist; committed-summary-only runs are
  clearly marked rather than reconstructing unsupported traces.
- **KPI fixtures** — static micro-benchmark payloads folded into the visualization data.

## Data caveat

Most committed historical runs contain summary statistics only. They still render in the
observatory, but the Action traces panel only expands when raw `duel.jsonl` / arm JSONL artifacts
with move logs are available.

## Validation

```bash
cd benchmarks/freeciv/viz
npm test
```
