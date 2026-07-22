"""v2 atomspace engine bridge for the ``facts+chaining-v2`` A/B arm (OPTIONAL, env-gated).

This routes one benchmark arm to the colleague's ``atomspace-v2``: it builds a v2-vocabulary
world overlay from the raw game state (reusing v2's own ``build_atomspaces.build_world`` so the
state->atom mapping stays authoritative), runs v2's host-side forward-chainer (``chain.py``) over
rulebook + world + player, and returns concrete ``(Recommend ...)`` strings — the same shape
``reason.derive`` returns, so ``ground.py`` and ``ab_sim`` consume it unchanged.

v2 lives OUTSIDE the committed tree (a gitignored scratch dir; its bundled ruleset is GPL, "do
not vendor into the MIT repo"). This module loads it DYNAMICALLY from ``OMEGACLAW_V2_DIR`` only
when present. Nothing here imports v2 at module-import time, so the committed benchmark has no
hard dependency on v2 and no GPL content: if the dir is absent, ``available()`` is False and the
caller falls back. ``chain.py`` is pure stdlib, so this engine runs on host and in-container
alike (no PeTTa needed) — which sidesteps the container's missing ``git-import!`` entirely.
"""

import importlib.util
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
V2_DIR = os.environ.get("OMEGACLAW_V2_DIR") or os.path.join(_HERE, "v2_scratch", "atomspace-v2")

_REQUIRED = ("chain.py", "build_atomspaces.py", "rulebook.metta", "player.metta")

_mods = {}       # name -> loaded module (cache)
_static = None   # cached [(tree, f, c, layer)] for the static rulebook + player layers


def available():
    """True iff a usable v2 atomspace is present at V2_DIR."""
    return all(os.path.exists(os.path.join(V2_DIR, f)) for f in _REQUIRED)


def _load(name):
    """Import a v2 .py module by file path (cached). Isolated module name to avoid clashes."""
    if name in _mods:
        return _mods[name]
    path = os.path.join(V2_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location("_v2_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    _mods[name] = mod
    return mod


def _static_sentences():
    global _static
    if _static is None:
        chain = _load("chain")
        s = []
        for layer in ("rulebook.metta", "player.metta"):
            s += chain.load_sentences(os.path.join(V2_DIR, layer))
        _static = s
    return _static


def world_sentences_from_raw(raw):
    """Map a raw llm_optimized state -> v2 world-overlay sentences as (tree, f, c, 'world').

    Reuses v2's build_world (authoritative state->atom mapping) by pointing its CAPTURE at a
    temp file holding `raw` and reading the freshly built B-space rows. Returns [] on any error
    (e.g. an unexpected state shape) so the arm degrades gracefully instead of crashing.
    """
    try:
        ba = _load("build_atomspaces")
        chain = _load("chain")
        fd, path = tempfile.mkstemp(suffix=".json", prefix="v2_state_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(raw, f)
            ba.CAPTURE = path          # redirect v2's hardcoded capture path
            ba.ROWS.clear()            # v2 accumulates atoms in a module global
            ba.build_world()
            out = []
            for r in ba.ROWS:
                if r.get("space") != "B" or r.get("atom") in (None, "(none)"):
                    continue
                tree, _ = chain.parse_sexpr(r["atom"])
                out.append((tree, float(r["f"]), float(r["c"]), "world"))
            return out
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    except Exception:  # noqa: BLE001 - bridge is best-effort; never break the arm
        return []


def derive(raw, conf_min=0.3):
    """Run v2's forward-chainer on rulebook + player + world(raw).

    Returns (recs, meta): recs is a sorted list of unique concrete ``(Recommend ...)`` strings
    (templates with $-vars and over-decayed conclusions filtered out); meta mirrors
    reason.derive's ``{"hops","n_conclusions","n_atoms"}``.
    """
    if not available():
        return [], {"hops": 0, "n_conclusions": 0, "n_atoms": 0}
    chain = _load("chain")
    sentences = list(_static_sentences()) + world_sentences_from_raw(raw)
    nodes = chain.chain(sentences)
    recs, maxdepth = [], 0
    for n in nodes.values():
        if n.rule is None or not (isinstance(n.tree, list) and n.tree[:1] == ["Recommend"]):
            continue
        if "$" in n.key or n.c < conf_min:
            continue
        recs.append(n.key)
        maxdepth = max(maxdepth, n.depth)
    recs = sorted(set(recs))
    return recs, {"hops": maxdepth, "n_conclusions": len(recs), "n_atoms": len(nodes)}


def derive_traced(raw, conf_min=0.3):
    """(recs, trace) matching reason.derive_traced's contract. Trace is None for v2 (the v2
    chainer keeps its own provenance; a PlnTrace is not modeled here — ab_sim tolerates None)."""
    recs, _meta = derive(raw, conf_min)
    return recs, None
