"""LLM fact enrichment for the FreeCiv PLN A/B experiment (hybrid facts).

The deterministic adapter (``adapter.facts_from_state``) emits a small, high-confidence
(``c=0.99``) fact set: a few properties (``Undefended``/``LowFood``/``Type_settlers``) plus
observed relations. The 20-seed batch traced the null PLN result to *sparse* facts (~0.85
conclusions/turn), so this module adds a second, best-effort fact source: one LLM call per turn
that PROPOSES additional facts about the same state, validated and discounted to the ``llm``
confidence tier (``c=0.55``) before they ever reach the reasoner.

Design (locked decisions):
  * Hybrid — the deterministic ``c=0.99`` facts are ALWAYS kept; LLM facts are merged on top and
    lose the dedup tie to a duplicate observed fact (``atoms.sentences_from_facts`` keeps the
    higher-confidence truth value).
  * JSON schema, not raw atoms — the LLM returns ``{subj,pred,obj,f,c}`` dicts (adapter schema),
    which minimises malformed output vs. free-form s-expressions.
  * Best-effort — ANY error (no key, network, bad JSON, malformed facts) yields ``[]``; a fact
    proposal must never kill a turn. Determinism-critical paths (host tests, ``benchmark.py``)
    never call this — LLM facts live ONLY in the live sims.

Provider plumbing mirrors ``llm_agent`` (``provider_config.provider_entry(FREECIV_PROVIDER)`` +
the key from the env var it names), so both extra calls route through the same provider.
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
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))          # benchmarks/freeciv
_BENCH = os.path.dirname(_HERE)                             # benchmarks
_SRC = os.path.join(os.path.dirname(_BENCH), "src")         # src (for provider_config)
for _p in (_BENCH, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import provider_config as pc  # noqa: E402

from freeciv import atoms  # noqa: E402

try:  # the canonical llm confidence tier (0.55); fall back to the literal if core is absent
    import memory_schema as _ms  # noqa: E402
    LLM_CONF = float(_ms.DEFAULT_CONFIDENCE.get("llm", 0.55))
except Exception:  # noqa: BLE001
    LLM_CONF = 0.55

PROVIDER = os.environ.get("FREECIV_PROVIDER", "SNET")
_P = pc.provider_entry(PROVIDER) or {}
_KEY = os.environ.get(_P.get("api_key_env", ""), "") if _P else ""

# Preds whose adapter rendering (atoms._statement) we can validate deterministically. We keep the
# LLM to the property/relation vocabulary the reasoner already understands.
_ALLOWED_PREDS = ("Inheritance", "Similarity", "Evaluation")

SYSTEM_PROMPT = (
    "You are a symbolic-reasoning assistant for a FreeCiv game. Given the current state, propose a "
    "SMALL set of additional strategic FACTS that are true or highly likely but not already listed. "
    "Return ONLY JSON: {\"facts\":[{\"subj\":str,\"pred\":str,\"obj\":str,\"f\":float,\"c\":float}]}. "
    "pred must be one of: Inheritance (a property, obj is a single CamelCase word e.g. Exposed, "
    "Vulnerable, Isolated, WellDefended), or Evaluation (a relation, obj is 'Predicate:arg' e.g. "
    "'Near:City_1'). subj is an entity token like City_1, Unit_7, or Player_1 exactly as shown. "
    "f,c are in [0,1]. Propose at most 6 facts; prefer few, confident, decision-relevant ones. "
    "Do NOT restate facts already given. No prose."
)


def provider_info():
    return {"provider": PROVIDER, "model": _P.get("model"), "have_key": bool(_KEY),
            "key_env": _P.get("api_key_env"), "llm_conf": LLM_CONF}


def have_key():
    return bool(_KEY)


def _clamp01(x, default):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, v))


def validate_facts(raw_facts):
    """Filter raw proposed dicts to well-formed, adapter-schema facts (discounted to the llm tier).

    Drops anything that is not a mapping, uses a pred outside ``_ALLOWED_PREDS``, or renders to a
    statement ``atoms.validate_atom`` rejects. Confidence is CLAMPED to at most ``LLM_CONF`` (0.55)
    so a proposed fact can never out-trust a deterministic observation; frequency is clamped to
    [0,1]. Returns a deterministically-ordered, de-duplicated list of fact dicts.
    """
    seen, out = set(), []
    for rf in raw_facts or []:
        if not isinstance(rf, dict):
            continue
        subj, pred, obj = rf.get("subj"), rf.get("pred"), rf.get("obj")
        if not (isinstance(subj, str) and isinstance(pred, str) and isinstance(obj, str)):
            continue
        if pred not in _ALLOWED_PREDS:
            continue
        f = _clamp01(rf.get("f"), 1.0)
        c = min(_clamp01(rf.get("c"), LLM_CONF), LLM_CONF)
        fact = {"subj": subj, "pred": pred, "obj": obj, "f": f, "c": c, "category": "llm"}
        try:
            stmt = atoms._statement(fact)
        except Exception:  # noqa: BLE001 - a malformed obj (e.g. bad Evaluation encoding) is dropped
            continue
        if atoms.validate_atom(stmt) is not None:
            continue
        if stmt in seen:
            continue
        seen.add(stmt)
        out.append(fact)
    out.sort(key=lambda x: (x["subj"], x["pred"], x["obj"]))
    return out


def _render_state(norm):
    """Compact rendering of the state for the proposer (reuses llm_agent's plain view)."""
    from freeciv import llm_agent
    return llm_agent.render_plain(norm)


def propose_facts(norm, units=None, timeout=60, temperature=0.2, max_tokens=1500):
    """Return ``(validated_fact_dicts, meta)`` — extra LLM-proposed facts for this turn.

    Best-effort: returns ``([], meta)`` on a missing key or any error. ``meta`` carries latency,
    the raw/validated counts, and any error string for the per-turn metrics log.
    """
    meta = {"fact_llm_ms": None, "n_raw": 0, "n_llm_facts": 0, "error": None}
    if not _KEY:
        meta["error"] = "no_key"
        return [], meta
    context = _render_state(norm)
    payload = json.dumps({
        "model": _P.get("model"),
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": context}],
        "max_tokens": max_tokens, "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        _P.get("base_url", "").rstrip("/") + "/chat/completions", data=payload,
        headers={"Authorization": "Bearer " + _KEY, "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        meta["fact_llm_ms"] = int((time.time() - t0) * 1000)
        content = d["choices"][0]["message"].get("content") or ""
        i, j = content.find("{"), content.rfind("}")
        raw = json.loads(content[i:j + 1]).get("facts", []) if i >= 0 and j > i else []
        raw = raw if isinstance(raw, list) else []
        meta["n_raw"] = len(raw)
        facts = validate_facts(raw)
        meta["n_llm_facts"] = len(facts)
        return facts, meta
    except Exception as e:  # noqa: BLE001 - proposal is best-effort; never break the turn
        meta["fact_llm_ms"] = int((time.time() - t0) * 1000)
        meta["error"] = "{}: {}".format(type(e).__name__, str(e)[:200])
        return [], meta


if __name__ == "__main__":
    # Spike helper: propose facts from a captured state file (needs a provider key).
    from freeciv import adapter
    print("provider:", provider_info())
    if len(sys.argv) > 1:
        st = json.load(open(sys.argv[1], encoding="utf-8"))
        norm = adapter.normalize_state(st)
        facts, meta = propose_facts(norm)
        print("meta:", meta)
        for f in facts:
            print("  ", atoms._statement(f), "c=%s" % f["c"])
