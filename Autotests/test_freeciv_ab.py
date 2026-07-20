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


def _run_arm(arm, out_dir, monkey_reason=True, decide=None):
    # inject fake websockets + stubs BEFORE importing ab_sim's run path
    sys.modules["websockets"] = _fake_websockets()
    import freeciv.ab_sim as ab_sim

    orig = {"have_key": ab_sim.llm_agent.have_key, "decide": ab_sim.llm_agent.decide,
            "derive": ab_sim.reason.derive, "derive_traced": ab_sim.reason.derive_traced}
    ab_sim.llm_agent.have_key = lambda: True
    ab_sim.llm_agent.decide = decide or (lambda ctx, units, **kw: (
        [{"type": "unit_fortify", "unit_id": 7}], {"prompt_chars": len(ctx), "llm_ms": 5, "error": None}))
    if monkey_reason:
        def _fake_derive(facts, **kw):
            recs = ["(Recommend City_1 Defend)"]
            if kw.get("return_meta"):
                return recs, {"hops": 2, "n_conclusions": len(recs), "n_atoms": 1}
            return recs
        ab_sim.reason.derive = _fake_derive

        def _fake_derive_traced(facts, **kw):
            from pln_trace import PlnTrace
            recs = ["(Recommend City_1 Defend)"]
            t = PlnTrace("recommend-for", facts=facts, context=kw.get("context") or {})
            t.add_hop(len(facts), [{"atom": "(Recommend City_1 Defend)",
                                    "strength": 0.9, "confidence": 0.71, "new": True}])
            t.set_conclusions([{"atom": "(Recommend City_1 Defend)", "strength": 0.9,
                                "confidence": 0.71, "rule_id": "recommend-defend"}])
            t.finish(recs)
            return recs, t
        ab_sim.reason.derive_traced = _fake_derive_traced
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
        ab_sim.reason.derive_traced = orig["derive_traced"]
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


# --- proactive trace recording (Issue #3) ----------------------------------

def test_pln_moves_link_to_existing_traces():
    """Every pln-arm turn carries a pln_trace_id; each move's trace_id matches and the trace
    file exists under <out>/traces/ with matching recommendations (Issue #3 acceptance)."""
    from pln_trace import PlnTrace
    with tempfile.TemporaryDirectory() as d:
        assert _run_arm("pln", d) == 0
        rows = _turn_rows(os.path.join(d, "pln.jsonl"))
        assert len(rows) >= 3
        for r in rows:
            tid = r.get("pln_trace_id")
            assert tid, r
            # every move record points at the same turn trace_id
            for mv in r["moves"]:
                assert mv.get("trace_id") == tid, mv
            # the trace file exists and round-trips
            path = os.path.join(d, "traces", "%s.json" % tid)
            assert os.path.isfile(path), path
            tr = PlnTrace.load(os.path.join(d, "traces"), tid)
            assert tr.status in ("ok", "no_conclusions", "interpreter_unavailable")
            assert tr.recommendations == r["recommendations"] or \
                [c["atom"] for c in tr.conclusions]  # recs mirror the logged recommendations


def test_blocked_move_keeps_trace_and_reason():
    """An invalid action retains valid=False, a non-null error_code, and its trace_id."""
    # propose an off-map move (E210 off-map) so the pre-submit validator rejects it
    bad_decide = lambda ctx, units, **kw: (  # noqa: E731
        [{"type": "unit_move", "unit_id": 7, "dest_x": -5, "dest_y": -5}],
        {"prompt_chars": len(ctx), "llm_ms": 5, "error": None})
    with tempfile.TemporaryDirectory() as d:
        assert _run_arm("pln", d, decide=bad_decide) == 0
        rows = _turn_rows(os.path.join(d, "pln.jsonl"))
        assert rows
        for r in rows:
            assert r["blocked"] >= 1 and r["submitted"] == 0
            for mv in r["moves"]:
                assert mv["valid"] is False
                assert mv["error_code"] == "E210" and mv["error_message"]
                assert mv["trace_id"] == r["pln_trace_id"]   # blocked move keeps its trace


def test_plain_arm_has_no_trace_ids():
    with tempfile.TemporaryDirectory() as d:
        assert _run_arm("plain", d) == 0
        rows = _turn_rows(os.path.join(d, "plain.jsonl"))
        assert rows and all(r.get("pln_trace_id") is None for r in rows)
        for r in rows:
            assert all(mv.get("trace_id") is None for mv in r["moves"])
        assert not os.path.isdir(os.path.join(d, "traces"))
        assert not os.path.isfile(os.path.join(d, "atomspace_latest.json"))  # no snapshot either


def test_pln_arm_writes_atomspace_snapshot():
    """The PLN arm emits a per-run AtomSpace snapshot artifact (Issue #2)."""
    with tempfile.TemporaryDirectory() as d:
        assert _run_arm("pln", d) == 0
        snap_path = os.path.join(d, "atomspace_latest.json")
        assert os.path.isfile(snap_path)
        snap = json.loads(open(snap_path, encoding="utf-8").read())
        assert snap["schema_version"] == 1
        assert snap["counts"].get("observed", 0) > 0
        assert "lint" in snap and "findings" in snap["lint"]


def test_move_record_carries_error_code_and_trace_id():
    """Unit-level: _move_record accepts a ValidationResult and a bool (back-compat)."""
    from freeciv import duel_sim, actions
    st = {"player_perspective": 0, "units": {"7": {"id": 7, "owner": 0, "x": 1, "y": 1}},
          "cities": {}, "players": {}, "techs": {}, "economic": {}, "strategic": {}, "tactical": {}}
    bad = actions.validate_action({"type": "unit_move", "unit_id": 7, "dest_x": -1, "dest_y": 0}, st)
    na = actions.normalize_action({"type": "unit_move", "unit_id": 7, "dest_x": -1, "dest_y": 0})
    rec = duel_sim._move_record(na, bad, {"Unit_7"}, trace_id="pln-abc")
    assert rec["valid"] is False and rec["error_code"] == "E210" and rec["error_message"]
    assert rec["trace_id"] == "pln-abc" and rec["pln_recommended"] is True
    # back-compat: a bare bool still works (valid -> no error fields)
    ok = duel_sim._move_record(na, True, set())
    assert ok["valid"] is True and ok["error_code"] is None and ok["trace_id"] is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} freeciv A/B tests passed".format(len(fns)))
