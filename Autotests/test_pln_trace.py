"""Tests for the reusable PLN trace module (Issue #1) and reason.derive_traced.

Host-safe: the trace module (src/pln_trace.py) is pure stdlib; reason.derive_traced is driven
against a monkeypatched reason._eval so no interpreter is needed. Covers the trace container
(JSON round-trip, save/load, render/explain), the known-inference demo, and that derive_traced
records the attempt even when the interpreter is unavailable.
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
_SRC = os.path.join(_REPO_ROOT, "src")
_BENCH = os.path.join(_REPO_ROOT, "benchmarks")
for _p in (_SRC, _BENCH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pln_trace  # noqa: E402
from pln_trace import PlnTrace  # noqa: E402
from freeciv import reason  # noqa: E402

_FACT = "((Inheritance City_1 Undefended) (stv 1.0 0.99))"


# --- trace container -------------------------------------------------------

def test_parse_stv_and_normalize_vars():
    assert pln_trace.parse_stv("(Recommend City_1 Defend) (stv 0.9 0.71)") == {
        "strength": 0.9, "confidence": 0.71}
    assert pln_trace.parse_stv("no truth here") is None
    assert pln_trace.normalize_vars("(Recommend $c#37 Defend)") == "(Recommend $c Defend)"


def test_trace_json_roundtrip_and_save_load():
    t = PlnTrace("recommend-for", facts=[_FACT], context={"turn": 3})
    t.add_hop(1, [{"atom": "(Recommend City_1 Defend)", "strength": 0.9, "confidence": 0.71, "new": True}])
    t.set_conclusions([{"atom": "(Recommend City_1 Defend)", "strength": 0.9, "confidence": 0.71,
                        "rule_id": "recommend-defend"}])
    t.finish(["(Recommend City_1 Defend)"], latency_ms=100)

    d = t.to_dict()
    assert d["schema"] == "pln-trace/v1"
    t2 = PlnTrace.from_dict(json.loads(t.to_json()))
    assert t2.to_dict() == d   # lossless round-trip

    with tempfile.TemporaryDirectory() as td:
        path = t.save(td)
        assert os.path.isfile(path)
        loaded = PlnTrace.load(td, t.trace_id)
        assert loaded.to_dict() == d


def test_render_text_and_explain_known_inference():
    t = PlnTrace("recommend-for", facts=[_FACT])
    t.add_hop(1, [{"atom": "(Recommend City_1 Defend)", "strength": 0.9, "confidence": 0.7128, "new": True}])
    t.set_conclusions([{"atom": "(Recommend City_1 Defend)", "strength": 0.9, "confidence": 0.7128,
                        "rule_id": "recommend-defend"}])
    t.finish(["(Recommend City_1 Defend)"])
    text = t.render_text()
    assert "Recommend City_1 Defend" in text and "stv 0.900/0.713" in text
    assert "recommend-defend" in text
    exp = t.explain()
    assert "Recommend City_1 Defend" in exp and "hop" in exp


def test_explain_variants():
    ua = PlnTrace("q", facts=[_FACT]).finish([], status="interpreter_unavailable")
    assert "unavailable" in ua.explain()
    empty = PlnTrace("q", facts=[_FACT]).finish([], status="no_conclusions")
    assert "No PLN conclusions" in empty.explain()


def test_demo_runs():
    pln_trace._demo()  # must not raise


# --- reason.derive_traced --------------------------------------------------

def _patch_eval(fn):
    saved = reason._eval
    reason._eval = fn
    return lambda: setattr(reason, "_eval", saved)


def test_derive_traced_records_derivation():
    restore = _patch_eval(lambda program, timeout: "((Recommend City_1 Defend) (stv 0.9 0.71))")
    try:
        recs, trace = reason.derive_traced([_FACT], context={"turn": 6, "arm": "pln"})
    finally:
        restore()
    assert recs == ["(Recommend City_1 Defend)"]
    assert trace is not None and trace.status == "ok"
    assert trace.facts == [_FACT]
    assert trace.engine.get("available") is True
    concl = {c["atom"]: c for c in trace.conclusions}
    assert "(Recommend City_1 Defend)" in concl
    assert concl["(Recommend City_1 Defend)"]["rule_id"] == "recommend-defend"
    assert concl["(Recommend City_1 Defend)"]["stv"] == {"strength": 0.9, "confidence": 0.71}
    assert len(trace.hops) >= 1


def test_derive_traced_interpreter_unavailable_records_attempt():
    def boom(program, timeout):
        raise RuntimeError("no interpreter")
    restore = _patch_eval(boom)
    try:
        recs, trace = reason.derive_traced([_FACT], context={"turn": 1})
    finally:
        restore()
    assert recs == []
    assert trace is not None
    assert trace.status == "interpreter_unavailable"
    assert trace.facts == [_FACT]                 # attempt recorded
    assert trace.engine.get("available") is False
    assert trace.error


def test_derive_traced_empty_facts():
    recs, trace = reason.derive_traced([])
    assert recs == [] and trace.status == "no_conclusions"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} PLN trace tests passed".format(len(fns)))
