"""Reusable PLN reasoning-trace container — the "electron microscope" for PLN (Issue #1).

Captures, serializes, and renders what a PLN derivation actually did: the input query/goal, the
premises it started from, each inference hop (the atoms derived that pass, with their truth
values), and the final recommendations. It is deliberately NOT coupled to FreeCiv / any game —
callers hand it opaque atom strings, truth values, and context, so any PLN use case can produce
and read the same trace object. FreeCiv's ``reason.derive_traced`` is one such caller.

Two renderings: ``to_json`` (machine-readable, stable schema ``pln-trace/v1``) and ``render_text``
(human-readable). ``explain`` produces natural-language sentences derived *purely* from the
recorded trace — never invented after the fact.

Stdlib only. Trace IDs use uuid4 (host-safe; randomness is fine — traces are addressed by id, not
compared for equality).
"""

import json
import os
import re
import uuid

SCHEMA = "pln-trace/v1"

_STV_RE = re.compile(r"\(stv\s+([-\d.eE]+)\s+([-\d.eE]+)\)")
_VAR_SUFFIX_RE = re.compile(r"(\$[A-Za-z_][\w-]*)#\d+")


def new_trace_id(prefix="pln"):
    """A stable, unique trace id, e.g. ``pln-8c1f2ab391de``."""
    return "{}-{}".format(prefix, uuid.uuid4().hex[:12])


def normalize_vars(text):
    """Strip hyperon variable-rename suffixes: ``$c#37`` -> ``$c``."""
    return _VAR_SUFFIX_RE.sub(r"\1", text)


def parse_stv(text):
    """Extract the first ``(stv f c)`` from ``text`` as {strength, confidence}, or None."""
    m = _STV_RE.search(text or "")
    if not m:
        return None
    try:
        return {"strength": float(m.group(1)), "confidence": float(m.group(2))}
    except (TypeError, ValueError):
        return None


def _stv(strength, confidence):
    if strength is None or confidence is None:
        return None
    return {"strength": float(strength), "confidence": float(confidence)}


def _fmt_stv(stv):
    if not stv:
        return "stv ?/?"
    return "stv %.3f/%.3f" % (stv["strength"], stv["confidence"])


