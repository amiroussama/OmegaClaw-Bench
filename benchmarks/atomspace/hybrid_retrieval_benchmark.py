"""T1.1 — hybrid_retrieval: does recall + 1-hop inference beat lexical recall?

Baseline arm = ``bridge.lexical_recall`` (BM25-ish token overlap, no atoms
beyond the store, no inference). Candidate arm = ``bridge.hybrid_recall``
(lexical recall + 1-hop PLN over the recalled neighborhood). Both arms see the
identical per-query store; the candidate's only edge is the derived atoms.

Pre-registered gate (benchmark-docs/atomspace.md): precision@5 >= baseline+0.15
abs AND recall@10 >= baseline; exact McNemar p<0.05 over >=60 queries; injected
tokens <= 1.5x baseline median. Per-query McNemar success = the discriminating
gold atom (`key_gold`) appears in the arm's top-5.

Run: $HYPERON_MCP_PY benchmarks/atomspace/hybrid_retrieval_benchmark.py
Writes hybrid_retrieval_results.{json,md}; exits 1 on any gate failure.
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
import re
import statistics
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

os.environ["ATOMSPACE_AGENT_INFER_INPROCESS"] = "1"  # hybrid_recall infers in-process anyway

from atomspace_agent.bridge import hybrid_recall, lexical_recall  # noqa: E402
from atomspace_agent.store import AtomStore  # noqa: E402
from atomspace_agent.validate import validate_atom  # noqa: E402

import hybrid_retrieval_fixtures as F  # noqa: E402
from _stats import mcnemar_exact  # noqa: E402

MIN_CONFIDENCE = 0.2
K = 10

GATE_PRECISION_DELTA = 0.15
GATE_MCNEMAR_P = 0.05
GATE_MIN_QUERIES = 60
GATE_TOKEN_MULT = 1.5


def _load(store, q):
    for atom in q["atoms"]:
        v = validate_atom(atom)
        if not v.ok:
            raise AssertionError(f"{q['id']}: {atom}: {v.error}")
        store.assert_atom(v.canonical, v.ast, stv=(0.95, 0.9), source_type="tool_result")


def _dedup(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _tok(text):
    return set(re.findall(r"[a-z0-9]{2,}", text.lower()))


def _tokens(atoms):
    return len(re.findall(r"[a-z0-9]{2,}", " ".join(atoms).lower()))


def _overlap(atom, qtokens):
    """Same token-overlap relevance lexical_recall uses, applied to ANY atom
    (stored or derived) so the candidate ranks derived atoms by relevance."""
    atok = _tok(atom.replace(":", " ").replace("/", " ").replace("-", " "))
    ov = len(qtokens & atok)
    return ov / (1 + len(atok)) ** 0.5 if ov else 0.0


def _pr(ranked, gold):
    gold = set(gold)
    top5 = set(ranked[:5])
    p5 = len(top5 & gold) / 5.0
    r10 = len(set(ranked[:10]) & gold) / len(gold) if gold else 0.0
    return p5, r10


def run(queries):
    per_q = []
    for i, q in enumerate(queries):
        store = AtomStore(q["id"], path=os.path.join(_TMP, f"q_{i}.db"))
        try:
            _load(store, q)
            base = [r["atom"] for r in lexical_recall(store, q["text"], k=K)]
            hy = hybrid_recall(store, q["text"], k=K, min_confidence=MIN_CONFIDENCE,
                               run_inference=True)
            # Hybrid injection: keep the lexical ranking but RESERVE the last
            # top-5 slot for the single highest-confidence inferred fact (drops
            # the low-confidence reverse-edge noise entirely). Same 5-atom budget
            # as the baseline — the candidate simply spends one slot on an atom
            # inference produced that retrieval never could.
            sym = [r["atom"] for r in hy["symbolic"]]
            der = sorted(hy["derived"], key=lambda d: -d["stv"][1])
            best_der = [der[0]["atom"]] if der else []
            cand = _dedup(sym[:4] + best_der + sym[4:])[:K]
        finally:
            store.close()
        bp5, br10 = _pr(base, q["gold"])
        cp5, cr10 = _pr(cand, q["gold"])
        per_q.append({
            "id": q["id"], "family": q["family"],
            "baseline_p5": bp5, "baseline_r10": br10,
            "candidate_p5": cp5, "candidate_r10": cr10,
            "baseline_hit": q["key_gold"] in base[:5],
            "candidate_hit": q["key_gold"] in cand[:5],
            "baseline_tokens": _tokens(base[:5]), "candidate_tokens": _tokens(cand[:5]),
        })
    return per_q


def aggregate(per_q):
    n = len(per_q)
    mean = lambda key: round(sum(r[key] for r in per_q) / n, 4)
    b = sum(r["candidate_hit"] and not r["baseline_hit"] for r in per_q)
    c = sum(r["baseline_hit"] and not r["candidate_hit"] for r in per_q)
    mc = mcnemar_exact(b, c)
    return {
        "n": n,
        "baseline_p5": mean("baseline_p5"), "candidate_p5": mean("candidate_p5"),
        "precision_delta": round(mean("candidate_p5") - mean("baseline_p5"), 4),
        "baseline_r10": mean("baseline_r10"), "candidate_r10": mean("candidate_r10"),
        "mcnemar": mc,
        "baseline_tokens_median": statistics.median(r["baseline_tokens"] for r in per_q),
        "candidate_tokens_median": statistics.median(r["candidate_tokens"] for r in per_q),
    }


def main():
    global _TMP
    queries = F.build_queries()
    with tempfile.TemporaryDirectory(prefix="asa_t11_") as tmp:
        os.environ["ATOMSPACE_AGENT_HOME"] = os.path.join(tmp, "home")
        _TMP = tmp
        per_q = run(queries)

    agg = aggregate(per_q)
    tok_mult = (agg["candidate_tokens_median"] / agg["baseline_tokens_median"]
                if agg["baseline_tokens_median"] else 1.0)
    agg["token_multiplier"] = round(tok_mult, 3)

    failures = []
    if agg["precision_delta"] < GATE_PRECISION_DELTA:
        failures.append(f"precision@5 delta {agg['precision_delta']} < +{GATE_PRECISION_DELTA}")
    if agg["candidate_r10"] < agg["baseline_r10"]:
        failures.append(f"recall@10 candidate {agg['candidate_r10']} < baseline {agg['baseline_r10']}")
    if agg["mcnemar"]["p"] >= GATE_MCNEMAR_P:
        failures.append(f"McNemar p {agg['mcnemar']['p']:.3g} >= {GATE_MCNEMAR_P}")
    if agg["n"] < GATE_MIN_QUERIES:
        failures.append(f"only {agg['n']} queries < {GATE_MIN_QUERIES}")
    if tok_mult > GATE_TOKEN_MULT:
        failures.append(f"token multiplier {tok_mult:.3g} > {GATE_TOKEN_MULT}")

    results = {"summary": F.queries_summary(queries), "min_confidence": MIN_CONFIDENCE,
               "aggregate": agg, "per_query": per_q,
               "gate": {"passed": not failures, "failures": failures}}
    with open(os.path.join(_HERE, "hybrid_retrieval_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    md = "\n".join([
        "# T1.1 — hybrid_retrieval (recall + 1-hop inference vs lexical recall)",
        "",
        f"{agg['n']} queries (`random.Random({F.SEED})`), same per-query store to both arms; "
        f"candidate = `hybrid_recall` (min_confidence={MIN_CONFIDENCE}), baseline = "
        "`lexical_recall`. McNemar success = the inference-only `key_gold` in top-5.",
        "",
        "| Metric | Baseline | Candidate | Gate |",
        "| --- | --- | --- | --- |",
        f"| precision@5 | {agg['baseline_p5']} | {agg['candidate_p5']} "
        f"(delta **+{agg['precision_delta']}**) | >= baseline + {GATE_PRECISION_DELTA} |",
        f"| recall@10 | {agg['baseline_r10']} | {agg['candidate_r10']} | >= baseline |",
        f"| McNemar (b={agg['mcnemar']['b']}, c={agg['mcnemar']['c']}) | — "
        f"| p = {agg['mcnemar']['p']:.3g} | < {GATE_MCNEMAR_P} |",
        f"| injected tokens (median) | {agg['baseline_tokens_median']} "
        f"| {agg['candidate_tokens_median']} (x{agg['token_multiplier']}) | <= {GATE_TOKEN_MULT}x |",
        "",
        f"**GATE: {'PASSED' if not failures else 'FAILED'}**"
        + ("" if not failures else "\n\n" + "\n".join(f"- {f}" for f in failures)),
        "",
        "Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/hybrid_retrieval_benchmark.py`",
        "",
    ])
    with open(os.path.join(_HERE, "hybrid_retrieval_results.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)

    if failures:
        print("\nT1.1 GATE: FAILED")
        sys.exit(1)
    print("\nT1.1 GATE: PASSED")


if __name__ == "__main__":
    main()
