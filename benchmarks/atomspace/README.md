# atomspace-agent T0 benchmarks

The correctness floor for the `atomspace_agent` product
(`/home/rojo-dev/Repos/Hyperon-MCP`): truth arithmetic, persistence/scoping,
and the MCP tool contract. Gates are pre-registered in
[`benchmark-docs/atomspace.md`](../../benchmark-docs/atomspace.md) — read that
first for the full roadmap (T0–T3) and the FreeCiv §3f rationale.

## Run

These benchmarks test the product package, **not** OmegaClaw core — they must
run under the Hyperon-MCP venv python (hyperon 0.2.10 + mcp installed):

```bash
HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python

$HYPERON_MCP_PY benchmarks/atomspace/nal_truth_benchmark.py
$HYPERON_MCP_PY benchmarks/atomspace/atomstore_benchmark.py        # --large adds 50k
$HYPERON_MCP_PY benchmarks/atomspace/mcp_conformance_benchmark.py
```

Each script locates the product by `import atomspace_agent`, falling back to
`$ATOMSPACE_AGENT_SRC` (default `/home/rojo-dev/Repos/Hyperon-MCP/src`). Each
writes `<name>_results.{json,md}` next to itself, prints PASS/FAIL per gate,
and exits non-zero on any gate failure. All state lives in tempdirs via
`ATOMSPACE_AGENT_HOME` — nothing touches `~/.atomspace-agent`.

## What each gates

| Benchmark | Fixtures | Pre-registered gate |
| --- | --- | --- |
| `nal_truth_benchmark.py` (T0.1) | `nal_truth_fixtures.py` — wraps the product's golden corpus (`atomspace_agent.conformance`: 236 truth cases + 4 rule cases) so Bench records its size/categories | 100% truth-value parity at eps 1e-6 on every available MeTTa backend (hyperon, petta); >=1 MeTTa backend required; unavailable backends reported SKIPPED. Pure backend runs rule cases only (its arithmetic IS the golden reference). |
| `atomstore_benchmark.py` (T0.2) | `atomstore_fixtures.py` — seeded (`random.Random(1001)`) generator, 1k/10k (50k via `--large`), all 5 heads + 5 source_types, ~5% supersession-marked | Round-trip fidelity 100% (export_metta -> fresh import, identical stv); cross-scope leakage 0 (hard); supersession-exclusion 100% (and 100% visible with `include_superseded`); crash recovery clean after a mid-loop `os._exit(1)`; hydrate 1k<500ms / 10k<3s; premise re-transmission reduction >=90% vs a stateless re-send-everything baseline. |
| `mcp_conformance_benchmark.py` (T0.3) | `mcp_conformance_fixtures.py` — ~50 ordered cases over all 11 tools incl. the product's injection corpus, failure taxonomy, hostile seed import | 100% case conformance; zero crashes (no tool call may raise); lossless 2-client interleaving (2 processes, overlapping canonicals, fresh scope, 3 trials); p95 <150ms per tool excluding `infer`/`bootstrap_project`. Real stdio transport (initialize + tools/list + tools/call) is probed when `mcp` is importable and reported ok/failed/skipped. |

## Current status (runs of 2026-07-20)

T0.1 and T0.2 **PASS**. T0.3 **FAILS on real product defects** (gate held, not
weakened): `atom_assert` raises on unknown source_type instead of returning a
structured error, and two concurrent-write races (WAL init on first open;
UNIQUE-constraint race on duplicate canonical asserts). Details in
`mcp_conformance_results.md` and the T0 results table in
`benchmark-docs/atomspace.md`.
