"""Parse the FreeCiv PLN rule set (``rules.metta``) into structured dicts, plus a host-safe
fact-vs-rule matcher.

This is the single parser for the ``((Implication <premise> (Recommend $x <Act>)) (stv f c))``
rule sentences. It supersedes the Inheritance-only regex that used to live in
``viz/dump_atoms.py``: it captures **all** rules — including the Evaluation-form Threatens
rule that is inert under the current lib_pln clauses — and it reads the per-rule
``; class: ... ; fires: ... ; rationale: ...`` annotations so downstream tools
(``mapping_inventory``, ``atomspace_export``, the viz) can render one consistent table.

Stdlib only, pure functions. ``benchmarks/freeciv/atoms.py`` provides the S-expression
parser we reuse for structural decoding.
"""

import os
import re

from . import atoms

_HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(_HERE, "rules.metta")

# A rule sentence begins with this literal; we balance-scan parentheses from here so the parser
# never depends on the interior shape (Inheritance vs Evaluation premise, nesting, etc.).
_RULE_START = "((Implication"


def _scan_balanced(text, start):
    """Return (sexpr, end_index) for the balanced parenthetical beginning at ``text[start]``.

    ``text[start]`` must be ``'('``. Returns ``(None, start)`` if the parens never balance
    (truncated / malformed) so callers can skip it.
    """
    depth = 0
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1], i + 1
        i += 1
    return None, start


def _parse_annotations(comment):
    """Parse a trailing ``; key: value ; key: value`` rule comment into a dict.

    Only recognizes the documented keys (class / fires / rationale); unknown keys are ignored.
    ``fires`` is coerced to a bool from yes/no/true/false.
    """
    meta = {}
    if not comment:
        return meta
    # comment is the text after ';' — split on ';' for multiple key:value segments.
    for seg in comment.split(";"):
        seg = seg.strip()
        if not seg or ":" not in seg:
            continue
        key, _, val = seg.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if key in ("class", "rationale"):
            meta[key] = val
        elif key == "fires":
            meta["fires"] = val.lower() in ("yes", "true", "1", "on")
    return meta


def _decode_rule(sexpr, annotations):
    """Decode one ``((Implication <premise> (Recommend $x <Act>)) (stv f c))`` sentence.

    Returns a structured dict, or None if the shape is not a recognizable Implication rule.
    """
    try:
        tree = atoms._parse_sexpr(sexpr)
    except ValueError:
        return None
    # tree == [ [Implication, <premise>, [Recommend, $x, <Act>]], [stv, f, c] ]
    if not (isinstance(tree, list) and len(tree) == 2 and isinstance(tree[0], list)):
        return None
    impl, stv = tree
    if len(impl) != 3 or impl[0] != "Implication":
        return None
    premise, conclusion = impl[1], impl[2]
    if not (isinstance(conclusion, list) and len(conclusion) == 3 and conclusion[0] == "Recommend"):
        return None
    if not (isinstance(stv, list) and stv[:1] == ["stv"] and len(stv) == 3):
        return None
    try:
        f, c = float(stv[1]), float(stv[2])
    except (TypeError, ValueError):
        return None

    action = conclusion[2]
    rule = {
        "statement": atoms._unparse(impl),
        "sentence": sexpr,
        "action": action,
        "f": f,
        "c": c,
        # annotations (default when the rule carries no comment yet)
        "rule_class": annotations.get("class", "heuristic"),
        "rationale": annotations.get("rationale", ""),
    }

    if isinstance(premise, list) and premise and premise[0] == "Inheritance" and len(premise) == 3:
        # (Inheritance $x <Attr>) -> fires under lib_pln word-form Modus Ponens
        rule["form"] = "inheritance"
        rule["attr"] = premise[2]
        rule["premise"] = atoms._unparse(premise)
        default_fires = True
    elif isinstance(premise, list) and premise and premise[0] == "Evaluation":
        # (Evaluation (Predicate P) (List ...)) -> inert under current lib_pln Evaluation clauses
        rule["form"] = "evaluation"
        pred = premise[1] if len(premise) > 1 and isinstance(premise[1], list) else []
        rule["predicate"] = pred[1] if len(pred) > 1 else None
        rule["premise"] = atoms._unparse(premise)
        default_fires = False
    else:
        rule["form"] = "other"
        rule["premise"] = atoms._unparse(premise) if isinstance(premise, list) else str(premise)
        default_fires = False

    # An explicit `fires:` annotation wins; otherwise fall back to the form default.
    rule["fires_on_host_engine"] = annotations.get("fires", default_fires)
    return rule


def parse_rules(text):
    """Parse every Implication rule sentence out of ``rules.metta`` text.

    Line-oriented so a trailing ``; ...`` annotation is attached to the rule on its line.
    Returns a list of rule dicts in file order.
    """
    rules = []
    for line in text.splitlines():
        idx = line.find(_RULE_START)
        if idx == -1:
            continue
        sexpr, end = _scan_balanced(line, idx)
        if sexpr is None:
            continue
        rest = line[end:]
        comment = rest.split(";", 1)[1] if ";" in rest else ""
        rule = _decode_rule(sexpr, _parse_annotations(comment))
        if rule is not None:
            rules.append(rule)
    return rules


def load_rules(path=None):
    """Parse the rule set from a file (default: the repo's ``rules.metta``)."""
    path = path or RULES_PATH
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return parse_rules(f.read())


def host_recommendations(facts, rules):
    """Match Inheritance facts against the firing rules -> recommendation edges.

    Host-safe stand-in for the real PLN engine (``reason.derive`` returns [] off-container):
    the same Inheritance-form Modus Ponens the engine performs in-container, so the
    fact->rule->recommendation graph stays populated on the host. Evaluation-form rules are
    inert (``fires_on_host_engine`` False) and are skipped, mirroring lib_pln.
    """
    by_attr = {r["attr"]: r for r in rules
               if r.get("form") == "inheritance" and r.get("fires_on_host_engine")}
    recs = []
    for f in facts:
        if f["pred"] != "Inheritance":
            continue
        rule = by_attr.get(f["obj"])
        if rule:
            recs.append({
                "entity": f["subj"],
                "action": rule["action"],
                "from_fact": atoms._statement(f),
                "rule": "Inheritance %s -> Recommend %s" % (f["obj"], rule["action"]),
                "engine_confirmed": False,
            })
    return recs
