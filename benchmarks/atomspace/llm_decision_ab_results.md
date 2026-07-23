# T2.2 — llm_decision_ab (atomspace-derived reasoning in the prompt vs premises alone)

Model: **MOCK** (deterministic harness self-test). N=120 cases x 3 seeds = 360 paired decisions; both arms same model/prompt, memory arm adds the atomspace's derived conclusions.

| Metric | Plain | Memory | Gate |
| --- | --- | --- | --- |
| accuracy | 0.5 | 1.0 (net **+50.0 pts**) | >= +10.0 pts |
| sign test (memory 180 / plain 0 wins) | — | p = 1.25e-12 | < 0.05 |
| injected tokens (median) | 33.0 | 48.5 (x1.47) | <= 1.25x |
| latency median | 1.0ms | 1.0ms | <= +2000ms |

**SELF-TEST (mock model): harness + statistics validated end-to-end; NOT a gate result. Re-run with a provider key for the real T2.2.**

Reproduce (real): `ATOMSPACE_LLM_PROVIDER=SNET SNET_API_KEY=... $HYPERON_MCP_PY benchmarks/atomspace/llm_decision_ab_benchmark.py`
