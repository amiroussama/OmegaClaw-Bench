# T1.2 — revision_staleness (NAL revision + supersession vs append-only)

60 knowledge-update cases (`random.Random(2203)`): 30 revision (same canonical re-asserted with better evidence) + 30 supersession (fact retracted and replaced). Candidate = product store; baseline = append-only / no-supersede.

| Metric | Baseline | Candidate | Gate |
| --- | --- | --- | --- |
| current-answer accuracy | 0.1667 | 1.0 (delta **+0.8333**) | >= 0.9 AND >= baseline+0.25 |
| contradiction-leak | 0.8333 | 0.0 | <= 0.05 |

**GATE: PASSED**

Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/revision_staleness_benchmark.py`
