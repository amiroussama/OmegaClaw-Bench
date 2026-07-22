"""AtomSpace inspector/export for benchmark runs (Issue #2).

Emits a readable, reviewable snapshot of the exact atoms PLN reasons over for a game state:
observed/derived facts, the asserted rules, and the inferred recommendations — each with its
truth value and provenance — plus a lint pass that flags suspicious conditions (missing
category facts, duplicate/conflicting atoms, game-law rules with non-absolute confidence,
LLM-induced vs hardcoded atoms). The snapshot is deterministic (NO timestamps) so it can be
committed as a golden artifact and diffed in review.

Reuses the live pipeline: ``adapter`` (facts + coverage), ``atoms`` (rendering + validation),
``rulesparse`` (rules + host matcher), ``reason.derive`` (the real engine when in-container).
Stdlib only.

CLI:
    python3 benchmarks/freeciv/atomspace_export.py [--state PATH] [--out PATH] [--pretty]
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

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BENCH = os.path.dirname(_HERE)
if _BENCH not in sys.path:
    sys.path.insert(0, _BENCH)

from freeciv import adapter, atoms, rulesparse, reason  # noqa: E402

SCHEMA_VERSION = 1
_DEFAULT_STATE = os.path.join(_HERE, "samples", "real_state_turn1.json")

# provenance labels keyed off the adapter's hardcoded truth constants
_OBSERVED = tuple(adapter.CONF_OBSERVED)
_DERIVED = tuple(adapter.CONF_DERIVED)


def _provenance(f, c):
    if (f, c) == _OBSERVED:
        return "observed"
    if (f, c) == _DERIVED:
        return "derived-heuristic"
    return "unknown"


def _fact_atoms(facts):
    """Fact atoms with stable ids (f001..) in the adapter's deterministic sort order."""
    rows = []
    for i, f in enumerate(facts, 1):
        rows.append({
            "id": "f%03d" % i,
            "kind": "fact",
            "type": f["pred"],
            "statement": atoms._statement(f),
            "sentence": "({} {})".format(atoms._statement(f), atoms._stv(f)),
            "stv": {"f": f["f"], "c": f["c"]},
            "category": f["category"],
            "provenance": _provenance(f["f"], f["c"]),
            "origin": "adapter",
            "subj": f["subj"], "pred": f["pred"], "obj": f["obj"],
        })
    return rows


def _rule_atoms(rules):
    """Rule atoms with stable ids (r001..) in rules.metta file order."""
    rows = []
    for i, r in enumerate(rules, 1):
        rows.append({
            "id": "r%03d" % i,
            "kind": "rule",
            "type": "Implication",
            "statement": r["statement"],
            "stv": {"f": r["f"], "c": r["c"]},
            "category": "rule",
            "provenance": "rule",
            "origin": "rules.metta",
            "form": r.get("form"),
            "action": r.get("action"),
            "fires_on_host_engine": r.get("fires_on_host_engine", False),
            "is_game_law": r.get("rule_class") == "law",
        })
    return rows


def _inferred_atoms(recs, source, fact_by_stmt, rule_by_action):
    """Inferred recommendation atoms (d001..), sorted by (entity, action), linked to premises.

    ``recs`` is the host-matcher edge list ([{entity, action, from_fact, ...}]) when we have
    structured edges, or a bare ``["(Recommend E A)", ...]`` list from the engine.
    """
    edges = _rec_edges(recs)
    rows = []
    for i, e in enumerate(sorted(edges, key=lambda x: (x["entity"], x["action"])), 1):
        premises = []
        fid = fact_by_stmt.get(e.get("from_fact"))
        if fid:
            premises.append(fid)
        rid = rule_by_action.get(e["action"])
        if rid:
            premises.append(rid)
        rows.append({
            "id": "d%03d" % i,
            "kind": "inferred",
            "type": "Recommend",
            "statement": "(Recommend {} {})".format(e["entity"], e["action"]),
            "stv": None,
            "category": "recommendation",
            "provenance": "inferred-pln",
            "origin": source,
            "premises": premises,
            "trace_id": None,
        })
    return rows


