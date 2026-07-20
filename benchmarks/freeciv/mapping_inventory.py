"""Render the FreeCiv AtomSpace mapping into a deterministic, committed markdown inventory
(``docs/MAPPING.md``) so mapping changes are reviewable as a plain git diff.

The mapping the experts asked to review (Issue #6) is spread across three code sites:
  * ``adapter.facts_from_state`` — game state -> observed/derived fact atoms (the vocabulary);
  * ``rules.metta``             — strategic heuristic rules (parsed by ``rulesparse``);
  * ``schemas`` + ``actions``   — action shape/legality and the action<->atom entity linkage.

This module has a declarative ``FACT_VOCABULARY`` — one entry per emission site in
``facts_from_state`` — plus ``match_fact`` so a test can prove every emitted fact is documented
(and every documented form is exercised). ``render_md`` renders the whole thing with NO
timestamps, so re-running it only changes the file when the mapping actually changed.

Stdlib only. CLI:
    python3 benchmarks/freeciv/mapping_inventory.py            # print to stdout
    python3 benchmarks/freeciv/mapping_inventory.py --write     # write docs/MAPPING.md
    python3 benchmarks/freeciv/mapping_inventory.py --check      # exit 1 if MAPPING.md is stale
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BENCH = os.path.dirname(_HERE)
if _BENCH not in sys.path:
    sys.path.insert(0, _BENCH)

from freeciv import adapter, rulesparse, schemas  # noqa: E402

MAPPING_MD = os.path.join(_HERE, "docs", "MAPPING.md")

_OBS = "(stv {} {})".format(*adapter.CONF_OBSERVED)   # (stv 1.0 0.99)
_DER = "(stv {} {})".format(*adapter.CONF_DERIVED)     # (stv 1.0 0.9)


# One entry per fact-emission site in adapter.facts_from_state. ``kind`` is the atom class
# (Issue #6's four categories); ``obj_match`` drives match_fact: a string ending in ':'/'_'
# is a prefix, None is the catch-all for that (category, pred), otherwise an exact obj.
FACT_VOCABULARY = [
    # --- units ---
    {"category": "units", "pred": "Inheritance", "obj_match": "Type_", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Inheritance Unit_102 Type_settlers)", "source": "units[].type",
     "reading": "unit <id> is of the given type"},
    {"category": "units", "pred": "Evaluation", "obj_match": "At:", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Evaluation (Predicate At) (List Unit_102 14 42))", "source": "units[].x, units[].y",
     "reading": "unit <id> stands at map tile (x, y)"},
    {"category": "units", "pred": "Evaluation", "obj_match": "Has:", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Evaluation (Predicate Has) (List Player_0 Type_settlers 1))",
     "source": "tactical.unit_groups[type].count", "reading": "player owns N units of the given type"},
    # --- cities ---
    {"category": "cities", "pred": "Evaluation", "obj_match": "At:", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Evaluation (Predicate At) (List City_1 4 5))", "source": "cities[].x, cities[].y",
     "reading": "city <id> is located at map tile (x, y)"},
    {"category": "cities", "pred": "Evaluation", "obj_match": "Produces:", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Evaluation (Predicate Produces) (List City_1 Warriors))",
     "source": "cities[].production", "reading": "city <id> is currently producing the named item"},
    {"category": "cities", "pred": "Evaluation", "obj_match": "Population:", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Evaluation (Predicate Population) (List City_1 2))",
     "source": "cities[].population", "reading": "city <id> has the given population"},
    {"category": "cities", "pred": "Inheritance", "obj_match": "LowFood", "kind": "state-fact/derived",
     "stv": _DER, "example": "(Inheritance City_1 LowFood)", "source": "cities[].food_surplus < 0 (or growth_potential)",
     "reading": "city <id> has a food deficit / shrink risk (derived heuristic)"},
    # --- resources ---
    {"category": "resources", "pred": "Evaluation", "obj_match": "Gold:", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Evaluation (Predicate Gold) (List Player_0 50))",
     "source": "players[pid].gold or economic.resources.gold or economic.gold", "reading": "player's treasury gold"},
    {"category": "resources", "pred": "Evaluation", "obj_match": "Science:", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Evaluation (Predicate Science) (List Player_0 5))",
     "source": "economic.resources.science or economic.research", "reading": "player's science/research output"},
    # --- techs ---
    {"category": "techs", "pred": "Inheritance", "obj_match": "Researched", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Inheritance Tech_Pottery Researched)",
     "source": "strategic.tech_position.researched or techs.player<pid>", "reading": "the named tech has been researched"},
    # --- strategic ---
    {"category": "strategic", "pred": "Evaluation", "obj_match": "Score:", "kind": "state-fact/observed",
     "stv": _OBS, "example": "(Evaluation (Predicate Score) (List Player_0 45))",
     "source": "players[pid].score or strategic.victory_progress.current_score or strategic.score",
     "reading": "player's current game score"},
    {"category": "strategic", "pred": "Inheritance", "obj_match": None, "kind": "state-fact/derived",
     "stv": _DER, "example": "(Inheritance Player_0 Average)", "source": "strategic.relative_strength",
     "reading": "player's relative military/economic strength (derived label)"},
    # --- threats (derived inferences, not raw fields) ---
    {"category": "threats", "pred": "Evaluation", "obj_match": "Threatens:", "kind": "inferred/strategic",
     "stv": _DER, "example": "(Evaluation (Predicate Threatens) (List Enemy_30 Target_2))",
     "source": "tactical.immediate_threats[] or tactical.visible_threats[]",
     "reading": "an enemy unit threatens the given target (derived)"},
    {"category": "threats", "pred": "Inheritance", "obj_match": "Undefended", "kind": "inferred/strategic",
     "stv": _DER, "example": "(Inheritance City_2 Undefended)", "source": "owned city tile with no owned unit on it",
     "reading": "city <id> has no friendly unit standing on it (derived)"},
]


def match_fact(fact):
    """Return the FACT_VOCABULARY entry describing ``fact``, or None if undocumented."""
    catch_all = None
    for entry in FACT_VOCABULARY:
        if entry["category"] != fact["category"] or entry["pred"] != fact["pred"]:
            continue
        om = entry["obj_match"]
        if om is None:
            catch_all = catch_all or entry
            continue
        obj = fact["obj"]
        if om.endswith(":") or om.endswith("_"):
            if obj.startswith(om):
                return entry
        elif obj == om:
            return entry
    return catch_all


def _fires(rule):
    return "yes" if rule.get("fires_on_host_engine") else "no"


def render_md(rules=None):
    """Render the full mapping inventory as deterministic markdown (no timestamps)."""
    rules = rules if rules is not None else rulesparse.load_rules()
    L = []
    L.append("# FreeCiv AtomSpace mapping inventory")
    L.append("")
    L.append("<!-- GENERATED by benchmarks/freeciv/mapping_inventory.py — do NOT hand-edit. -->")
    L.append("<!-- Regenerate: python3 benchmarks/freeciv/mapping_inventory.py --write -->")
    L.append("")
    L.append("This file is the reviewable snapshot of how FreeCiv game state, rules, and actions map "
             "to PLN atoms. A change to `adapter.facts_from_state`, `rules.metta`, or the action "
             "schema changes this file — review the git diff. See `docs/atomspace-mapping.md` for "
             "the reviewer's guide and checklist.")
    L.append("")
    L.append("Confidence conventions: directly-observed facts carry `%s`; derived/heuristic facts "
             "carry `%s`; strategic heuristic rules carry frequency/confidence < 1.0; game-world "
             "laws (none today) would carry `%s`." % (_OBS, _DER, _OBS))
    L.append("")

    # 1. State facts
    L.append("## 1. Current-state facts")
    L.append("")
    L.append("| category | class | atom form | truth | source (state path) | reading |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for e in FACT_VOCABULARY:
        L.append("| {} | {} | `{}` | `{}` | `{}` | {} |".format(
            e["category"], e["kind"], e["example"], e["stv"], e["source"], e["reading"]))
    L.append("")

    # 2. Rules
    L.append("## 2. Strategic heuristic rules (`rules.metta`)")
    L.append("")
    L.append("Each rule is a PLN `Implication` (situation => recommended action) fired via lib_pln "
             "Modus Ponens. All are heuristics, not laws — see §3.")
    L.append("")
    L.append("| premise | => recommends | truth | class | fires | rationale |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for r in rules:
        concl = "Recommend <{}> {}".format(r["form"] == "evaluation" and "target" or "entity", r["action"])
        L.append("| `{}` | `{}` | `(stv {} {})` | {} | {} | {} |".format(
            r["premise"], concl, _num(r["f"]), _num(r["c"]), r["rule_class"], _fires(r), r["rationale"]))
    L.append("")

    # 3. Game-world laws
    L.append("## 3. Game-world laws")
    L.append("")
    L.append("**None are represented as atoms today.** Hard legality — a settler can found a city, "
             "you cannot move an enemy's unit, a move target must be on the map — is enforced "
             "procedurally by `actions.validate_action` (see §4), not asserted as PLN atoms. "
             "Convention if a law is ever added as an atom: it MUST carry truth `%s` (frequency 1, "
             "near-certain confidence). No strategic heuristic in §2 may claim frequency 1.0." % _OBS)
    L.append("")

    # 4. Actions
    L.append("## 4. Actions: preconditions & atom linkage")
    L.append("")
    L.append("Preconditions mirror `actions.validate_action` (checked in order: known type -> "
             "required fields -> entity exists & owned -> move target on-map -> server legal_actions). "
             "The actor of an action links to a recommendation entity via the token prefix below.")
    L.append("")
    L.append("| action type | required fields | actor | error codes |")
    L.append("| --- | --- | --- | --- |")
    err_by_kind = {
        "unit": "E201 unknown unit, E202 not owned",
        "city": "E203 unknown city, E204 not owned",
        "move": "E210 off-map",
        "": "",
    }
    for atype in sorted(schemas.ACTION_REQUIRED_FIELDS):
        req = ", ".join(schemas.ACTION_REQUIRED_FIELDS[atype]) or "(none)"
        if atype in schemas.UNIT_ACTIONS:
            actor = "unit_id (-> Unit_<id>)"
            errs = err_by_kind["unit"]
        elif atype in schemas.CITY_ACTIONS:
            actor = "city_id (-> City_<id>)"
            errs = err_by_kind["city"]
        elif atype == schemas.ACTION_TECH_RESEARCH:
            actor = "tech_id (-> Tech_<name>)"
            errs = ""
        else:
            actor = "(none)"
            errs = ""
        if atype == schemas.ACTION_UNIT_MOVE:
            errs = (errs + ", " + err_by_kind["move"]).strip(", ")
        L.append("| `{}` | {} | {} | {} |".format(atype, req, actor, errs or "—"))
    L.append("")
    L.append("Common shape errors: `E100` unknown action type, `E220` missing required field, "
             "`E230` not in server legal_actions.")
    L.append("")

    # 5. Recommendation vocabulary
    L.append("## 5. Recommendation vocabulary")
    L.append("")
    L.append("Rules derive `(Recommend <entity> <action>)` atoms. Current actions: " +
             ", ".join("`{}`".format(a) for a in sorted({r["action"] for r in rules})) + ".")
    L.append("")
    return "\n".join(L) + "\n"


def _num(x):
    x = float(x)
    return "{:.1f}".format(x) if x == int(x) else ("%.6f" % x).rstrip("0").rstrip(".")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write docs/MAPPING.md")
    ap.add_argument("--check", action="store_true", help="exit 1 if docs/MAPPING.md is stale")
    args = ap.parse_args(argv)
    md = render_md()

    if args.check:
        if not os.path.isfile(MAPPING_MD):
            print("MAPPING.md missing — run --write", file=sys.stderr)
            return 1
        current = open(MAPPING_MD, encoding="utf-8").read()
        if current != md:
            print("MAPPING.md is stale — regenerate with: "
                  "python3 benchmarks/freeciv/mapping_inventory.py --write", file=sys.stderr)
            return 1
        print("MAPPING.md is up to date")
        return 0

    if args.write:
        os.makedirs(os.path.dirname(MAPPING_MD), exist_ok=True)
        with open(MAPPING_MD, "w", encoding="utf-8") as f:
            f.write(md)
        print("wrote", os.path.relpath(MAPPING_MD, _BENCH))
        return 0

    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
