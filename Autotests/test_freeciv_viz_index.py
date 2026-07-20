"""Tests for the dashboard data builder (Issue #4): trace + snapshot shipping, A/B raw moves.

Host-safe: builds a temp ab_runs tree and points build_index at it via monkeypatching the module
constant, then asserts the index carries per-unit moves (with error_code/trace_id), the referenced
PLN traces (filtered), and the per-run AtomSpace snapshot — everything the page needs to open a
trace from an action row without a live game.
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
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VIZ = os.path.join(_REPO_ROOT, "benchmarks", "freeciv", "viz")
_FREECIV = os.path.join(_REPO_ROOT, "benchmarks", "freeciv")
for _p in (_VIZ, _FREECIV):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_index  # noqa: E402


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _move(actor, valid, trace_id, error_code=None, pln=True):
    return {"actor": actor, "actor_kind": "unit_id", "action_type": "unit_move",
            "target": {"x": 1, "y": 1}, "valid": valid, "error_code": error_code,
            "error_message": ("off-map" if error_code else None),
            "pln_recommended": pln, "trace_id": trace_id}


def _trace_file(traces_dir, tid):
    os.makedirs(traces_dir, exist_ok=True)
    rec = {"schema": "pln-trace/v1", "trace_id": tid, "query": "recommend-for",
           "facts": ["((Inheritance City_1 Undefended) (stv 1.0 0.99))"],
           "conclusions": [{"atom": "(Recommend City_1 Defend)",
                            "stv": {"strength": 0.9, "confidence": 0.71}, "rule_id": "recommend-defend"}],
           "recommendations": ["(Recommend City_1 Defend)"], "status": "ok"}
    with open(os.path.join(traces_dir, "%s.json" % tid), "w", encoding="utf-8") as f:
        json.dump(rec, f)


def _snapshot_file(d):
    snap = {"schema_version": 1, "counts": {"observed": 3, "rule": 4},
            "atoms": [], "lint": {"ok": True, "findings": []}}
    with open(os.path.join(d, "atomspace_latest.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f)


def _build_in(base):
    saved = build_index._AB_RUNS
    build_index._AB_RUNS = base
    try:
        return build_index.build()
    finally:
        build_index._AB_RUNS = saved


def test_duel_run_ships_moves_traces_snapshot():
    with tempfile.TemporaryDirectory() as base:
        run = os.path.join(base, "duelX")
        g1 = os.path.join(run, "g1")
        tid = "pln-deadbeef0001"
        rows = [
            {"turn": 1,
             "side0": {"arm": "pln", "metrics": {"n_cities": 1, "n_units": 2, "n_techs": 0},
                       "proposed": 1, "submitted": 0, "blocked": 1, "n_conclusions": 1,
                       "moves": [_move(7, False, tid, error_code="E210")],
                       "recommendations": [{"entity": "Unit_7", "action": "Defend"}],
                       "pln_trace_id": tid},
             "side1": {"arm": "plain", "metrics": {"n_cities": 1, "n_units": 2, "n_techs": 0},
                       "proposed": 1, "submitted": 1, "blocked": 0, "n_conclusions": 0,
                       "moves": [_move(9, True, None, pln=False)], "recommendations": [],
                       "pln_trace_id": None}},
        ]
        _write_jsonl(os.path.join(g1, "duel.jsonl"), rows)
        _trace_file(os.path.join(g1, "traces"), tid)
        _snapshot_file(g1)

        idx = _build_in(base)
        duel = next(r for r in idx["runs"] if r["type"] == "duel")
        assert duel["has_moves"]
        game = duel["games"][0]
        mv = game["moves"][0]
        # invalid move retains its reason + trace link
        assert mv["pln"][0]["error_code"] == "E210"
        assert mv["pln"][0]["trace_id"] == tid
        # the referenced trace is shipped (and only it)
        assert tid in game["traces"] and len(game["traces"]) == 1
        assert game["traces"][tid]["conclusions"][0]["rule_id"] == "recommend-defend"
        # the per-run snapshot is shipped
        assert game["atomspace"] and game["atomspace"]["schema_version"] == 1


def test_ab_run_raw_moves_and_traces():
    with tempfile.TemporaryDirectory() as base:
        run = os.path.join(base, "abX")
        os.makedirs(run)
        tid = "pln-abcabc000002"
        # comparison.json (contrast pln vs plain) + raw arm jsonl with moves
        cmp = {"stats": {"pln": {"final": {"n_cities": 2, "n_units": 3, "n_techs": 1}},
                         "plain": {"final": {"n_cities": 1, "n_units": 2, "n_techs": 0}}},
               "trajectory": {"pln": [], "plain": []}, "overall": "pln",
               "verdict_wins": {"pln": 3, "plain": 1}, "arms": ["pln", "plain"],
               "contrast": ["pln", "plain"]}
        with open(os.path.join(run, "comparison.json"), "w", encoding="utf-8") as f:
            json.dump(cmp, f)
        _write_jsonl(os.path.join(run, "pln.jsonl"), [
            {"turn": 1, "advanced_to": 1, "metrics": {"n_cities": 1, "n_units": 2, "n_techs": 0},
             "moves": [_move(7, True, tid)], "recommendations": [{"entity": "Unit_7", "action": "Defend"}],
             "pln_trace_id": tid}])
        _write_jsonl(os.path.join(run, "plain.jsonl"), [
            {"turn": 1, "advanced_to": 1, "metrics": {"n_cities": 1, "n_units": 2, "n_techs": 0},
             "moves": [_move(9, True, None, pln=False)], "recommendations": []}])
        _trace_file(os.path.join(run, "traces"), tid)
        _snapshot_file(run)

        idx = _build_in(base)
        ab = next(r for r in idx["runs"] if r["type"] == "ab")
        assert ab["has_moves"]                          # raw path populated moves
        game = ab["games"][0]
        assert game["moves"][0]["pln"][0]["trace_id"] == tid
        assert tid in game["traces"]
        assert game["atomspace"]["schema_version"] == 1


def test_legacy_committed_only_run_still_indexes():
    with tempfile.TemporaryDirectory() as base:
        run = os.path.join(base, "abLegacy")
        os.makedirs(run)
        cmp = {"stats": {"pln": {"final": {"n_cities": 1, "n_units": 1, "n_techs": 0}},
                         "plain": {"final": {"n_cities": 1, "n_units": 1, "n_techs": 0}}},
               "trajectory": {"pln": [], "plain": []}, "overall": "tie",
               "verdict_wins": {"pln": 0, "plain": 0}}
        with open(os.path.join(run, "comparison.json"), "w", encoding="utf-8") as f:
            json.dump(cmp, f)
        idx = _build_in(base)
        ab = next(r for r in idx["runs"] if r["type"] == "ab")
        assert ab["has_moves"] is False                 # no raw jsonl -> aggregates only, no crash
        assert ab["games"][0].get("traces", {}) == {} or "traces" not in ab["games"][0]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} viz index tests passed".format(len(fns)))
