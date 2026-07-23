# T0.2 — AtomStore persistence, scoping, hydration

Deterministic corpus (`random.Random(1001)`, all 5 heads, all 5 source_types, ~5% supersession-marked). Baseline for section f = a **stateless** engine that re-sends all n premises on each of 50 inference calls; candidate = the persisted store (each atom written once, reads via `by_terms` neighborhoods).

| Corpus | write | hydrate (active_atoms + parse) | baseline atoms sent | candidate atoms sent | reduction |
| --- | --- | --- | --- | --- | --- |
| 1,000 | 27 ms | 4.7 ms < 500 ms | 50,000 | 3,355 | **93.3%** |
| 10,000 | 305 ms | 45.0 ms < 3000 ms | 500,000 | 22,800 | **95.4%** |

| Section | Result | Gate |
| --- | --- | --- |
| a. round-trip fidelity (export_metta -> fresh import, n=1000) | 1000/1000 identical stv (100.0%), 0 rejected | 100% |
| b. scope isolation (2 projects + global, 1320 cross-scope lookups) | 0 leaks | 0 |
| c. supersession (67 marked) | 67/67 excluded by default; 67/67 visible with include_superseded | 100% / 100% |
| d. crash recovery (child os._exit(1) after 250 asserts) | integrity_check=ok, rows=250, reopen+assert=added | clean |

Pre-registered gates: fidelity 100%; cross-scope leakage 0; supersession-exclusion 100%; crash recovery clean; hydrate 1k<500ms / 10k<3s; re-transmission reduction >=90% vs the stateless baseline.

**GATE: PASSED**

Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/atomstore_benchmark.py` (HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python; add `--large` for the 50k size)
