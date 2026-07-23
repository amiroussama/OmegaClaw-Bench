# T2.1 — multihop_impact (primary program gate)

80 pre-registered decision cases (`random.Random(2101)`); both arms get the same premises + same rule text, in-process inference (min_confidence=0.2, max_hops=3). Mode: **code_rules loaded**.

| Family | N | baseline correct | PLN correct |
| --- | --- | --- | --- |
| direct | 25 | 25/25 | 25/25 |
| impact-chain | 25 | 0/25 | 25/25 |
| invariant | 15 | 0/15 | 15/15 |
| negative | 15 | 15/15 | 15/15 |

| Metric | Value | Gate |
| --- | --- | --- |
| exact-match (PLN vs baseline) | 1.0 vs 0.5 (delta **+0.5**) | >= baseline + 0.25 |
| net decision-flips-to-correct | **+40** (40 to-correct, 0 to-wrong) | >= +20/80 |
| exact two-sided sign test | p = 1.82e-12 | < 0.05 |
| median inference latency | 87.2 ms (mean 137.1, max 354.3) | < 2000 ms |

**GATE: PASSED**

Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/multihop_impact_benchmark.py` (HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python)
