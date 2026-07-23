"""T2.1 — multihop_impact, the primary program gate.

Measures whether multi-hop PLN chaining changes DECISIONS a strong retrieval
baseline gets wrong, over the 80 pre-registered decision cases in
``multihop_impact_fixtures``. Both arms receive the identical premises (loaded
into a fresh per-case store) and the identical trusted ``CODE_RULES`` text
(inline for the baseline, loaded into the runtime for PLN) — the candidate's
only edge is inference.

  * PLN arm      — ``infer_in_process(question, max_hops=3, min_confidence)``;
    decision = YES iff a matched conclusion unifies the (ground) query above the
    confidence floor. When the product exposes the ``code_rules`` mechanism the
    trusted invariant rules are loaded too (feature-detected).
  * baseline arm — ``bridge.lexical_recall`` (BM25-ish) over the store; decision
    = YES iff a retrieved stored atom unifies the query. Retrieval only, no
    inference — it structurally cannot return a never-stored composed edge.

Pre-registered gate (benchmark-docs/atomspace.md): exact-match >= baseline+0.25
abs; net decision-flips-to-correct >= +20/80; exact two-sided sign test p<0.05;
median inference <2s.

Run with the Hyperon-MCP venv python (in-process inference, warm runtime):
    HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python
    $HYPERON_MCP_PY benchmarks/atomspace/multihop_impact_benchmark.py

Writes multihop_impact_results.{json,md} next to this script; exits 1 on any
gate failure. All state lives in a tempdir via ATOMSPACE_AGENT_HOME.
"""

# --- atomspace-agent product locator (Bench repo tests the product, not core) ---
import os as _os
import sys as _sys

try:
    import atomspace_agent  # noqa: F401
except ImportError:
    _sys.path.insert(0, _os.environ.get("ATOMSPACE_AGENT_SRC",
                                        "/home/rojo-dev/Repos/Hyperon-MCP/src"))
    import atomspace_agent  # noqa: F401
# --- end product locator ---

import inspect
import json
import os
import statistics
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# In-process inference: one warm MeTTa runtime shared across all 80 cases, which
# is how the latency gate is measured (a fresh subprocess per call is a separate,
# separately-reported cost). Must be set before importing the product inference.
os.environ["ATOMSPACE_AGENT_INFER_INPROCESS"] = "1"

from atomspace_agent import sexpr  # noqa: E402
from atomspace_agent.bridge import lexical_recall  # noqa: E402
from atomspace_agent.inference import infer_in_process  # noqa: E402
from atomspace_agent.store import AtomStore  # noqa: E402
from atomspace_agent.validate import validate_atom  # noqa: E402

import multihop_impact_fixtures as F  # noqa: E402
from _stats import sign_test  # noqa: E402

MIN_CONFIDENCE = 0.2
MAX_HOPS = 3

# Pre-registered gates.
GATE_DELTA = 0.25
GATE_NET_FLIPS = 20
GATE_SIGN_P = 0.05
GATE_MEDIAN_MS = 2000.0

# Does the product expose the trusted code_rules channel yet?
_INFER_PARAMS = inspect.signature(infer_in_process).parameters
HAS_CODE_RULES = "code_rules" in _INFER_PARAMS


def _load(store, case):
    for atom, stv in case["premises"]:
        v = validate_atom(atom)
        if not v.ok:
            raise AssertionError(f"{case['id']}: premise rejected: {atom}: {v.error}")
        store.assert_atom(v.canonical, v.ast, stv=tuple(stv), source_type="tool_result")


def _pln_decision(store, case):
    """YES iff inference produces a matched conclusion above the floor."""
    kwargs = dict(max_hops=MAX_HOPS, min_confidence=MIN_CONFIDENCE, engine="both",
                  deadline_s=10.0)
    if HAS_CODE_RULES:
        kwargs["code_rules"] = F.CODE_RULES
    result = infer_in_process(store, case["question"], **kwargs)
    q_ast = sexpr.parse(case["question"])
    hit = any(sexpr.unify(q_ast, sexpr.parse(m["atom"])) is not None
              and m["stv"][1] >= MIN_CONFIDENCE for m in result["matched"])
    return hit, result["stats"].get("elapsed_ms", 0.0)


def _baseline_decision(store, case):
    """YES iff a lexically-retrieved STORED atom unifies the query (no inference).
    k spans every premise, so the baseline sees all evidence — it simply cannot
    compose it."""
    q_ast = sexpr.parse(case["question"])
    k = max(10, len(case["premises"]))
    for rec in lexical_recall(store, case["question"], k=k):
        if sexpr.unify(q_ast, sexpr.parse(rec["atom"])) is not None:
            return True
    return False


def run(cases):
    per_case = []
    pln_latencies = []
    for i, case in enumerate(cases):
        store = AtomStore(case["id"], path=os.path.join(_TMP, f"case_{i}.db"))
        try:
            _load(store, case)
            pln_yes, ms = _pln_decision(store, case)
            base_yes = _baseline_decision(store, case)
        finally:
            store.close()
        pln_latencies.append(ms)
        per_case.append({
            "id": case["id"], "family": case["family"], "gold": case["gold"],
            "pln_yes": pln_yes, "baseline_yes": base_yes,
            "pln_correct": pln_yes == case["gold"],
            "baseline_correct": base_yes == case["gold"],
            "latency_ms": ms,
        })
    return per_case, pln_latencies


