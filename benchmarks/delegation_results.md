# Delegation KPI Benchmark — Issue #18

12 independent subtasks (short sleep + artifact) run serially vs. via isolated concurrent subagents (`src/delegation.py`), plus cross-workdir-write and cancellation probes.

- **baseline** = single-loop, no delegation → serial execution, no isolation/cancellation.
- **candidate** = concurrent isolated subagents with containment + cancellation contract.

| Metric | baseline | candidate |
| --- | --- | --- |
| Subtasks | 12 | 12 |
| Serial wall-clock (s) | 1.2968 | 1.2968 |
| Parallel wall-clock (s) | 1.2968 | 0.2004 |
| Wall-clock improvement % (target >= 30) | 0.0 | 84.5 |
| Success rate | 1.0 | 1.0 |
| Structured outputs (session id + artifact path) | False | True |
| Isolation violations (target 0) | 0 | 0 |
| Clean cancellation + workspace cleanup | False | True |

Candidate runs 12 subtasks **84% faster** than serial (0.20s vs 1.30s) with structured per-subagent outputs, **0** isolation violations, and clean cancellation — none of which the single-loop baseline provides.

Reproduce: `python3 benchmarks/delegation_benchmark.py`
