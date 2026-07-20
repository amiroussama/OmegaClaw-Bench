"""T0.1 fixtures: the golden truth-value conformance corpus.

The corpus VALUES live in the product (`atomspace_agent.conformance` — the
pure-Python `truth.py` reimplementation of the vendored lib_nal/lib_pln is the
golden reference). This wrapper exists so OmegaClaw-Bench records the corpus
size and category breakdown alongside the results: a silent corpus shrink in
the product would show up as a diff here, not as a quietly weaker gate.

Run with the Hyperon-MCP venv python:
    HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python
    $HYPERON_MCP_PY benchmarks/atomspace/nal_truth_fixtures.py   # prints summary
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

from atomspace_agent.conformance import EPSILON, RULE_CASES, truth_cases  # noqa: E402

# Minimum corpus size the Bench repo pre-registers: if the product corpus ever
# shrinks below this, the T0.1 benchmark fails loudly instead of passing on less.
MIN_TRUTH_CASES = 190
MIN_RULE_CASES = 4


def corpus_summary():
    """Size + category counts of the product corpus (recorded in results)."""
    cases = list(truth_cases())
    by_family = {"nal": 0, "pln": 0}
    by_kind = {"stv": 0, "scalar": 0, "empty": 0}
    for c in cases:
        fn = c["metta"].split()[0].lstrip("!(")
        by_family["pln" if fn.startswith("Truth__") else "nal"] += 1
        want = c["expected"]
        if want is None:
            by_kind["empty"] += 1
        elif isinstance(want, tuple):
            by_kind["stv"] += 1
        else:
            by_kind["scalar"] += 1
    return {
        "truth_cases": len(cases),
        "rule_cases": len(RULE_CASES),
        "epsilon": EPSILON,
        "by_family": by_family,
        "by_expected_kind": by_kind,
        "rule_case_names": [c["name"] for c in RULE_CASES],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(corpus_summary(), indent=2))
