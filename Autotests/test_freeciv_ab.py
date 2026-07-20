"""Host tests for the PLN-vs-plain-LLM A/B harness (Issue #25 experiment).

No Docker / LLM / hyperon. Drives the REAL `ab_sim.run` per-turn loop against `MockProxyWS`
(from `freeciv.turn_cycle_fixtures`) with a fake `websockets` module and stubbed
`llm_agent.decide` / `reason.derive`, then asserts both arms advance turns and emit well-formed
metric lines. Also covers `metrics_from_state`, `render_plain` (same entities, no PLN atoms), and
that `reason.derive` is host-safe (returns [] without the interpreter).
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

import asyncio
import json
import os
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BENCH = os.path.join(_REPO_ROOT, "benchmarks")
_SRC = os.path.join(_REPO_ROOT, "src")
for _p in (_BENCH, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from freeciv import metrics, llm_agent, reason, adapter  # noqa: E402
from freeciv.turn_cycle_fixtures import MockProxyWS  # noqa: E402

_STATE = {
    "format": "llm_optimized", "turn": 1, "phase": "movement", "player_perspective": 1,
    "economic": {"resources": {"gold": 12, "science": 3}},
    "strategic": {"score": 7},
    "players": {"1": {"id": 1, "name": "Rome"}},
    "units": {"7": {"id": 7, "type": "Warrior", "owner": 1, "x": 3, "y": 4},
              "8": {"id": 8, "type": "settlers", "owner": 1, "x": 4, "y": 4}},
    "cities": {"1": {"id": 1, "name": "Rome", "owner": 1, "x": 3, "y": 4, "production": "Warriors"}},
    "techs": {"player1": ["Pottery", "Alphabet"]},
}


# --- metrics + rendering ---------------------------------------------------

def test_metrics_from_state():
    m = metrics.metrics_from_state(adapter.normalize_state(_STATE))
    assert m == {"turn": 1, "score": 7, "gold": 12, "science": 3,
                 "n_cities": 1, "n_units": 2, "n_techs": 2,
                 "tech_names": ["Alphabet", "Pottery"]}, m


def test_render_plain_has_entities_but_no_pln_atoms():
    txt = llm_agent.render_plain(adapter.normalize_state(_STATE))
    assert "unit 7" in txt and "city 1" in txt and "gold=12" in txt and "score=7" in txt
    assert "(Inheritance" not in txt and "(Evaluation" not in txt and "(stv" not in txt


def test_reason_derive_is_host_safe():
    prog = reason.build_program(["((Inheritance City_1 Undefended) (stv 1.0 0.99))"])
    assert "recommend-for" in prog and "lib_pln" in prog
    # no interpreter on the host -> returns [] (never raises)
    assert reason.derive(["((Inheritance City_1 Undefended) (stv 1.0 0.99))"]) == []
    assert reason.format_for_llm([]) == ""
    assert "Defend" in reason.format_for_llm(["(Recommend City_1 Defend)"])


# --- ab_sim per-turn loop (mock proxy + stubs) -----------------------------

class _WS(MockProxyWS):
    async def close(self):
        return None


def _fake_websockets():
    import types
    mod = types.ModuleType("websockets")

    async def connect(*a, **k):
        return _WS(start_turn=1)

    mod.connect = connect
    mod.ConnectionClosed = type("ConnectionClosed", (Exception,), {})
    return mod


def _run_arm(arm, out_dir, monkey_reason=True):
    # inject fake websockets + stubs BEFORE importing ab_sim's run path
    sys.modules["websockets"] = _fake_websockets()
    import freeciv.ab_sim as ab_sim

    orig = {"have_key": ab_sim.llm_agent.have_key, "decide": ab_sim.llm_agent.decide,
            "derive": ab_sim.reason.derive}
    ab_sim.llm_agent.have_key = lambda: True
    ab_sim.llm_agent.decide = lambda ctx, units, **kw: (
        [{"type": "unit_fortify", "unit_id": 7}], {"prompt_chars": len(ctx), "llm_ms": 5, "error": None})
    if monkey_reason:
        def _fake_derive(facts, **kw):
            recs = ["(Recommend City_1 Defend)"]
            if kw.get("return_meta"):
                return recs, {"hops": 2, "n_conclusions": len(recs), "n_atoms": 1}
            return recs
        ab_sim.reason.derive = _fake_derive
    # fact-proposal is a live-only LLM call; force it host-safe (no key) for the fact arms.
    ab_sim.fact_proposer._KEY = ""
    # MockProxyWS.state() has no units by default -> _pregame would loop; give it our state
    _WS.state = lambda self: dict(_STATE, turn=self.turn)
    os.environ["FREECIV_GAME_ID"] = "ab_test_%s" % arm
    try:
        return asyncio.new_event_loop().run_until_complete(
            ab_sim.run(arm, seed=42, hours=1.0, max_turns=3, out_dir=out_dir))
    finally:
        ab_sim.llm_agent.have_key = orig["have_key"]
        ab_sim.llm_agent.decide = orig["decide"]
        ab_sim.reason.derive = orig["derive"]
        sys.modules.pop("websockets", None)


def _turn_rows(path):
    return [json.loads(x) for x in open(path, encoding="utf-8") if x.strip() and '"metrics"' in x]


def test_plain_arm_advances_and_logs():
    with tempfile.TemporaryDirectory() as d:
        rc = _run_arm("plain", d)
        assert rc == 0
        rows = _turn_rows(os.path.join(d, "plain.jsonl"))
        assert len(rows) >= 3
        advanced = [r["advanced_to"] for r in rows if r.get("advanced_to")]
        assert advanced == sorted(advanced) and len(set(advanced)) == len(advanced)  # monotonic
        assert all(r["submitted"] == 1 for r in rows)          # fortify validated + submitted
        assert all(r["n_conclusions"] == 0 for r in rows)      # plain arm: no reasoning
        assert os.path.isfile(os.path.join(d, "plain_summary.json"))


def test_pln_arm_includes_reasoning():
    with tempfile.TemporaryDirectory() as d:
        rc = _run_arm("pln", d)
        assert rc == 0
        rows = _turn_rows(os.path.join(d, "pln.jsonl"))
        assert len(rows) >= 3
        assert all(r["n_conclusions"] >= 1 for r in rows)      # pln arm: derived conclusions present


def test_facts_only_arm_has_facts_but_no_reasoning():
    with tempfile.TemporaryDirectory() as d:
        rc = _run_arm("facts-only", d)
        assert rc == 0
        rows = _turn_rows(os.path.join(d, "facts-only.jsonl"))
        assert len(rows) >= 3
        # facts arm gets the extra proposal call (0 facts host-side, no key) but NO PLN reasoning
        assert all(r["n_conclusions"] == 0 for r in rows)
        assert all(r["n_llm_facts"] == 0 for r in rows)        # no key on host -> best-effort []
        assert all("n_llm_facts" in r and "fact_llm_ms" in r for r in rows)


def test_facts_chaining_arm_includes_reasoning():
    with tempfile.TemporaryDirectory() as d:
        rc = _run_arm("facts+chaining", d)
        assert rc == 0
        rows = _turn_rows(os.path.join(d, "facts+chaining.jsonl"))
        assert len(rows) >= 3
        assert all(r["n_conclusions"] >= 1 for r in rows)      # chaining arm: derived conclusions


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} freeciv A/B tests passed".format(len(fns)))
