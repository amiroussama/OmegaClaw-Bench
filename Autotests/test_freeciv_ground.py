"""Host tests for grounding abstract PLN recommendations into concrete legal actions.

For every FreeCiv fixture state, grounds a battery of recommendations and asserts that ANY action
``ground.ground`` returns validates via ``actions.validate_action`` (the 0%-illegal invariant),
that foreign/unknown entities and unparseable recs yield None, and that grounding is deterministic.
No interpreter/LLM/Docker.
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

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BENCH = os.path.join(_REPO_ROOT, "benchmarks")
if _BENCH not in sys.path:
    sys.path.insert(0, _BENCH)

from freeciv import adapter, actions, ground  # noqa: E402
from freeciv.fixtures import FIXTURES  # noqa: E402

# The full recommendation vocabulary grounding must handle (city- and unit-targeted).
_VERBS = ("Defend", "BuildDefender", "Food", "Irrigate", "Settle", "FoundCity", "Retreat")


def _recs_for_state(norm):
    """Build (Recommend <entity> <verb>) strings over every owned entity × verb."""
    pid = norm.get("player_perspective")
    recs = []
    for c in norm.get("cities", []):
        if c.get("owner") == pid:
            recs += ["(Recommend City_%s %s)" % (c["id"], v) for v in _VERBS]
    for u in norm.get("units", []):
        if u.get("owner") == pid:
            recs += ["(Recommend Unit_%s %s)" % (u["id"], v) for v in _VERBS]
    return recs


def test_every_grounded_action_is_legal():
    checked = 0
    for fx in FIXTURES:
        norm = adapter.normalize_state(fx["state"])
        for rec in _recs_for_state(norm):
            action = ground.ground(rec, norm)
            if action is None:
                continue
            checked += 1
            res = actions.validate_action(action, fx["state"])
            assert res.is_valid, ("grounded illegal action %r for %r in %s: %s"
                                  % (action, rec, fx["id"], res.error_message))
    assert checked > 0, "no recommendation grounded to a concrete action across all fixtures"


def test_settler_fixture_grounds_to_build_city():
    fx = next(f for f in FIXTURES if f["id"] == "pln_settler_to_found_city")
    norm = adapter.normalize_state(fx["state"])
    action = ground.ground("(Recommend Unit_301 Settle)", norm)
    assert action == {"type": "unit_build_city", "unit_id": 301}, action
    # the chain-endpoint verb grounds the same way
    assert ground.ground("(Recommend Unit_301 FoundCity)", norm)["type"] == "unit_build_city"


def test_undefended_city_grounds_to_defense():
    fx = next(f for f in FIXTURES if f["id"] == "undefended_city")
    norm = adapter.normalize_state(fx["state"])
    action = ground.ground("(Recommend City_2 Defend)", norm)
    assert action is not None and action["type"] in ("unit_fortify", "unit_move")
    assert actions.validate_action(action, fx["state"]).is_valid
    # BuildDefender (3-hop chain endpoint) grounds to the same kind of concrete action
    assert ground.ground("(Recommend City_2 BuildDefender)", norm) is not None


def test_worker_fixture_food_grounds_to_irrigation():
    fx = next(f for f in FIXTURES if f["id"] == "worker_improvement")
    norm = adapter.normalize_state(fx["state"])
    action = ground.ground("(Recommend City_1 Food)", norm)
    assert action == {"type": "unit_build_irrigation", "unit_id": 9}, action


def test_foreign_and_bad_entities_return_none():
    fx = next(f for f in FIXTURES if f["id"] == "undefended_city")
    norm = adapter.normalize_state(fx["state"])
    assert ground.ground("(Recommend City_999 Defend)", norm) is None      # no such city
    assert ground.ground("(Recommend Unit_30 Settle)", norm) is None       # enemy unit / not owned
    assert ground.ground("(Recommend $c Defend)", norm) is None            # template, not concrete
    assert ground.ground("garbage", norm) is None
    assert ground.ground("(Recommend City_2 Teleport)", norm) is None      # unknown verb


def test_grounding_is_deterministic():
    fx = next(f for f in FIXTURES if f["id"] == "undefended_city")
    norm = adapter.normalize_state(fx["state"])
    a = ground.ground("(Recommend City_2 Defend)", norm)
    b = ground.ground("(Recommend City_2 Defend)", norm)
    assert a == b


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} grounding tests passed".format(len(fns)))
