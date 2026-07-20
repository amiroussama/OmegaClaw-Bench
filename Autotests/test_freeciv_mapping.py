"""Tests for the AtomSpace mapping review workflow (Issue #6).

Host-safe and deterministic (no PeTTa/interpreter): the host-side rule matcher in
``rulesparse.host_recommendations`` stands in for ``reason.derive``. Covers:
  * MAPPING.md is regenerable and up to date (the CI drift gate);
  * every fact the adapter emits is documented in FACT_VOCABULARY, and vice-versa;
  * rule truth values obey the heuristic/law confidence conventions;
  * the end-to-end action-to-atom golden fixture (state -> fact -> rule -> rec -> action).
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

from freeciv import adapter, atoms, actions, rulesparse, mapping_inventory as mi  # noqa: E402
from freeciv.fixtures import FIXTURES  # noqa: E402

_SAMPLES = os.path.join(_BENCHMARKS, "freeciv", "samples")


def _all_states():
    states = [fx["state"] for fx in FIXTURES]
    for name in ("real_state_turn0.json", "real_state_turn1.json"):
        p = os.path.join(_SAMPLES, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                states.append(json.load(f))
    return states


def _all_facts():
    facts = []
    for st in _all_states():
        facts.extend(adapter.facts_from_state(adapter.normalize_state(st)))
    return facts


# --- MAPPING.md drift gate -------------------------------------------------

def test_mapping_md_up_to_date():
    """MAPPING.md must equal render_md() — regenerate with --write if this fails."""
    assert os.path.isfile(mi.MAPPING_MD), "docs/MAPPING.md missing — run mapping_inventory.py --write"
    with open(mi.MAPPING_MD, encoding="utf-8") as f:
        current = f.read()
    assert current == mi.render_md(), (
        "docs/MAPPING.md is stale — regenerate: "
        "python3 benchmarks/freeciv/mapping_inventory.py --write")


def test_render_md_is_deterministic():
    assert mi.render_md() == mi.render_md()


# --- vocabulary completeness (both directions) -----------------------------

def test_all_emitted_facts_in_vocabulary():
    undocumented = []
    for f in _all_facts():
        if mi.match_fact(f) is None:
            undocumented.append((f["category"], f["pred"], f["obj"]))
    assert not undocumented, "facts not documented in FACT_VOCABULARY: %s" % sorted(set(undocumented))


def test_vocabulary_fully_exercised():
    exercised = {id(mi.match_fact(f)) for f in _all_facts()}
    missing = [(e["category"], e["pred"], e["obj_match"]) for e in mi.FACT_VOCABULARY
               if id(e) not in exercised]
    assert not missing, "vocabulary entries never produced by any fixture/sample: %s" % missing


# --- rule confidence conventions -------------------------------------------

def test_rules_parse_and_confidence_classes():
    rules = rulesparse.load_rules()
    assert len(rules) == 4, "expected 4 rules in rules.metta, got %d" % len(rules)
    for r in rules:
        assert 0.0 <= r["f"] <= 1.0 and 0.0 <= r["c"] <= 1.0, r
        if r["rule_class"] == "law":
            assert (r["f"], r["c"]) == adapter.CONF_OBSERVED, ("law must be certain", r)
        else:  # heuristic: must NOT claim certainty
            assert r["f"] < 1.0 or r["c"] < 0.99, ("heuristic claims certainty", r)


def test_evaluation_rule_is_inert_inheritance_rules_fire():
    by_form = {}
    for r in rulesparse.load_rules():
        by_form.setdefault(r["form"], []).append(r)
    assert all(r["fires_on_host_engine"] for r in by_form.get("inheritance", []))
    assert all(not r["fires_on_host_engine"] for r in by_form.get("evaluation", []))


# --- end-to-end action-to-atom golden fixture ------------------------------

def test_action_to_atom_golden_fixture():
    fx = next(f for f in FIXTURES if f["id"] == "pln_settler_to_found_city")
    st = fx["state"]
    exp = fx["expected"]

    facts = adapter.facts_from_state(adapter.normalize_state(st))
    stmts, sents = atoms.atoms_from_facts(facts), atoms.sentences_from_facts(facts)
    atoms.assert_well_formed(stmts, sents)  # every atom/sentence well-formed

    for want in exp["atoms_subset"]:
        assert want in stmts, (want, stmts)

    recs = rulesparse.host_recommendations(facts, rulesparse.load_rules())
    got = sorted((r["entity"], r["action"]) for r in recs)
    want = sorted((r["entity"], r["action"]) for r in exp["recommendations"])
    assert got == want, (got, want)

    # the recommended action validates, and its actor links back to the recommendation entity
    ra = exp["recommended_action"]
    assert actions.validate_action(ra, st).is_valid, ra
    actor_token = adapter._tok("Unit", ra["unit_id"])
    assert actor_token in {r["entity"] for r in exp["recommendations"]}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("\nAll {} mapping tests passed".format(len(fns)))
