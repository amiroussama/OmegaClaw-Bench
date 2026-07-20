"""Host tests for the multi-hop PLN chaining fixpoint (reason.derive), no interpreter needed.

Drives the REAL ``reason.derive`` fixpoint against a MONKEYPATCHED ``reason._eval`` that returns
canned per-pass output, so we exercise: sentence parsing, multi-hop accumulation (an intermediate
predicate on pass N enables a recommendation on pass N+1), the hop cap, the confidence floor, and
fixpoint termination when a pass adds nothing new. Also asserts host-safety (``_eval`` raising ->
``[]``).
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

from freeciv import reason  # noqa: E402

_FACT = "((Inheritance City_1 Undefended) (stv 1.0 0.99))"


def _patch_eval(outputs):
    """Patch reason._eval to yield ``outputs`` (one per pass); return a restore callable + call log."""
    calls = []
    seq = list(outputs)

    def fake_eval(program, timeout):
        calls.append(program)
        return seq[len(calls) - 1] if len(calls) <= len(seq) else seq[-1]

    saved = reason._eval
    reason._eval = fake_eval
    return (lambda: setattr(reason, "_eval", saved)), calls


def test_parse_sentences_extracts_atom_and_truth():
    out = "noise [((Recommend City_1 Defend) (stv 0.9 0.71))] more (garbage (State City_2 X) (stv 0.8 0.5))"
    sents = reason._parse_sentences(out)
    stmts = {s for s, _, _ in sents}
    assert "(Recommend City_1 Defend)" in stmts
    # a (stv ...) that is not a top-level 2-tuple sentence is not picked up as a false positive
    assert all(0.0 <= f <= 1.0 and 0.0 <= c <= 1.0 for _, f, c in sents)


def test_multihop_accumulation_and_floor():
    # pass1: intermediate; pass2: another intermediate + a below-floor rec (pruned);
    # pass3: the chained recommendation.
    outputs = [
        "((State City_1 NeedsGarrison) (stv 0.9 0.76))",
        "((Priority City_1 Military) (stv 0.81 0.58))\n((Recommend City_1 Weak) (stv 0.9 0.2))",
        "((Recommend City_1 BuildDefender) (stv 0.73 0.38))",
    ]
    restore, calls = _patch_eval(outputs)
    try:
        recs, meta = reason.derive([_FACT], return_meta=True)
    finally:
        restore()
    assert recs == ["(Recommend City_1 BuildDefender)"], recs   # Weak pruned by the conf floor
    assert meta["hops"] == 3 and len(calls) == 3
    assert meta["n_conclusions"] == 1


def test_hop_cap_bounds_passes():
    # every pass yields a brand-new atom, so only the cap stops the fixpoint.
    outputs = ["((Recommend City_1 A%d) (stv 0.9 0.9))" % i for i in range(10)]
    restore, calls = _patch_eval(outputs)
    try:
        recs, meta = reason.derive([_FACT], max_hops=2, return_meta=True)
    finally:
        restore()
    assert len(calls) == 2 and meta["hops"] == 2
    assert sorted(recs) == ["(Recommend City_1 A0)", "(Recommend City_1 A1)"]


def test_fixpoint_terminates_when_no_new_atoms():
    # same single atom every pass -> added=False after pass 1 -> stop before the cap.
    restore, calls = _patch_eval(["((Recommend City_1 Defend) (stv 0.9 0.71))"] * 5)
    try:
        recs, meta = reason.derive([_FACT], max_hops=5, return_meta=True)
    finally:
        restore()
    assert recs == ["(Recommend City_1 Defend)"]
    assert len(calls) == 2 and meta["hops"] == 2  # pass1 adds it, pass2 finds nothing new -> stop


def test_conf_min_prunes_everything():
    restore, _ = _patch_eval(["((Recommend City_1 X) (stv 0.9 0.4))"])
    try:
        recs = reason.derive([_FACT], conf_min=0.5)
    finally:
        restore()
    assert recs == []


def test_eval_failure_is_host_safe():
    def boom(program, timeout):
        raise RuntimeError("no interpreter")
    saved = reason._eval
    reason._eval = boom
    try:
        assert reason.derive([_FACT]) == []
        assert reason.derive([_FACT], return_meta=True) == ([], {"hops": 0, "n_conclusions": 0, "n_atoms": 0})
    finally:
        reason._eval = saved


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} reason fixpoint tests passed".format(len(fns)))
