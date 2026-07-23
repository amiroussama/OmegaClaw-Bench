# T1.3 — scope_routing (cwd -> AtomSpace, zero cross-project leakage)

6 repos (distinct remotes, a clone sharing repo-a's remote, a no-remote repo, a non-git dir); 48 cwd probes; 5 distinct scopes cross-queried.

| Metric | Value | Gate |
| --- | --- | --- |
| routing accuracy | 1.0 (48/48) | >= 0.95 |
| cross-scope leakage | 0 / 300 lookups | 0 (hard) |

**GATE: PASSED**

Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/scope_routing_benchmark.py`
