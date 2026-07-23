"""T1.3 — scope_routing: does a cwd resolve to the right AtomSpace, with zero
cross-project leakage?

Builds real git repos (distinct remotes, a clone sharing a remote, a no-remote
repo, a non-git dir), then (a) probes many cwds through ``scopes.resolve`` and
checks each lands on the expected scope key, and (b) asserts a distinct atom
slice into every scope (via the resolve-driven ``db_path``) and cross-queries
every other scope — which must return nothing.

Pre-registered gate (benchmark-docs/atomspace.md): cross-project leakage = 0
(hard); routing accuracy >= 0.95.

Run: $HYPERON_MCP_PY benchmarks/atomspace/scope_routing_benchmark.py
Writes scope_routing_results.{json,md}; exits 1 on any gate failure.
"""

# --- atomspace-agent product locator ---
import os as _os
import sys as _sys

try:
    import atomspace_agent  # noqa: F401
except ImportError:
    _sys.path.insert(0, _os.environ.get("ATOMSPACE_AGENT_SRC",
                                        "/home/rojo-dev/Repos/Hyperon-MCP/src"))
    import atomspace_agent  # noqa: F401
# --- end product locator ---

import json
import os
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from atomspace_agent import scopes  # noqa: E402
from atomspace_agent.store import AtomStore  # noqa: E402
from atomspace_agent.validate import validate_atom  # noqa: E402

import scope_routing_fixtures as F  # noqa: E402

GATE_ROUTING_ACCURACY = 0.95


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _build_repos(root):
    """Create the repo topology; return {name: toplevel_path}."""
    paths = {}
    for spec in F.REPOS:
        p = os.path.join(root, spec["name"])
        os.makedirs(p, exist_ok=True)
        if spec["git"]:
            _git(["init", "-q"], p)
            _git(["config", "user.email", "b@b.test"], p)
            _git(["config", "user.name", "bench"], p)
            if spec["remote"]:
                _git(["remote", "add", "origin", spec["remote"]], p)
        for sub in F.SUBDIRS:
            if sub:
                os.makedirs(os.path.join(p, sub), exist_ok=True)
        paths[spec["name"]] = p
    return paths


def _expected_key(spec, paths):
    if not spec["git"]:
        return scopes.GLOBAL_SCOPE
    root = paths[spec.get("same_key_as", spec["name"])]
    return scopes.project_key(root)


def run(root):
    paths = _build_repos(root)
    probes = []
    for spec in F.REPOS:
        expected = _expected_key(spec, paths)
        for sub in F.SUBDIRS:
            cwd = os.path.join(paths[spec["name"]], sub) if sub else paths[spec["name"]]
            got, _ = scopes.resolve(scope=None, cwd=cwd)
            probes.append({"repo": spec["name"], "subdir": sub or ".",
                           "expected": expected, "got": got, "ok": got == expected})
    routed = sum(p["ok"] for p in probes)
    routing_accuracy = round(routed / len(probes), 4)

    # -- cross-scope leakage: one distinct atom slice per DISTINCT scope key --
    keys = {}
    for spec in F.REPOS:
        keys.setdefault(_expected_key(spec, paths), spec["name"])
    slices = {}
    for idx, key in enumerate(sorted(keys)):
        atoms = [f"(Inheritance file:scope{idx}/f{j}.py module:s{idx}) " for j in range(15)]
        slices[key] = [a.strip() for a in atoms]
        store = AtomStore(key)
        try:
            for a in slices[key]:
                v = validate_atom(a)
                store.assert_atom(v.canonical, v.ast, source_type="tool_result")
        finally:
            store.close()
    leaks, checked = 0, 0
    for key in slices:
        store = AtomStore(key)
        try:
            for other, atoms in slices.items():
                if other == key:
                    continue
                for a in atoms:
                    checked += 1
                    if store.get(a) is not None:
                        leaks += 1
        finally:
            store.close()

    return {"probes": probes, "routing_accuracy": routing_accuracy,
            "routed": routed, "n_probes": len(probes),
            "distinct_scopes": len(keys), "cross_scope_lookups": checked, "leaks": leaks}


def main():
    with tempfile.TemporaryDirectory(prefix="asa_t13_") as tmp:
        os.environ["ATOMSPACE_AGENT_HOME"] = os.path.join(tmp, "home")
        res = run(os.path.join(tmp, "repos"))

    failures = []
    if res["leaks"]:
        failures.append(f"cross-scope leakage: {res['leaks']} atoms (hard gate = 0)")
    if res["routing_accuracy"] < GATE_ROUTING_ACCURACY:
        miss = [f"{p['repo']}/{p['subdir']} -> {p['got']} (want {p['expected']})"
                for p in res["probes"] if not p["ok"]][:8]
        failures.append(f"routing accuracy {res['routing_accuracy']} < {GATE_ROUTING_ACCURACY}: "
                        + "; ".join(miss))

    results = {"summary": F.summary(), "result": {k: res[k] for k in
               ("routing_accuracy", "routed", "n_probes", "distinct_scopes",
                "cross_scope_lookups", "leaks")},
               "gate": {"passed": not failures, "failures": failures}}
    with open(os.path.join(_HERE, "scope_routing_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    md = "\n".join([
        "# T1.3 — scope_routing (cwd -> AtomSpace, zero cross-project leakage)",
        "",
        f"{len(F.REPOS)} repos (distinct remotes, a clone sharing repo-a's remote, a no-remote "
        f"repo, a non-git dir); {res['n_probes']} cwd probes; {res['distinct_scopes']} distinct "
        "scopes cross-queried.",
        "",
        "| Metric | Value | Gate |",
        "| --- | --- | --- |",
        f"| routing accuracy | {res['routing_accuracy']} ({res['routed']}/{res['n_probes']}) "
        f"| >= {GATE_ROUTING_ACCURACY} |",
        f"| cross-scope leakage | {res['leaks']} / {res['cross_scope_lookups']} lookups "
        "| 0 (hard) |",
        "",
        f"**GATE: {'PASSED' if not failures else 'FAILED'}**"
        + ("" if not failures else "\n\n" + "\n".join(f"- {f}" for f in failures)),
        "",
        "Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/scope_routing_benchmark.py`",
        "",
    ])
    with open(os.path.join(_HERE, "scope_routing_results.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)

    if failures:
        print("\nT1.3 GATE: FAILED")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nT1.3 GATE: PASSED")


if __name__ == "__main__":
    main()
