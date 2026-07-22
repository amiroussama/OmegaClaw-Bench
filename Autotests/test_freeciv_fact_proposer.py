"""Host tests for the LLM fact-enrichment module (hybrid facts, no network/LLM/Docker).

Covers ``validate_facts`` (malformed/hallucinated dropped, confidence clamped to the llm tier) and
``propose_facts`` end-to-end against a MONKEYPATCHED ``urlopen`` returning a canned response, so
the parse + validate + clamp path is exercised deterministically. These facts live ONLY in live
sims; the host determinism path (benchmark.py / adapter tests) never calls this module.
"""

# --- OmegaClaw-Bench core-path bootstrap (added by the benchmarks<->core split) ---
import os as _ocp, sys as _scp
_cp_root = _ocp.path.dirname(_ocp.path.abspath(__file__))
while _cp_root != _ocp.path.dirname(_cp_root):
    if _ocp.path.isdir(_ocp.path.join(_cp_root, "core", "src")):
        break
    _cp_root = _ocp.path.dirname(_cp_root)
for _cp in (_ocp.path.join(_cp_root, "core", "src"), _ocp.path.join(_cp_root, "core")):
    if _cp not in _scp.path:
        _scp.path.insert(0, _cp)
# --- end OmegaClaw-Bench core-path bootstrap ---

import io
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BENCH = os.path.join(_REPO_ROOT, "benchmarks")
_SRC = os.path.join(_REPO_ROOT, "src")
for _p in (_BENCH, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from freeciv import fact_proposer, atoms  # noqa: E402

_LLM_CONF = fact_proposer.LLM_CONF


def test_validate_drops_malformed_and_clamps_confidence():
    raw = [
        {"subj": "City_2", "pred": "Inheritance", "obj": "Exposed", "f": 1.0, "c": 0.9},  # ok, clamp c
        {"subj": "Unit_7", "pred": "Evaluation", "obj": "Near:City_1", "f": 0.8, "c": 0.4},  # ok
        {"subj": "City_3", "pred": "Implication", "obj": "Whatever", "f": 1.0, "c": 0.5},  # bad pred
        {"subj": "City_4", "pred": "Inheritance"},                                          # missing obj
        {"subj": 5, "pred": "Inheritance", "obj": "Exposed"},                               # non-str subj
        "not a dict",                                                                        # junk
    ]
    facts = fact_proposer.validate_facts(raw)
    stmts = [atoms._statement(f) for f in facts]
    assert "(Inheritance City_2 Exposed)" in stmts
    assert "(Evaluation (Predicate Near) (List Unit_7 City_1))" in stmts
    assert all("Implication" not in s and "City_4" not in s and "City_3" not in s for s in stmts)
    assert len(facts) == 2
    # confidence never exceeds the llm tier; the 0.4 proposal is preserved (already below tier)
    by_subj = {f["subj"]: f for f in facts}
    assert by_subj["City_2"]["c"] == _LLM_CONF          # 0.9 clamped down to the tier
    assert by_subj["Unit_7"]["c"] == 0.4                # already below tier -> unchanged
    # every kept fact renders to a well-formed atom
    assert all(atoms.validate_atom(s) is None for s in stmts)


def test_validate_dedupes_and_sorts():
    raw = [{"subj": "City_1", "pred": "Inheritance", "obj": "Exposed"},
           {"subj": "City_1", "pred": "Inheritance", "obj": "Exposed"},   # dup
           {"subj": "Aaa", "pred": "Inheritance", "obj": "Zed"}]
    facts = fact_proposer.validate_facts(raw)
    assert len(facts) == 2
    assert [f["subj"] for f in facts] == ["Aaa", "City_1"]  # deterministically sorted


def test_propose_facts_no_key_is_best_effort():
    saved = fact_proposer._KEY
    fact_proposer._KEY = ""
    try:
        facts, meta = fact_proposer.propose_facts({"player_perspective": 1})
        assert facts == [] and meta["error"] == "no_key"
    finally:
        fact_proposer._KEY = saved


def test_propose_facts_parses_and_validates(monkeypatch_urlopen=None):
    """propose_facts wires a mocked HTTP response through the parse+validate pipeline."""
    norm = {"player_perspective": 1, "turn": 5, "units": [], "cities": [], "economic": {},
            "strategic": {}, "techs": {}}
    body = json.dumps({"choices": [{"message": {"content":
           '{"facts":[{"subj":"City_1","pred":"Inheritance","obj":"Exposed","f":1.0,"c":0.99},'
           '{"subj":"X","pred":"Implication","obj":"Y","f":1,"c":1}]}'}}]})

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    saved_key, saved_open = fact_proposer._KEY, fact_proposer.urllib.request.urlopen
    fact_proposer._KEY = "test-key"
    fact_proposer.urllib.request.urlopen = lambda req, timeout=0: _Resp(body.encode())
    try:
        facts, meta = fact_proposer.propose_facts(norm)
        assert meta["error"] is None
        assert meta["n_raw"] == 2 and meta["n_llm_facts"] == 1     # bad-pred fact dropped
        assert atoms._statement(facts[0]) == "(Inheritance City_1 Exposed)"
        assert facts[0]["c"] == _LLM_CONF                          # 0.99 clamped to tier
    finally:
        fact_proposer._KEY = saved_key
        fact_proposer.urllib.request.urlopen = saved_open


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} fact_proposer tests passed".format(len(fns)))
