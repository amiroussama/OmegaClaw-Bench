#!/usr/bin/env sh
# Run every host-runnable atomspace gate in order and report PASS/FAIL.
# Usage: HYPERON_MCP_PY=/path/to/venv/python sh benchmarks/atomspace/run_gates.sh
set -u
PY="${HYPERON_MCP_PY:-/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python}"
HERE="$(cd "$(dirname "$0")" && pwd)"

GATES="nal_truth atomstore mcp_conformance hybrid_retrieval revision_staleness scope_routing multihop_impact"
rc=0
for g in $GATES; do
  printf '\n========== %s ==========\n' "$g"
  "$PY" "$HERE/${g}_benchmark.py" || rc=1
done

printf '\n========== llm_decision_ab (self-test; real run needs a provider key) ==========\n'
"$PY" "$HERE/llm_decision_ab_benchmark.py" --mock || rc=1

printf '\n========== SUMMARY ==========\n'
[ "$rc" -eq 0 ] && echo "ALL HOST-RUNNABLE GATES PASSED (T0.1-0.3, T1.1-1.3, T2.1; T2.2 self-test)" \
               || echo "SOME GATES FAILED — see output above"
exit "$rc"