def aggregate(per_case, pln_latencies):
    n = len(per_case)
    pln_exact = sum(r["pln_correct"] for r in per_case) / n
    base_exact = sum(r["baseline_correct"] for r in per_case) / n
    flips_correct = sum(r["pln_correct"] and not r["baseline_correct"] for r in per_case)
    flips_wrong = sum(r["baseline_correct"] and not r["pln_correct"] for r in per_case)
    net = flips_correct - flips_wrong
    p = sign_test(flips_correct, flips_correct + flips_wrong)
    median_ms = statistics.median(pln_latencies) if pln_latencies else 0.0

    by_family = {}
    for r in per_case:
        f = by_family.setdefault(r["family"], {"n": 0, "pln": 0, "base": 0})
        f["n"] += 1
        f["pln"] += r["pln_correct"]
        f["base"] += r["baseline_correct"]

    return {
        "n": n, "pln_exact": round(pln_exact, 4), "baseline_exact": round(base_exact, 4),
        "delta": round(pln_exact - base_exact, 4),
        "flips_to_correct": flips_correct, "flips_to_wrong": flips_wrong, "net_flips": net,
        "sign_test_p": p, "median_latency_ms": round(median_ms, 1),
        "mean_latency_ms": round(statistics.mean(pln_latencies), 1) if pln_latencies else 0.0,
        "max_latency_ms": round(max(pln_latencies), 1) if pln_latencies else 0.0,
        "by_family": by_family,
    }


def main():
    global _TMP
    cases = F.build_cases()
    with tempfile.TemporaryDirectory(prefix="asa_t21_") as tmp:
        os.environ["ATOMSPACE_AGENT_HOME"] = os.path.join(tmp, "home")
        _TMP = tmp
        per_case, latencies = run(cases)

    agg = aggregate(per_case, latencies)
    failures = []
    if agg["delta"] < GATE_DELTA:
        failures.append(f"exact-match delta {agg['delta']} < +{GATE_DELTA} "
                        f"(pln {agg['pln_exact']} vs baseline {agg['baseline_exact']})")
    if agg["net_flips"] < GATE_NET_FLIPS:
        failures.append(f"net flips-to-correct {agg['net_flips']} < +{GATE_NET_FLIPS}")
    if agg["sign_test_p"] >= GATE_SIGN_P:
        failures.append(f"sign-test p {agg['sign_test_p']:.3g} >= {GATE_SIGN_P}")
    if agg["median_latency_ms"] >= GATE_MEDIAN_MS:
        failures.append(f"median inference {agg['median_latency_ms']}ms >= {GATE_MEDIAN_MS}ms")

    mode = "code_rules loaded" if HAS_CODE_RULES else "NO code_rules (vendored PLN only)"
    results = {"summary": F.cases_summary(cases), "code_rules_mode": mode,
               "min_confidence": MIN_CONFIDENCE, "max_hops": MAX_HOPS,
               "aggregate": agg, "per_case": per_case,
               "gate": {"passed": not failures, "failures": failures}}
    with open(os.path.join(_HERE, "multihop_impact_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    fam = agg["by_family"]
    fam_rows = [f"| {name} | {d['n']} | {d['base']}/{d['n']} | {d['pln']}/{d['n']} |"
                for name, d in sorted(fam.items())]
    md = "\n".join([
        "# T2.1 — multihop_impact (primary program gate)",
        "",
        f"80 pre-registered decision cases (`random.Random({F.SEED})`); both arms get the "
        f"same premises + same rule text, in-process inference (min_confidence="
        f"{MIN_CONFIDENCE}, max_hops={MAX_HOPS}). Mode: **{mode}**.",
        "",
        "| Family | N | baseline correct | PLN correct |",
        "| --- | --- | --- | --- |",
        *fam_rows,
        "",
        "| Metric | Value | Gate |",
        "| --- | --- | --- |",
        f"| exact-match (PLN vs baseline) | {agg['pln_exact']} vs {agg['baseline_exact']} "
        f"(delta **+{agg['delta']}**) | >= baseline + {GATE_DELTA} |",
        f"| net decision-flips-to-correct | **+{agg['net_flips']}** "
        f"({agg['flips_to_correct']} to-correct, {agg['flips_to_wrong']} to-wrong) "
        f"| >= +{GATE_NET_FLIPS}/80 |",
        f"| exact two-sided sign test | p = {agg['sign_test_p']:.3g} | < {GATE_SIGN_P} |",
        f"| median inference latency | {agg['median_latency_ms']} ms "
        f"(mean {agg['mean_latency_ms']}, max {agg['max_latency_ms']}) | < {int(GATE_MEDIAN_MS)} ms |",
        "",
        f"**GATE: {'PASSED' if not failures else 'FAILED'}**"
        + ("" if not failures else "\n\n" + "\n".join(f"- {f}" for f in failures)),
        "",
        "Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/multihop_impact_benchmark.py` "
        "(HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python)",
        "",
    ])
    with open(os.path.join(_HERE, "multihop_impact_results.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)

    if failures:
        print("\nT2.1 GATE: FAILED")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nT2.1 GATE: PASSED")


if __name__ == "__main__":
    main()