class PlnTrace:
    """One PLN derivation's structured trace.

    Populated by the caller: ``add_hop`` per inference pass, ``finish`` with the final
    recommendations. Host-safe callers still create + finish a trace (recording the attempt and an
    ``interpreter_unavailable`` status) so every decision has an auditable record.
    """

    def __init__(self, query, facts=None, engine=None, context=None, trace_id=None):
        self.trace_id = trace_id or new_trace_id()
        self.query = query
        self.facts = list(facts or [])
        self.engine = dict(engine or {})
        self.context = dict(context or {})
        self.hops = []
        self.conclusions = []
        self.recommendations = []
        self.status = "pending"
        self.error = None
        self.latency_ms = None

    # --- population -------------------------------------------------------

    def add_hop(self, n_premises, derived):
        """Record one inference pass.

        ``derived`` is an iterable of dicts ``{atom, strength, confidence, new}`` — the atoms the
        engine produced this pass, with truth values and whether the atom was newly learned.
        """
        rows = []
        for d in derived:
            rows.append({
                "atom": normalize_vars(d["atom"]),
                "stv": _stv(d.get("strength"), d.get("confidence")),
                "new": bool(d.get("new", True)),
            })
        self.hops.append({"hop": len(self.hops) + 1, "n_premises": n_premises,
                          "derived": rows, "n_new": sum(1 for r in rows if r["new"])})

    def set_conclusions(self, conclusions):
        """Record the final conclusion atoms. Each: {atom, strength, confidence, rule_id?, premises?}."""
        self.conclusions = []
        for c in conclusions:
            self.conclusions.append({
                "atom": normalize_vars(c["atom"]),
                "stv": _stv(c.get("strength"), c.get("confidence")),
                "rule_id": c.get("rule_id"),
                "premises": list(c.get("premises") or []),
            })

    def finish(self, recommendations, status=None, error=None, latency_ms=None):
        self.recommendations = list(recommendations or [])
        if status is not None:
            self.status = status
        else:
            self.status = "ok" if self.recommendations else "no_conclusions"
        self.error = error
        self.latency_ms = latency_ms
        return self

    # --- serialization ----------------------------------------------------

    def to_dict(self):
        return {
            "schema": SCHEMA,
            "trace_id": self.trace_id,
            "query": self.query,
            "engine": self.engine,
            "context": self.context,
            "inputs": {"facts": self.facts},
            "hops": self.hops,
            "conclusions": self.conclusions,
            "recommendations": self.recommendations,
            "status": self.status,
            "error": self.error,
            "latency_ms": self.latency_ms,
        }

    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, d):
        t = cls(d.get("query"), facts=(d.get("inputs") or {}).get("facts"),
                engine=d.get("engine"), context=d.get("context"), trace_id=d.get("trace_id"))
        t.hops = d.get("hops") or []
        t.conclusions = d.get("conclusions") or []
        t.recommendations = d.get("recommendations") or []
        t.status = d.get("status", "pending")
        t.error = d.get("error")
        t.latency_ms = d.get("latency_ms")
        return t

    def save(self, traces_dir):
        """Write ``<traces_dir>/<trace_id>.json`` (creating the dir); return the path."""
        os.makedirs(traces_dir, exist_ok=True)
        path = os.path.join(traces_dir, "{}.json".format(self.trace_id))
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        return path

    @classmethod
    def load(cls, traces_dir, trace_id):
        path = os.path.join(traces_dir, "{}.json".format(trace_id))
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    # --- rendering --------------------------------------------------------

    def render_text(self):
        """Human-readable electron-microscope view of the derivation."""
        L = []
        head = "PLN trace {}  status={}".format(self.trace_id, self.status)
        if self.latency_ms is not None:
            head += "  {}ms".format(int(self.latency_ms))
        if self.context:
            head += "  context={}".format(self.context)
        L.append(head)
        if self.error:
            L.append("  error: {}".format(self.error))
        L.append("facts ({}):".format(len(self.facts)))
        for f in self.facts:
            L.append("  {}".format(f))
        for h in self.hops:
            L.append("hop {} (premises={}, new={}):".format(h["hop"], h["n_premises"], h["n_new"]))
            for d in h["derived"]:
                mark = "+" if d["new"] else " "
                L.append("  {} {}  {}".format(mark, d["atom"], _fmt_stv(d["stv"])))
        L.append("conclusions ({}):".format(len(self.conclusions)))
        for c in self.conclusions:
            via = "  [{}]".format(c["rule_id"]) if c.get("rule_id") else ""
            L.append("  {}  {}{}".format(c["atom"], _fmt_stv(c["stv"]), via))
        L.append("recommendations: {}".format(", ".join(self.recommendations) or "(none)"))
        return "\n".join(L)

    def explain(self):
        """Natural-language summary derived purely from the recorded trace (no invention)."""
        if self.status == "interpreter_unavailable":
            return ("PLN engine unavailable — no derivation ran; recorded {} input fact(s)."
                    .format(len(self.facts)))
        if not self.conclusions and not self.recommendations:
            return "No PLN conclusions were derived from {} input fact(s).".format(len(self.facts))
        parts = []
        for c in self.conclusions:
            s = c["atom"]
            if c.get("stv"):
                s += " ({})".format(_fmt_stv(c["stv"]))
            if c.get("rule_id"):
                s += " via {}".format(c["rule_id"])
            parts.append(s)
        return ("Derived {} conclusion(s) over {} hop(s): ".format(len(self.conclusions), len(self.hops))
                + "; ".join(parts))


def _demo():
    """Build a trace for a known one-hop inference and print both renderings."""
    t = PlnTrace(query="recommend-for",
                 facts=["((Inheritance City_1 Undefended) (stv 1.0 0.99))"],
                 engine={"cmd": "sh /PeTTa/run.sh", "available": True},
                 context={"turn": 12, "arm": "pln"})
    t.add_hop(1, [{"atom": "(Recommend City_1 Defend)", "strength": 0.9, "confidence": 0.7128, "new": True}])
    t.set_conclusions([{"atom": "(Recommend City_1 Defend)", "strength": 0.9, "confidence": 0.7128,
                        "rule_id": "recommend-defend",
                        "premises": ["((Inheritance City_1 Undefended) (stv 1.0 0.99))"]}])
    t.finish(["(Recommend City_1 Defend)"], latency_ms=412)
    print(t.render_text())
    print()
    print(t.explain())
    print()
    print(t.to_json())


if __name__ == "__main__":
    _demo()
