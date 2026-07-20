"""Offline atomspace dump for the FreeCiv viz page.

Reconstructs the PLN player's per-turn atomspace from a captured game state — the atoms are
NOT persisted in run logs (only the *count* n_conclusions is), so we regenerate them through
the exact live pipeline: adapter.facts_from_state -> atoms -> rules.metta.

Recommendations come from OmegaClaw's real MeTTa/PLN engine (reason.derive) when it is available
(in-container). On a host without the interpreter derive returns [] (see reason.py), so we also
run a small host-side matcher over the Inheritance rules in rules.metta — the same three rules
that actually fire in-container (Undefended->Defend, LowFood->Food, Type_settlers->Settle; the
Evaluation-form Threatens rule is inert under current lib_pln, per rules.metta). This keeps the
fact->rule->recommendation graph populated on the host, and marks which recs the authentic
engine confirmed.

Emits benchmarks/freeciv/viz/data/atoms.json. Stdlib only.

Usage: python3 benchmarks/freeciv/viz/dump_atoms.py [--state PATH] [--out PATH]
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

_HERE = os.path.dirname(os.path.abspath(__file__))            # benchmarks/freeciv/viz
_FREECIV = os.path.dirname(_HERE)                             # benchmarks/freeciv
_BENCH = os.path.dirname(_FREECIV)                            # benchmarks
if _BENCH not in sys.path:
    sys.path.insert(0, _BENCH)

from freeciv import adapter, atoms, reason, rulesparse  # noqa: E402

_DEFAULT_STATE = os.path.join(_FREECIV, "samples", "real_state_turn1.json")


def _fact_rows(facts):
    """Attach the rendered statement + truth value to each adapter fact dict."""
    rows = []
    for f in facts:
        rows.append({
            "subj": f["subj"], "pred": f["pred"], "obj": f["obj"],
            "f": f["f"], "c": f["c"], "category": f["category"],
            "statement": atoms._statement(f),
            "stv": atoms._stv(f),
        })
    return rows


def dump(state_path):
    raw = json.load(open(state_path, encoding="utf-8"))
    norm = adapter.normalize_state(raw)
    facts = adapter.facts_from_state(norm)
    rules = rulesparse.load_rules()
    recs = rulesparse.host_recommendations(facts, rules)

    # Authentic engine (works in-container); annotate which host-matched recs it confirms.
    engine = reason.derive(atoms.sentences_from_facts(facts))
    engine_pairs = set()
    for r in engine:
        m = reason._REC_RE.search(r)
        if m:
            engine_pairs.add((m.group(1), m.group(2)))
    for rec in recs:
        rec["engine_confirmed"] = (rec["entity"], rec["action"]) in engine_pairs
    source = "derive" if engine_pairs else "host-fallback"

    return {
        "state_file": os.path.relpath(state_path, _BENCH),
        "turn": norm.get("turn"),
        "player_perspective": norm.get("player_perspective"),
        "facts": _fact_rows(facts),
        "rules": rules,
        "recommendations": recs,
        "source": source,
        "n_facts": len(facts),
        "n_recommendations": len(recs),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=_DEFAULT_STATE)
    ap.add_argument("--out", default=os.path.join(_HERE, "data", "atoms.json"))
    args = ap.parse_args()
    if not os.path.isfile(args.state):
        print("state file not found: %s" % args.state, file=sys.stderr)
        return 2
    payload = dump(args.state)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print("wrote %s — %d facts, %d recommendations (source=%s)" %
          (args.out, payload["n_facts"], payload["n_recommendations"], payload["source"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
