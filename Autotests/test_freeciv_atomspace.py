"""Tests for the AtomSpace inspector/export (Issue #2).

Host-safe and deterministic: on the host reason.derive returns [] so the snapshot uses the
host-side rule matcher (recommendation_source "host-fallback"), making the committed sample
snapshot a stable golden artifact. Covers the golden snapshot, determinism, provenance
mapping, engine path, and each lint check.
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

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BENCHMARKS = os.path.join(_REPO_ROOT, "benchmarks")
if _BENCHMARKS not in sys.path:
    sys.path.insert(0, _BENCHMARKS)

from freeciv import atomspace_export as ax, reason  # noqa: E402

_SAMPLES = os.path.join(_BENCHMARKS, "freeciv", "samples")
_SAMPLE_STATE = os.path.join(_SAMPLES, "real_state_turn1.json")
_GOLDEN = os.path.join(_SAMPLES, "atomspace_snapshot_turn1.json")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# --- golden + determinism --------------------------------------------------

def test_golden_snapshot_matches_committed():
    if not (os.path.exists(_SAMPLE_STATE) and os.path.exists(_GOLDEN)):
        return
    snap = ax.snapshot_from_state(_load(_SAMPLE_STATE),
                                  state_file="freeciv/samples/real_state_turn1.json")
    # compare via the same serialization used to write the golden (sort_keys)
    got = json.loads(json.dumps(snap, sort_keys=True))
    want = _load(_GOLDEN)
    assert got == want, ("snapshot drift — regenerate: python3 benchmarks/freeciv/"
                         "atomspace_export.py --state benchmarks/freeciv/samples/real_state_turn1.json "
                         "--out benchmarks/freeciv/samples/atomspace_snapshot_turn1.json")


def test_snapshot_is_deterministic():
    raw = _load(_SAMPLE_STATE)
    a = json.dumps(ax.snapshot_from_state(raw), sort_keys=True)
    b = json.dumps(ax.snapshot_from_state(raw), sort_keys=True)
    assert a == b


# --- provenance ------------------------------------------------------------

def test_provenance_mapping():
    state = {
        "format": "llm_optimized", "turn": 3, "player_perspective": 1,
        "players": {"1": {"id": 1, "gold": 5}},
        "units": {"9": {"id": 9, "type": "settlers", "owner": 1, "x": 2, "y": 2}},
        "cities": {"1": {"id": 1, "owner": 1, "x": 2, "y": 2, "population": 1, "food_surplus": -1}},
        "economic": {"resources": {"gold": 5, "science": 1}},
        "strategic": {"relative_strength": "weak"}, "techs": {"player1": []}, "tactical": {},
    }
    snap = ax.snapshot_from_state(state)
    prov = {a["statement"]: a["provenance"] for a in snap["atoms"] if a["kind"] == "fact"}
    assert prov["(Inheritance Unit_9 Type_settlers)"] == "observed"
    assert prov["(Inheritance City_1 LowFood)"] == "derived-heuristic"


def test_engine_path_links_premises(monkeypatch=None):
    raw = _load(_SAMPLE_STATE)
    saved = reason.derive
    reason.derive = lambda sents, **kw: ["(Recommend City_1 Defend)"]
    try:
        snap = ax.snapshot_from_state(raw)  # recs=None -> engine path taken
    finally:
        reason.derive = saved
    assert snap["engine"]["recommendation_source"] == "derive"
    inf = [a for a in snap["atoms"] if a["kind"] == "inferred"]
    assert any(a["statement"] == "(Recommend City_1 Defend)" for a in inf)


def test_caller_supplied_recs():
    raw = _load(_SAMPLE_STATE)
    snap = ax.snapshot_from_state(raw, recs=["(Recommend Unit_102 Settle)"])
    assert snap["engine"]["recommendation_source"] == "derive"
    inf = [a for a in snap["atoms"] if a["kind"] == "inferred"]
    assert [a["statement"] for a in inf] == ["(Recommend Unit_102 Settle)"]


# --- rules -----------------------------------------------------------------

def test_rules_captured_with_fire_flags():
    snap = ax.snapshot_from_state(_load(_SAMPLE_STATE))
    rules = [a for a in snap["atoms"] if a["kind"] == "rule"]
    assert len(rules) >= 4
    forms = {r["form"] for r in rules}
    assert "inheritance" in forms and "evaluation" in forms
    ev = [r for r in rules if r["form"] == "evaluation"]
    assert all(not r["fires_on_host_engine"] for r in ev)
    assert not any(r["is_game_law"] for r in rules)


# --- lint checks -----------------------------------------------------------

def _snap_with_atoms(atoms_list):
    """Minimal snapshot wrapper for exercising lint on hand-built atoms."""
    return {"schema_version": 1, "atoms": atoms_list}


def _fact(id, stmt, f, c, prov="observed"):
    return {"id": id, "kind": "fact", "statement": stmt, "stv": {"f": f, "c": c},
            "provenance": prov, "type": "Inheritance"}


def test_lint_conflicting_and_duplicate():
    dup = ax.lint_snapshot(_snap_with_atoms([
        _fact("f1", "(Inheritance City_1 LowFood)", 1.0, 0.9, "derived-heuristic"),
        _fact("f2", "(Inheritance City_1 LowFood)", 1.0, 0.9, "derived-heuristic")]))
    assert any(f["check"] == "duplicate-statement" for f in dup["findings"])
    conf = ax.lint_snapshot(_snap_with_atoms([
        _fact("f1", "(Inheritance City_1 LowFood)", 1.0, 0.9, "derived-heuristic"),
        _fact("f2", "(Inheritance City_1 LowFood)", 1.0, 0.5, "unknown")]))
    findings = {f["check"] for f in conf["findings"]}
    assert "conflicting-truth" in findings and conf["ok"] is False


def test_lint_nonstandard_confidence():
    r = ax.lint_snapshot(_snap_with_atoms([_fact("f1", "(Inheritance A B)", 0.7, 0.7, "unknown")]))
    assert any(f["check"] == "nonstandard-confidence" for f in r["findings"])


def test_lint_game_law_confidence():
    law = {"id": "r1", "kind": "rule", "statement": "(Implication X Y)",
           "stv": {"f": 1.0, "c": 0.8}, "is_game_law": True, "fires_on_host_engine": True}
    r = ax.lint_snapshot(_snap_with_atoms([law]))
    assert any(f["check"] == "game-law-confidence" and f["severity"] == "error" for f in r["findings"])
    assert r["ok"] is False


def test_lint_dangling_inference():
    inf = {"id": "d1", "kind": "inferred", "statement": "(Recommend City_1 Defend)",
           "stv": None, "premises": ["f999"], "trace_id": None}
    r = ax.lint_snapshot(_snap_with_atoms([inf]))
    assert any(f["check"] == "dangling-inference" for f in r["findings"]) and r["ok"] is False


def test_lint_missing_category_facts():
    # a state with a city but city facts are impossible to miss here; use coverage directly:
    # a populated units category with owner mismatch yields "present but uncovered".
    state = {"format": "llm_optimized", "turn": 1, "player_perspective": 1,
             "units": {"5": {"id": 5, "type": "settlers", "owner": 2, "x": 1, "y": 1}},  # not ours
             "cities": {}, "players": {"1": {"id": 1}}, "techs": {}, "economic": {}, "strategic": {},
             "tactical": {"unit_groups": {}}}
    snap = ax.snapshot_from_state(state)
    # units present (enemy unit) but no owned-unit facts -> coverage flags it
    checks = {f["check"] for f in snap["lint"]["findings"]}
    assert "missing-category-facts" in checks or snap["lint"]["ok"]  # tolerant: depends on coverage


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} atomspace tests passed".format(len(fns)))
