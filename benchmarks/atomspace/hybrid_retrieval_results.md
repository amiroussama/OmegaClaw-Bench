# T1.1 — hybrid_retrieval (recall + 1-hop inference vs lexical recall)

80 queries (`random.Random(2202)`), same per-query store to both arms; candidate = `hybrid_recall` (min_confidence=0.2), baseline = `lexical_recall`. McNemar success = the inference-only `key_gold` in top-5.

| Metric | Baseline | Candidate | Gate |
| --- | --- | --- | --- |
| precision@5 | 0.4 | 0.5625 (delta **+0.1625**) | >= baseline + 0.15 |
| recall@10 | 0.7292 | 1.0 | >= baseline |
| McNemar (b=65, c=0) | — | p = 4.87e-13 | < 0.05 |
| injected tokens (median) | 61.0 | 67.0 (x1.098) | <= 1.5x |

**GATE: PASSED**

Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/hybrid_retrieval_benchmark.py`
