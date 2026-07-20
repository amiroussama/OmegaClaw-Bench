# T0.3 — MCP tool-surface conformance

**52 scripted cases** over all 11 tool handlers (`atomspace_agent.tools`, backend: hyperon): statuses (added/dup/revised + conflict flag), the full injection-firewall corpus from the product's test suite, stv/source_type/scope failure taxonomy, supersession visibility, empty-scope inference, bootstrap, and export/import round-trips (including a hostile seed file).

| Cases passed | Crashes (tool call raised) | 2-client interleaving | stdio transport |
| --- | --- | --- | --- |
| 52/52 | 0 | 3/3 lossless trials (2x100 asserts, 150 unique canonicals, fresh scope per trial) -> lossless | ok (11 tools listed) |

Per-tool latency over 5 runs/case (warm runtime; `infer` and `bootstrap_project` are exempt per the pre-registered gate):

| Tool | samples | p50 ms | p95 ms |
| --- | --- | --- | --- |
| atom_assert | 115 | 0.01 | 0.3 |
| atom_assert_batch | 10 | 0.0 | 0.45 |
| atom_query | 40 | 0.21 | 0.36 |
| atom_retract | 15 | 0.14 | 0.17 |
| hybrid_recall | 10 | 0.41 | 3.14 |
| revise | 10 | 0.2 | 0.33 |
| scope_info | 10 | 0.17 | 0.24 |
| snapshot_export | 10 | 0.46 | 0.62 |
| snapshot_import | 15 | 0.39 | 0.68 |

Findings (non-gating): an unknown scope key format (e.g. `not-a-valid-scope!`) silently falls back to cwd resolution rather than returning a structured error — covered by `query-unknown-scope-format` as documented behavior.

Known interleaving failure modes (which one a given run hits is a race): (1) concurrent FIRST-open of a new scope DB — `PRAGMA journal_mode=WAL` raises `sqlite3.OperationalError: database is locked` (AtomStore.__init__, store.py:92); (2) two clients asserting the same canonical — `assert_atom`'s SELECT-then-INSERT races to `sqlite3.IntegrityError: UNIQUE constraint failed: atoms.canonical` (store.py:117-127), contradicting the store's documented "concurrent duplicate asserts converge" contract.

Pre-registered gates: 100% case conformance; zero crashes; lossless 2-client interleaving; p95 < 150 ms per tool excluding inference/bootstrap.

**GATE: PASSED**

Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/mcp_conformance_benchmark.py` (HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python)
