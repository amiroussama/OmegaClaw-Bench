"""Host tests for the v2 atomspace engine bridge (benchmarks/freeciv/reason_v2.py).

The v2 atomspace lives in a gitignored scratch dir (OMEGACLAW_V2_DIR); these tests SKIP cleanly
when it is absent (e.g. CI) and otherwise gate the bridge: it builds a v2 world overlay from raw
state, chains it, returns concrete (Recommend ...) strings, and those ground to legal actions.
Standalone runner (no pytest): python3 Autotests/test_freeciv_reason_v2.py
"""

import json
import os
import sys

# --- core-path bootstrap (mirrors the other freeciv tests) ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while _ROOT != os.path.dirname(_ROOT):
    if os.path.isdir(os.path.join(_ROOT, "core", "src")):
        break
    _ROOT = os.path.dirname(_ROOT)
for _p in (os.path.join(_ROOT, "core", "src"), os.path.join(_ROOT, "core"),
           os.path.join(_ROOT, "benchmarks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from freeciv import reason_v2, adapter, ground  # noqa: E402

_STATE = os.path.join(_ROOT, "benchmarks", "freeciv", "samples", "real_state_turn1.json")


def _raw():
    return json.load(open(_STATE, encoding="utf-8"))


def test_world_overlay_built_from_raw():
    if not reason_v2.available():
        print("SKIP (v2 atomspace not present at %s)" % reason_v2.V2_DIR)
        return
    ws = reason_v2.world_sentences_from_raw(_raw())
    assert len(ws) > 50, "expected a populated world overlay, got %d" % len(ws)
    # every entry is (tree, f, c, layer); instance atoms (Unit_*/Tile_*) live only here
    assert all(len(t) == 4 for t in ws)
    joined = " ".join(reason_v2._load("chain").unparse(t[0]) for t in ws)
    assert "Unit_" in joined and "Type_settlers" in joined


def test_derive_yields_founding_recommendations():
    if not reason_v2.available():
        print("SKIP (v2 atomspace not present)")
        return
    recs, meta = reason_v2.derive(_raw())
    assert meta["n_conclusions"] == len(recs)
    assert meta["hops"] >= 2, "expected multi-hop chaining, got %r" % meta
    found = [r for r in recs if "FoundCityNow" in r]
    assert found, "expected >=1 FoundCityNow rec, got %r" % recs
    # concrete only: no unbound templates leak out
    assert all("$" not in r for r in recs)


def test_v2_recs_ground_to_legal_actions():
    if not reason_v2.available():
        print("SKIP (v2 atomspace not present)")
        return
    raw = _raw()
    norm = adapter.normalize_state(raw)
    recs, _ = reason_v2.derive(raw)
    grounded = [ground.ground(r, norm) for r in recs if "FoundCityNow" in r]
    assert grounded and all(g and g["type"] == "unit_build_city" for g in grounded), \
        "FoundCityNow should ground to unit_build_city, got %r" % grounded


def test_absent_v2_dir_degrades_gracefully():
    """derive() on a missing dir must return empty, never raise."""
    saved = reason_v2.V2_DIR
    try:
        reason_v2.V2_DIR = "/nonexistent/v2/dir"
        reason_v2._static = None
        assert reason_v2.available() is False
        recs, meta = reason_v2.derive(_raw())
        assert recs == [] and meta["n_conclusions"] == 0
    finally:
        reason_v2.V2_DIR = saved
        reason_v2._static = None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
        passed += 1
    print("\nAll %d freeciv reason_v2 tests passed" % passed)
