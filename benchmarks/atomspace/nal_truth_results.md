# T0.1 — NAL/PLN truth-value cross-backend conformance

Corpus: **236 golden truth cases** (176 NAL / 60 PLN; 222 stv, 12 scalar, 2 expected-empty) + **4 rule-level pair cases**, epsilon **1e-06**.
Golden reference: `atomspace_agent.truth` (pure-Python mirror of the vendored lib_nal.metta / lib_pln.metta). Every available MeTTa backend must reproduce it exactly;
the pure backend runs rule cases only (its arithmetic IS the reference).

| Backend | Status | Truth cases pass | Rule cases pass | max abs Δ | s |
| --- | --- | --- | --- | --- | --- |
| hyperon | RUN | 236/236 | 4/4 | 3.08e-11 | 1.17 |
| petta | SKIPPED | — | — | — | — |
| pure | RUN | n/a (golden ref) | 3/3 (+1 skipped arrow-form) | 3.08e-11 | — |

Pre-registered gate: 100% truth-value parity at eps 1e-6 on every available MeTTa backend; >=1 MeTTa backend required; unavailable backends reported as SKIPPED.

**GATE: PASSED**

Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/nal_truth_benchmark.py` (HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python)
