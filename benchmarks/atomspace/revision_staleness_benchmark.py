"""T1.2 — revision_staleness: does NAL revision + supersession keep the current
answer correct where an append-only memory goes stale?

Candidate = the product store (``assert_atom`` auto-revises a re-asserted
canonical via ``revision.revise``; ``retract`` supersedes a replaced fact).
Baseline = append-only / no-merge / no-supersede: it keeps what it learned first
and never marks anything stale (modelled on a real store: revision baseline
asserts only the first value; supersession baseline asserts both without
retract).

Pre-registered gate (benchmark-docs/atomspace.md): current-answer accuracy >=0.9
AND >= baseline+0.25; contradiction-leak <=5%. Leak = a stale/wrong value is
still the active answer (revision) or a superseded atom is still active
(supersession).

Run: $HYPERON_MCP_PY benchmarks/atomspace/revision_staleness_benchmark.py
Writes revision_staleness_results.{json,md}; exits 1 on any gate failure.
"""

# --- atomspace-agent product locator ---
import os as _os
import sys as _sys

try:
    import atomspace_agent  # noqa: F401
except ImportError:
    _sys.path.insert(0, _os.environ.get("ATOMSPACE_AGENT_SRC",
                                        "/home/rojo-dev/Repos/Hyperon-MCP/src"))
    import atomspace_agent  # noqa: F401
# --- end product locator ---

import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from atomspace_agent import sexpr  # noqa: E402
from atomspace_agent.store import AtomStore  # noqa: E402
from atomspace_agent.validate import validate_atom  # noqa: E402

import revision_staleness_fixtures as F  # noqa: E402

GATE_ACCURACY = 0.9
GATE_ACCURACY_DELTA = 0.25
GATE_LEAK = 0.05


def _assert(store, atom, stv):
    v = validate_atom(atom)
    if not v.ok:
        raise AssertionError(f"{atom}: {v.error}")
    return store.assert_atom(v.canonical, v.ast, stv=tuple(stv), source_type="tool_result")


def _active_modules(store, file_term):
    """Modules M with an active (Inheritance file:F M)."""
    pat = sexpr.parse(f"(Inheritance {file_term} $m)")
    return {m["bindings"]["$m"] for m in store.query_pattern(pat, include_superseded=False)}


def _revision_case(cand, base, case):
    c = case["canonical"]
    # candidate: assert wrong/first, then correct/second -> store revises.
    _assert(cand, c, case["first_stv"])
    _assert(cand, c, case["second_stv"])
    cf = cand.get(c)["stv"][0]
    cand_ans = cf > 0.5
    # baseline: learned the first value, never updated.
    _assert(base, c, case["first_stv"])
    bf = base.get(c)["stv"][0]
    base_ans = bf > 0.5
    gold = case["gold_true"]
    return {"gold": gold, "cand_correct": cand_ans == gold, "base_correct": base_ans == gold,
            "cand_leak": cand_ans != gold, "base_leak": base_ans != gold,
            "cand_f": round(cf, 4), "base_f": round(bf, 4)}


def _supersession_case(cand, base, case):
    # candidate: old fact retracted + superseded by the new fact, then new asserted.
    _assert(cand, case["old"], [1.0, 0.9])
    cand.retract(sexpr.canonical(case["old"]), reason="module moved",
                 superseded_by=sexpr.canonical(case["new"]))
    _assert(cand, case["new"], [1.0, 0.9])
    cand_mods = _active_modules(cand, case["file"])
    cand_correct = cand_mods == {case["new_module"]}
    cand_leak = case["old_module"] in cand_mods
    # baseline: both facts asserted, nothing retracted.
    _assert(base, case["old"], [1.0, 0.9])
    _assert(base, case["new"], [1.0, 0.9])
    base_mods = _active_modules(base, case["file"])
    base_correct = base_mods == {case["new_module"]}
    base_leak = case["old_module"] in base_mods
    return {"gold": case["new_module"], "cand_correct": cand_correct, "base_correct": base_correct,
            "cand_leak": cand_leak, "base_leak": base_leak}


def run(cases):
    per_case = []
    for i, case in enumerate(cases):
        cand = AtomStore(f"{case['id']}-c", path=os.path.join(_TMP, f"c_{i}.db"))
        base = AtomStore(f"{case['id']}-b", path=os.path.join(_TMP, f"b_{i}.db"))
        try:
            r = (_revision_case if case["kind"] == "revision" else _supersession_case)(cand, base, case)
        finally:
            cand.close(); base.close()
        r.update(id=case["id"], kind=case["kind"])
        per_case.append(r)
    return per_case


def aggregate(per_case):
    n = len(per_case)
    return {
        "n": n,
        "candidate_accuracy": round(sum(r["cand_correct"] for r in per_case) / n, 4),
        "baseline_accuracy": round(sum(r["base_correct"] for r in per_case) / n, 4),
        "candidate_leak": round(sum(r["cand_leak"] for r in per_case) / n, 4),
        "baseline_leak": round(sum(r["base_leak"] for r in per_case) / n, 4),
    }


def main():
    global _TMP
    cases = F.build_cases()
    with tempfile.TemporaryDirectory(prefix="asa_t12_") as tmp:
        os.environ["ATOMSPACE_AGENT_HOME"] = os.path.join(tmp, "home")
        _TMP = tmp
        per_case = run(cases)

    agg = aggregate(per_case)
    agg["accuracy_delta"] = round(agg["candidate_accuracy"] - agg["baseline_accuracy"], 4)
    failures = []
    if agg["candidate_accuracy"] < GATE_ACCURACY:
        failures.append(f"current-answer accuracy {agg['candidate_accuracy']} < {GATE_ACCURACY}")
    if agg["accuracy_delta"] < GATE_ACCURACY_DELTA:
        failures.append(f"accuracy delta {agg['accuracy_delta']} < +{GATE_ACCURACY_DELTA}")
    if agg["candidate_leak"] > GATE_LEAK:
        failures.append(f"contradiction-leak {agg['candidate_leak']} > {GATE_LEAK}")

    results = {"summary": F.cases_summary(cases), "aggregate": agg, "per_case": per_case,
               "gate": {"passed": not failures, "failures": failures}}
    with open(os.path.join(_HERE, "revision_staleness_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    md = "\n".join([
        "# T1.2 — revision_staleness (NAL revision + supersession vs append-only)",
        "",
        f"{agg['n']} knowledge-update cases (`random.Random({F.SEED})`): 30 revision "
        "(same canonical re-asserted with better evidence) + 30 supersession (fact retracted "
        "and replaced). Candidate = product store; baseline = append-only / no-supersede.",
        "",
        "| Metric | Baseline | Candidate | Gate |",
        "| --- | --- | --- | --- |",
        f"| current-answer accuracy | {agg['baseline_accuracy']} | {agg['candidate_accuracy']} "
        f"(delta **+{agg['accuracy_delta']}**) | >= 0.9 AND >= baseline+{GATE_ACCURACY_DELTA} |",
        f"| contradiction-leak | {agg['baseline_leak']} | {agg['candidate_leak']} | <= {GATE_LEAK} |",
        "",
        f"**GATE: {'PASSED' if not failures else 'FAILED'}**"
        + ("" if not failures else "\n\n" + "\n".join(f"- {f}" for f in failures)),
        "",
        "Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/revision_staleness_benchmark.py`",
        "",
    ])
    with open(os.path.join(_HERE, "revision_staleness_results.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)

    if failures:
        print("\nT1.2 GATE: FAILED")
        sys.exit(1)
    print("\nT1.2 GATE: PASSED")


if __name__ == "__main__":
    main()
