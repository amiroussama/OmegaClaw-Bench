"""Authentic MeTTa/PLN reasoning bridge for the A/B experiment.

`derive(fact_sentences)` runs OmegaClaw's REAL PLN engine (lib_pln, via the PeTTa interpreter) over
the turn's observed fact atoms + the FreeCiv rule set (`benchmarks/freeciv/rules.metta`) and returns
the derived recommendation atoms. Each `(|- fact rule)` fires lib_pln's Modus Ponens, so an observed
`((Inheritance City_1 Undefended) (stv 1.0 0.99))` + the Undefended rule derives
`((Recommend City_1 Defend) (stv ...))`.

This only works inside the omegaclaw container (PeTTa/hyperon is not on the host). On a host without
the interpreter, `derive` returns `[]` (best-effort) so importing this module never breaks anything.

Env overrides (finalized during the in-container spike):
- OMEGACLAW_METTA_CMD     interpreter command (default ``sh /PeTTa/run.sh``); the program file is
                          appended as the final arg.
- OMEGACLAW_METTA_CWD     working dir for the interpreter (default ``/PeTTa``).
- OMEGACLAW_REASON_IMPORTS override the import preamble (newline-separated MeTTa import lines).
- OMEGACLAW_REASON_DEBUG  truthy -> print the generated program + raw interpreter output to stderr.
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
import re
import shlex
import subprocess
import sys
import tempfile
import time

from . import atoms, rulesparse

_HERE = os.path.dirname(os.path.abspath(__file__))            # benchmarks/freeciv
_REPO = os.path.dirname(os.path.dirname(_HERE))               # repo root

# The reusable PLN trace module lives at <repo>/src (beside delegation.py).
_SRC = os.path.join(_REPO, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
try:
    from pln_trace import PlnTrace
except Exception:  # noqa: BLE001 - tracing is best-effort; never break reasoning
    PlnTrace = None

# Chaining bounds (env-overridable). The fixpoint runs at most HOP_CAP passes, and conclusions
# whose confidence has decayed below CONF_MIN are pruned (chained Modus Ponens decays c fast).
_HOP_CAP_DEFAULT = 3
_CONF_MIN_DEFAULT = 0.3

# Import preamble: replicate run.metta's setup so the `OmegaClaw-Core` library root is registered
# (lib_import provides `library`/`git-import!`; git-import! resolves to the LOCAL repos/ clone
# offline). Then pull in the reasoning libs + our rules. PLN word-form inference uses `|~`
# (lib_pln), not `|-` (arrow-form NAL) — see rules.metta.
_DEFAULT_IMPORTS = "\n".join([
    "!(import! &self (library lib_import))",
    '!(git-import! "https://github.com/asi-alliance/OmegaClaw-Core.git")',
    "!(import! &self (library OmegaClaw-Core lib_nal))",
    "!(import! &self (library OmegaClaw-Core lib_pln))",
    "!(import! &self (library OmegaClaw-Core ./benchmarks/freeciv/rules))",
])

# A derived recommendation atom: (Recommend <entity> <action>) [optionally followed by an stv].
_REC_RE = re.compile(r"\(Recommend\s+([^\s()]+)\s+([^\s()]+)\)")


def _debug():
    return (os.environ.get("OMEGACLAW_REASON_DEBUG") or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name, default):
    try:
        return max(1, int(os.environ.get(name, "")))
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        return float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def _imports():
    return os.environ.get("OMEGACLAW_REASON_IMPORTS") or _DEFAULT_IMPORTS


def build_program(fact_sentences):
    """Build the MeTTa program: imports + one (recommend-for <fact>) per observed fact."""
    lines = [_imports(), ""]
    for f in fact_sentences:
        lines.append("!(recommend-for {})".format(f))
    return "\n".join(lines) + "\n"


def _eval(program, timeout):
    """Run the PeTTa interpreter on `program`; return stdout (raises on failure)."""
    cmd = shlex.split(os.environ.get("OMEGACLAW_METTA_CMD", "sh /PeTTa/run.sh"))
    cwd = os.environ.get("OMEGACLAW_METTA_CWD", "/PeTTa")
    fd, path = tempfile.mkstemp(suffix=".metta", prefix="fc_reason_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(program)
        proc = subprocess.run(cmd + [path], cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if _debug():
            sys.stderr.write("=== reason program ===\n{}\n=== output ===\n{}\n".format(program, out))
        return out
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _balanced_groups(text):
    """Yield every top-level parenthesized substring of ``text`` (ignores non-paren noise/brackets)."""
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start:i + 1]
                start = None


def _sentence_of(node):
    """If ``node`` is a ``[<atom>, [stv, f, c]]`` sentence with f,c in [0,1], return
    ``(statement_str, f, c)``; else None."""
    if not (isinstance(node, list) and len(node) == 2 and isinstance(node[1], list)):
        return None
    stv = node[1]
    if stv[:1] != ["stv"] or len(stv) != 3:
        return None
    try:
        f, c = float(stv[1]), float(stv[2])
    except (TypeError, ValueError):
        return None
    if not (0.0 <= f <= 1.0 and 0.0 <= c <= 1.0):
        return None
    return (atoms._unparse(node[0]), f, c)


def _collect_sentences(node, out):
    """Recursively collect every ``[atom, [stv f c]]`` sentence anywhere in ``node``.

    The PeTTa interpreter wraps ``findall`` results in extra list layers (a one-result recommendation
    prints as ``(((Recommend City_1 Defend) (stv 0.9 0.71)))``), so we walk the whole parse tree
    rather than only matching the top level.
    """
    s = _sentence_of(node)
    if s is not None:
        out.append(s)
        return  # don't also recurse into a matched sentence's own subterms
    if isinstance(node, list):
        for child in node:
            _collect_sentences(child, out)


def _parse_sentences(out):
    """Parse interpreter output into a list of ``(statement_str, f, c)`` derived sentences.

    A derived sentence is ``(<atom> (stv f c))`` with f,c parseable floats in [0,1] — found at any
    nesting depth (the interpreter wraps results in extra parens). Non-matching text is skipped.
    """
    results = []
    for grp in _balanced_groups(out):
        try:
            tree = atoms._parse_sexpr(grp)
        except ValueError:
            continue
        _collect_sentences(tree, results)
    return results


def _head(statement):
    """The head constructor of an atom statement (``''`` if unparseable)."""
    try:
        tree = atoms._parse_sexpr(statement)
    except ValueError:
        return ""
    return tree[0] if isinstance(tree, list) and tree and isinstance(tree[0], str) else ""


def _recs_from_statements(statements):
    """Concrete (non-template) ``(Recommend entity action)`` atoms from a statement iterable."""
    seen, recs = set(), []
    for stmt in statements:
        m = _REC_RE.match(stmt) or _REC_RE.search(stmt)
        if not m:
            continue
        entity, action = m.group(1), m.group(2)
        # Skip ungrounded rule templates that leak from non-matching fact/rule pairings
        # (e.g. "(Recommend $c Defend)"): a real recommendation has a concrete entity.
        if entity.startswith("$") or action.startswith("$"):
            continue
        key = (entity, action)
        if key not in seen:
            seen.add(key)
            recs.append("(Recommend {} {})".format(entity, action))
    return recs


def _fixpoint(facts, timeout, max_hops, conf_min, trace=None):
    """Run the bounded multi-hop fixpoint. Returns (known, seed, hops, status, error).

    ``known`` maps statement -> (f, c) best-seen truth (seeded with the input facts). When a
    ``trace`` (PlnTrace) is given, each pass records its derived atoms with truth values.
    ``status`` is "ok", or "interpreter_unavailable"/"error" if the interpreter failed before any
    hop completed (host case: no PeTTa).
    """
    known = {}  # statement -> (f, c), best truth seen; seed with the input facts so chains compose
    for stmt, f, c in _parse_sentences("\n".join(facts)):
        known[stmt] = (f, c)
    seed = set(known)
    premises = list(facts)
    hops = 0
    status, error = "ok", None
    for _ in range(max_hops):
        try:
            out = _eval(build_program(premises), timeout)
        except Exception as e:  # noqa: BLE001 - reasoning is best-effort; never break the arm
            if hops == 0:
                status, error = "interpreter_unavailable", str(e)
            break
        hops += 1
        added = False
        hop_rows = []
        for stmt, f, c in _parse_sentences(out):
            if c < conf_min:
                continue
            prev = known.get(stmt)
            is_new = prev is None
            if prev is None:
                known[stmt] = (f, c)
                added = True
            elif c > prev[1]:
                known[stmt] = (f, c)
            if trace is not None:
                hop_rows.append({"atom": stmt, "strength": f, "confidence": c, "new": is_new})
        if trace is not None:
            trace.add_hop(len(premises), hop_rows)
        if not added:
            break
        # Next pass = the input facts (so first-hop rules keep firing) + only the derived
        # CUSTOM-head intermediates (State/Priority/Recommend/...). Re-feeding standard PLN links
        # (Inheritance/Implication/...) would recycle lib_pln's inversion/revision reflections of
        # the rules themselves and blow the premise set up combinatorially.
        premises = list(facts) + [
            "({} (stv {} {}))".format(stmt, atoms._fmt(f), atoms._fmt(c))
            for stmt, (f, c) in known.items()
            if stmt not in seed and _head(stmt) not in atoms._KNOWN_LINKS]
    return known, seed, hops, status, error


def derive(fact_sentences, timeout=30, max_hops=None, conf_min=None, return_meta=False):
    """Multi-hop PLN derivation over the observed facts (``[]`` / ``([], meta)`` on any failure).

    Bounded Python-driven fixpoint: each pass runs the interpreter over the current premise set,
    parses ALL derived ``(atom (stv f c))`` sentences, prunes those below ``conf_min``, adds the
    new ones back to the premises, and re-runs until no new atom is derived or ``max_hops`` passes
    have run. This composes intermediate-predicate rules into specific recommendations while a
    confidence floor bounds over-decayed chains.

    Returns the unique concrete ``(Recommend entity action)`` atoms. With ``return_meta=True`` also
    returns ``{"hops", "n_conclusions", "n_atoms"}`` for the per-turn metrics log.
    """
    max_hops = max_hops if max_hops is not None else _env_int("OMEGACLAW_REASON_HOPS", _HOP_CAP_DEFAULT)
    conf_min = conf_min if conf_min is not None else _env_float("OMEGACLAW_REASON_CONF_MIN", _CONF_MIN_DEFAULT)
    facts = [f.strip() for f in (fact_sentences or []) if f and f.strip()]
    if not facts:
        meta = {"hops": 0, "n_conclusions": 0, "n_atoms": 0}
        return ([], meta) if return_meta else []

    known, seed, hops, _status, _error = _fixpoint(facts, timeout, max_hops, conf_min)
    recs = _recs_from_statements(sorted(known))
    meta = {"hops": hops, "n_conclusions": len(recs),
            "n_atoms": len([s for s in known if s not in seed])}
    return (recs, meta) if return_meta else recs


_RULE_ACTIONS = None


def _rule_id_for_action(action):
    """Best-effort rule id for a derived Recommend action (None if no rule declares it)."""
    global _RULE_ACTIONS
    if _RULE_ACTIONS is None:
        try:
            _RULE_ACTIONS = {r["action"] for r in rulesparse.load_rules()}
        except Exception:  # noqa: BLE001
            _RULE_ACTIONS = set()
    return "recommend-" + action.lower() if action in _RULE_ACTIONS else None


def derive_traced(fact_sentences, timeout=30, max_hops=None, conf_min=None, context=None):
    """Like ``derive`` but also returns a structured ``PlnTrace`` (Issue #1/#3).

    Records the derivation proactively — the trace always captures the query, input facts, each
    inference hop (atoms + truth values), and the final recommendations, even when the interpreter
    is unavailable (host case -> status ``interpreter_unavailable`` with the attempt recorded).
    Never raises. Returns (recommendations, PlnTrace-or-None).
    """
    max_hops = max_hops if max_hops is not None else _env_int("OMEGACLAW_REASON_HOPS", _HOP_CAP_DEFAULT)
    conf_min = conf_min if conf_min is not None else _env_float("OMEGACLAW_REASON_CONF_MIN", _CONF_MIN_DEFAULT)
    facts = [f.strip() for f in (fact_sentences or []) if f and f.strip()]

    if PlnTrace is None:  # trace module unavailable -> fall back to plain derive
        return derive(facts, timeout, max_hops, conf_min), None

    engine = {"cmd": os.environ.get("OMEGACLAW_METTA_CMD", "sh /PeTTa/run.sh")}
    trace = PlnTrace(query="recommend-for", facts=facts, engine=engine, context=context or {})
    if not facts:
        trace.finish([], status="no_conclusions")
        return [], trace

    t0 = time.monotonic()
    known, _seed, _hops, status, error = _fixpoint(facts, timeout, max_hops, conf_min, trace=trace)
    latency_ms = round((time.monotonic() - t0) * 1000.0, 1)
    trace.engine["available"] = status != "interpreter_unavailable"
    trace.engine["latency_ms"] = latency_ms

    recs = _recs_from_statements(sorted(known))
    conclusions = []
    for stmt in sorted(known):
        m = _REC_RE.match(stmt) or _REC_RE.search(stmt)
        if not m:
            continue
        entity, action = m.group(1), m.group(2)
        if entity.startswith("$") or action.startswith("$"):
            continue
        f, c = known[stmt]
        conclusions.append({"atom": stmt, "strength": f, "confidence": c,
                            "rule_id": _rule_id_for_action(action)})
    trace.set_conclusions(conclusions)

    final_status = status if status in ("interpreter_unavailable", "error") else \
        ("ok" if recs else "no_conclusions")
    trace.finish(recs, status=final_status, error=error, latency_ms=latency_ms)
    return recs, trace


def format_facts_for_llm(fact_sentences, limit=40):
    """Render observed fact sentences as a compact premise block (empty string if none).

    Used by BOTH fact arms (``facts-only`` and ``facts+chaining``) so the ONLY difference between
    them is the PLN engine, not the observations shown to the LLM. Facts are shown as the symbolic
    premises the reasoner consumes, framed as context (not instructions).
    """
    facts = [f.strip() for f in (fact_sentences or []) if f and f.strip()]
    if not facts:
        return ""
    lines = ["OBSERVED FACTS (symbolic premises — context, not a to-do list):"]
    for s in facts[:limit]:
        lines.append("  - {}".format(s))
    if len(facts) > limit:
        lines.append("  ... (+%d more)" % (len(facts) - limit))
    return "\n".join(lines)


def format_for_llm(recommendations, grounded=None):
    """Render derived recommendations as a concise prompt block (empty string if none).

    Framed as OPTIONAL hints, NOT a checklist. The 2026-07-08 head-to-head duel showed the LLM
    treated a "recommended priorities this turn" list as exhaustive: it did exactly
    len(recommendations) actions and stopped (proposed == n_conclusions on 97-99% of turns, ~1.6-2.1
    actions/turn vs the plain arm's ~2.9), a compounding activity deficit that starved expansion.
    The wording below decouples the action budget from the recommendation count.

    ``grounded`` (optional) is a list parallel to ``recommendations`` of concrete action dicts (from
    ``ground.ground``) or None; when a grounding is present the specific, legality-checked action is
    shown alongside the abstract hint so the LLM can act on it precisely.
    """
    if not recommendations:
        return ""
    grounded = grounded or []
    lines = ["DERIVED (PLN reasoning) — optional strategic hints (NOT a to-do list):"]
    for i, r in enumerate(recommendations):
        m = _REC_RE.match(r)
        if not m:
            continue
        line = "  - {} → {}".format(m.group(1), m.group(2))
        g = grounded[i] if i < len(grounded) else None
        if g:
            from . import ground
            line += "  [suggested legal action: {}]".format(ground.format_action(g))
        lines.append(line)
    lines.append(
        "(Hints only — do NOT limit yourself to these. Still choose the FULL 1-3 actions using your "
        "own judgment, including expansion such as founding new cities with settlers, which the "
        "hints may omit.)")
    return "\n".join(lines)


if __name__ == "__main__":
    # Spike helper: derive from a captured state file, or from stdin fact lines.
    # Optional: `--trace-out DIR` saves the PlnTrace and prints its human-readable rendering
    # (the in-container demo path for Issue #1).
    import argparse
    import json
    sys.path.insert(0, os.path.dirname(_HERE))  # benchmarks (for the `freeciv` package)
    from freeciv import adapter, atoms  # noqa: E402

    ap = argparse.ArgumentParser()
    ap.add_argument("state", nargs="?", help="captured llm_optimized state JSON (else read stdin)")
    ap.add_argument("--trace-out", help="directory to save the PlnTrace JSON")
    args = ap.parse_args()

    if args.state:
        state = json.load(open(args.state, encoding="utf-8"))
        facts = atoms.sentences_from_facts(adapter.facts_from_state(adapter.normalize_state(state)))
    else:
        facts = [ln.strip() for ln in sys.stdin if ln.strip()]
    print("input facts: {}".format(len(facts)))

    if args.trace_out:
        recs, trace = derive_traced(facts, context={"source": args.state or "stdin"})
        print("\n" + trace.render_text())
        if trace is not None:
            path = trace.save(args.trace_out)
            print("\nsaved trace -> {}".format(path))
    else:
        recs = derive(facts)
        print("derived {} recommendation(s):".format(len(recs)))
        for r in recs:
            print("  ", r)
        print("\n" + (format_for_llm(recs) or "(none)"))