def _rec_edges(recs):
    """Normalize recs into edge dicts with entity/action (+ from_fact when available)."""
    edges = []
    for r in recs or []:
        if isinstance(r, dict) and "entity" in r:
            edges.append(r)
        elif isinstance(r, str):
            m = reason._REC_RE.search(r)
            if m:
                edges.append({"entity": m.group(1), "action": m.group(2), "from_fact": None})
    return edges


def snapshot_from_state(raw_state, state_file=None, recs=None):
    """Build a deterministic AtomSpace snapshot dict for a raw llm_optimized state.

    ``recs`` (optional): live recommendations from the sim's ``reason.derive`` — when given the
    snapshot records ``recommendation_source: "derive"`` without re-running the engine. Otherwise
    the engine is tried (in-container) and falls back to the host-side rule matcher.
    """
    norm = adapter.normalize_state(raw_state)
    facts = adapter.facts_from_state(norm)
    rules = rulesparse.load_rules()

    # recommendations: caller-supplied engine recs > engine call > host-side matcher
    if recs is not None:
        source = "derive"
        rec_list = recs
    else:
        engine = reason.derive(atoms.sentences_from_facts(facts))
        if engine:
            source, rec_list = "derive", engine
        else:
            source, rec_list = "host-fallback", rulesparse.host_recommendations(facts, rules)

    fact_rows = _fact_atoms(facts)
    rule_rows = _rule_atoms(rules)
    fact_by_stmt = {r["statement"]: r["id"] for r in fact_rows}
    rule_by_action = {r["action"]: r["id"] for r in rule_rows if r.get("action")}
    inferred_rows = _inferred_atoms(rec_list, source, fact_by_stmt, rule_by_action)

    all_atoms = fact_rows + rule_rows + inferred_rows
    groups = {}
    for a in all_atoms:
        groups.setdefault(a["provenance"], []).append(a["id"])

    snap = {
        "schema_version": SCHEMA_VERSION,
        "generated_from": {
            "state_file": state_file,
            "state_hash": adapter.state_hash(raw_state),
            "turn": norm.get("turn"),
            "player_perspective": norm.get("player_perspective"),
        },
        "engine": {"recommendation_source": source},
        "atoms": all_atoms,
        "groups": {k: groups[k] for k in sorted(groups)},
        "counts": {k: len(groups[k]) for k in sorted(groups)},
    }
    snap["lint"] = lint_snapshot(snap, raw_state)
    return snap


# --------------------------------------------------------------------------- lint

def _finding(check, severity, message, atom_ids=None):
    return {"check": check, "severity": severity, "message": message, "atom_ids": atom_ids or []}


