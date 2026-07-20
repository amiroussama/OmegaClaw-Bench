"""Tests for the metric extraction fix + era-progression helpers (Issue #5).

Host-safe, deterministic. Covers: gold/score read from the per-player block (the runtime
shape), fallback to the summary blocks for the documented shape, tech_names, and the
turns_to_tech_counts / turns_to_milestones / era_progression / pln_quality helpers.
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

from freeciv import metrics, adapter  # noqa: E402

_SAMPLES = os.path.join(_BENCHMARKS, "freeciv", "samples")


# --- extraction fix --------------------------------------------------------

def test_gold_score_prefer_players_block_on_real_sample():
    p = os.path.join(_SAMPLES, "real_state_turn1.json")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8") as f:
        state = json.load(f)
    m = metrics.metrics_from_state(adapter.normalize_state(state))
    assert m["gold"] == 50, m["gold"]        # players[0].gold, not economic.gold (0)
    assert m["score"] == 0, m["score"]        # players[0].score
    assert m["n_units"] == 7 and m["n_cities"] == 0
    assert m["tech_names"] == ["Advanced Flight"], m["tech_names"]


def test_documented_shape_falls_back_to_summary_blocks():
    # players block has no gold/score -> fall back to economic.resources.gold + strategic.score
    state = {
        "format": "llm_optimized", "turn": 2, "player_perspective": 1,
        "economic": {"resources": {"gold": 12, "science": 3}},
        "strategic": {"score": 7},
        "players": {"1": {"id": 1, "name": "Rome"}},
        "units": {}, "cities": {}, "techs": {"player1": ["Pottery"]},
    }
    m = metrics.metrics_from_state(adapter.normalize_state(state))
    assert m["gold"] == 12 and m["score"] == 7 and m["science"] == 3


def test_negative_player_score_falls_back():
    # AI players report score -1 (unknown) -> must not be used
    state = {
        "format": "llm_optimized", "turn": 5, "player_perspective": 0,
        "players": {"0": {"id": 0, "score": -1, "gold": 3}},
        "strategic": {"score": 42}, "economic": {}, "units": {}, "cities": {}, "techs": {},
    }
    m = metrics.metrics_from_state(adapter.normalize_state(state))
    assert m["score"] == 42 and m["gold"] == 3


def test_science_research_points_fallback():
    state = {
        "format": "llm_optimized", "turn": 5, "player_perspective": 0,
        "players": {"0": {"id": 0}}, "economic": {},
        "strategic": {"tech_position": {"research_points": 9, "researched": ["A", "B"]}},
        "units": {}, "cities": {}, "techs": {},
    }
    m = metrics.metrics_from_state(adapter.normalize_state(state))
    assert m["science"] == 9
    assert m["n_techs"] == 2 and m["tech_names"] == ["A", "B"]


# --- era helpers -----------------------------------------------------------

_TRAJ = [
    {"turn": 1, "n_techs": 0, "tech_names": []},
    {"turn": 3, "n_techs": 2, "tech_names": ["Pottery", "Bronze Working"]},
    {"turn": 5, "n_techs": 4, "tech_names": ["Pottery", "Bronze Working", "Currency", "Writing"]},
]


def test_turns_to_tech_counts_with_censoring():
    out = metrics.turns_to_tech_counts(_TRAJ)
    assert out == {"2": 3, "4": 5, "6": None, "8": None}, out


def test_turns_to_tech_counts_unsorted_and_empty():
    shuffled = list(reversed(_TRAJ))
    assert metrics.turns_to_tech_counts(shuffled) == {"2": 3, "4": 5, "6": None, "8": None}
    assert metrics.turns_to_tech_counts([]) == {"2": None, "4": None, "6": None, "8": None}


def test_turns_to_milestones():
    out = metrics.turns_to_milestones(_TRAJ)
    assert out["Bronze Working"] == 3 and out["Currency"] == 5 and out["Writing"] == 5
    assert out["Monarchy"] is None
    # records lacking tech_names simply don't contribute
    assert metrics.turns_to_milestones([{"turn": 1, "n_techs": 3}])["Bronze Working"] is None


def test_era_progression_tech_rate():
    era = metrics.era_progression(_TRAJ)
    assert era["tech_rate"] == 0.8   # 4 techs / turn 5
    assert era["turns_to_tech_count"]["2"] == 3
    assert metrics.era_progression([])["tech_rate"] is None


# --- PLN quality -----------------------------------------------------------

def test_pln_quality():
    bundles = [{
        "moves": [
            {"actor": 102, "actor_kind": "unit_id", "pln_recommended": True, "valid": True},
            {"actor": 5, "actor_kind": "unit_id", "pln_recommended": True, "valid": False},
            {"actor": 9, "actor_kind": "unit_id", "pln_recommended": False, "valid": True},
        ],
        "recommendations": [{"entity": "Unit_102", "action": "Settle"},
                            {"entity": "Unit_999", "action": "Defend"}],
    }]
    q = metrics.pln_quality(bundles)
    assert q["pln_rec_proposed"] == 2 and q["pln_rec_valid"] == 1
    assert q["pln_action_success_rate"] == 0.5
    assert q["rec_adoption_rate"] == 0.5   # 1 of 2 recs (Unit_102) had a matching move


def test_pln_quality_empty():
    q = metrics.pln_quality([])
    assert q["pln_action_success_rate"] is None and q["rec_adoption_rate"] is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} metrics/era tests passed".format(len(fns)))