def lint_snapshot(snapshot, raw_state=None):
    """Flag suspicious conditions. Returns {ok, findings:[{check,severity,message,atom_ids}]}."""
    findings = []
    atoms_ = snapshot["atoms"]
    facts = [a for a in atoms_ if a["kind"] == "fact"]
    rules = [a for a in atoms_ if a["kind"] == "rule"]
    inferred = [a for a in atoms_ if a["kind"] == "inferred"]
    ids = {a["id"] for a in atoms_}

    # 1) missing category facts (reuse adapter.coverage)
    if raw_state is not None:
        missing = adapter.coverage(raw_state).get("missing", [])
        if missing:
            findings.append(_finding("missing-category-facts", "error",
                                     "present state categories with no facts: %s" % ", ".join(missing)))

    # 2/3) duplicate vs conflicting statements
    by_stmt = {}
    for a in facts:
        by_stmt.setdefault(a["statement"], []).append(a)
    for stmt, group in by_stmt.items():
        if len(group) < 2:
            continue
        stvs = {(g["stv"]["f"], g["stv"]["c"]) for g in group}
        gids = [g["id"] for g in group]
        if len(stvs) == 1:
            findings.append(_finding("duplicate-statement", "warn",
                                     "%s appears %d times" % (stmt, len(group)), gids))
        else:
            findings.append(_finding("conflicting-truth", "error",
                                     "%s has conflicting truth values %s" % (stmt, sorted(stvs)), gids))

    # 4) non-standard confidence on facts
    ns = [a["id"] for a in facts if a["provenance"] == "unknown"]
    if ns:
        findings.append(_finding("nonstandard-confidence", "warn",
                                 "facts with non-standard truth (not observed/derived)", ns))

    # 5) game-law confidence + info that all rules are heuristics
    for a in rules:
        if a.get("is_game_law") and a["stv"]["c"] != 1.0:
            findings.append(_finding("game-law-confidence", "error",
                                     "game-law rule %s has confidence != 1.0" % a["statement"], [a["id"]]))
    if rules and not any(a.get("is_game_law") for a in rules):
        findings.append(_finding("game-law-confidence", "info",
                                 "no game-world-law atoms — all %d rules are strategic heuristics "
                                 "(legality is enforced procedurally by validate_action)" % len(rules)))

    # 6) malformed atoms / stv out of range. Only *fact* atoms use the standard PLN link
    # vocabulary that validate_atom knows; Recommend/Implication atoms are a separate vocabulary,
    # so we structurally validate facts and range-check every truth value.
    bad = []
    for a in atoms_:
        stv = a.get("stv")
        if stv and not (0.0 <= stv["f"] <= 1.0 and 0.0 <= stv["c"] <= 1.0):
            bad.append(a["id"])
        if a["kind"] == "fact" and atoms.validate_atom(a["statement"]) is not None:
            bad.append(a["id"])
    if bad:
        findings.append(_finding("malformed-atom", "error", "atoms failing validation", sorted(set(bad))))

    # 7) inert rules (present, not firing on the host engine)
    inert = [a["id"] for a in rules if not a.get("fires_on_host_engine")]
    if inert:
        findings.append(_finding("inert-rule", "info",
                                 "rules that do not fire under the current host engine", inert))

    # 8) LLM-origin atoms (induction vs hardcoded)
    llm = [a["id"] for a in atoms_ if str(a.get("origin", "")).startswith("llm")]
    if llm:
        findings.append(_finding("llm-origin-atoms", "info", "LLM-induced (not hardcoded) atoms", llm))

    # 9) dangling inferences
    dangling = []
    for a in inferred:
        prem = a.get("premises") or []
        if not prem and not a.get("trace_id"):
            dangling.append(a["id"])
        elif any(p not in ids for p in prem):
            dangling.append(a["id"])
    if dangling:
        findings.append(_finding("dangling-inference", "error",
                                 "inferred atoms with missing/absent premises", dangling))

    ok = not any(f["severity"] == "error" for f in findings)
    return {"ok": ok, "findings": findings}


# --------------------------------------------------------------------------- write helpers

def write_snapshot(snapshot, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, sort_keys=True)
    return path


def write_run_snapshot(out_dir, raw_state, recs, turn):
    """Per-run artifact hook for the sims: write atomspace_turn<first>.json once + refresh latest.

    Best-effort — callers wrap in try/except; returns the latest path or None on empty state.
    """
    if not raw_state:
        return None
    snap = snapshot_from_state(raw_state, recs=recs)
    d = os.path.join(out_dir, "")
    latest = os.path.join(out_dir, "atomspace_latest.json")
    write_snapshot(snap, latest)
    first = os.path.join(out_dir, "atomspace_turn%s.json" % turn)
    if not os.path.isfile(first):
        write_snapshot(snap, first)
    return latest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", default=_DEFAULT_STATE)
    ap.add_argument("--out")
    ap.add_argument("--pretty", action="store_true", help="print a human summary to stdout")
    args = ap.parse_args(argv)
    if not os.path.isfile(args.state):
        print("state file not found: %s" % args.state, file=sys.stderr)
        return 2
    raw = json.load(open(args.state, encoding="utf-8"))
    snap = snapshot_from_state(raw, state_file=os.path.relpath(args.state, _BENCH))
    if args.out:
        write_snapshot(snap, args.out)
        print("wrote %s" % args.out)
    if args.pretty or not args.out:
        print("AtomSpace snapshot — turn %s, source=%s" %
              (snap["generated_from"]["turn"], snap["engine"]["recommendation_source"]))
        print("counts: %s" % snap["counts"])
        print("lint: %s (%d findings)" % ("OK" if snap["lint"]["ok"] else "ISSUES",
                                          len(snap["lint"]["findings"])))
        for f in snap["lint"]["findings"]:
            print("  [%s] %s: %s" % (f["severity"], f["check"], f["message"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
