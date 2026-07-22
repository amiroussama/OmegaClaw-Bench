"""T0.2 — AtomStore persistence, scoping, and hydration benchmark.

Exercises the product's SQLite-backed scoped store (`atomspace_agent.store`)
over the deterministic corpus from `atomstore_fixtures.build_corpus` (seeded
random.Random(1001), all 5 schema heads, all 5 source_types, ~5% marked for
supersession). Sections:

  a. round-trip fidelity  — assert corpus -> export_metta -> import into a
     FRESH store -> every canonical atom present with an identical stv (100%).
  b. scope isolation      — two project stores + global; each scope queried
     for the others' atoms (0 leakage, hard gate).
  c. supersession         — retract the marked ~5%; default query_pattern
     excludes 100% of them; include_superseded=True finds them all.
  d. crash recovery       — a subprocess asserts atoms in a loop and
     os._exit(1)s mid-run (no close/checkpoint); the reopened DB must pass
     PRAGMA integrity_check with counts consistent.
  e. hydration latency    — store.active_atoms(limit=n) + sexpr.parse of every
     atom: 1k < 500 ms, 10k < 3 s.
  f. re-transmission      — stateless baseline re-sends ALL n premises on each
     of M=50 inference calls (n*M atom-transmissions); candidate writes each
     atom once and reads only by_terms neighborhoods for 50 term queries.
     Gate: reduction >= 0.90.

Pre-registered gates (benchmark-docs/atomspace.md): fidelity 100%; cross-scope
leakage 0; supersession-exclusion 100%; crash recovery clean; hydrate
1k<500ms / 10k<3s; premise re-transmission reduction >=90%.

Run with the Hyperon-MCP venv python:
    HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python
    $HYPERON_MCP_PY benchmarks/atomspace/atomstore_benchmark.py [--large]

`--large` adds the 50_000-atom size. Writes atomstore_results.{json,md} next
to this script; exits 1 on any gate failure. All stores live in a tempdir via
ATOMSPACE_AGENT_HOME — nothing touches ~/.atomspace-agent.
"""

# --- atomspace-agent product locator (Bench repo tests the product, not core) ---
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
import random
import sqlite3
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from atomspace_agent import sexpr  # noqa: E402
from atomspace_agent.export import export_metta, import_seed  # noqa: E402
from atomspace_agent.store import AtomStore  # noqa: E402
from atomspace_agent.validate import validate_atom  # noqa: E402
from atomstore_fixtures import GROUPS, SEED, build_corpus, corpus_summary  # noqa: E402

RETRANSMIT_CALLS = 50          # M: inference calls in the stateless baseline
HYDRATE_GATES_MS = {1000: 500.0, 10000: 3000.0}
REDUCTION_GATE = 0.90


def _validated(corpus):
    """Pre-validate the corpus through the product firewall (fixture sanity)."""
    out = []
    for rec in corpus:
        v = validate_atom(rec["atom"])
        if not v.ok:
            raise AssertionError(f"fixture atom rejected by validator: {rec['atom']}: {v.error}")
        out.append((rec, v))
    return out


def _fill_store(store, validated):
    t0 = time.monotonic()
    added = 0
    for rec, v in validated:
        r = store.assert_atom(v.canonical, v.ast, stv=rec["stv"],
                              source_type=rec["source_type"])
        added += r["status"] == "added"
    return added, round((time.monotonic() - t0) * 1000, 1)


def section_fidelity(tmp, validated):
    """a. corpus -> export_metta -> fresh store -> identical canonical + stv."""
    orig = AtomStore("fid-orig", path=os.path.join(tmp, "fid_orig.db"))
    added, _ = _fill_store(orig, validated)
    text = export_metta(orig)
    fresh = AtomStore("fid-fresh", path=os.path.join(tmp, "fid_fresh.db"))
    report = import_seed(fresh, text)
    ok = 0
    mismatches = []
    for rec, v in validated:
        a, b = orig.get(v.canonical), fresh.get(v.canonical)
        if b is not None and a["stv"] == b["stv"]:
            ok += 1
        elif len(mismatches) < 5:
            mismatches.append({"atom": v.canonical, "orig": a and a["stv"],
                               "fresh": b and b["stv"]})
    orig.close(); fresh.close()
    n = len(validated)
    return {"n": n, "asserted": added, "import_report": {k: report[k] for k in
                                                         ("added", "dup", "revised", "total")},
            "import_rejected": len(report["rejected"]),
            "identical": ok, "fidelity_pct": round(100.0 * ok / n, 3),
            "mismatches": mismatches}


def section_scope_isolation(tmp):
    """b. two project scopes + global; 0 cross-scope leakage."""
    corpus = _validated(build_corpus(600))
    slices = {"aaaaaaaaaaaa": corpus[0:200], "bbbbbbbbbbbb": corpus[200:400],
              "global": corpus[400:600]}
    stores = {k: AtomStore(k, path=os.path.join(tmp, f"scope_{k}.db")) for k in slices}
    for k, sl in slices.items():
        _fill_store(stores[k], sl)
    leaks = 0
    checked = 0
    for k, sl in slices.items():
        others = [o for o in slices if o != k]
        for rec, v in sl:
            for o in others:
                checked += 1
                if stores[o].get(v.canonical) is not None:
                    leaks += 1
    # pattern-level spot check: exact-atom patterns against foreign scopes
    rng = random.Random(SEED + 7)
    for k, sl in slices.items():
        for rec, v in rng.sample(sl, 20):
            for o in [o for o in slices if o != k]:
                checked += 1
                if stores[o].query_pattern(v.ast):
                    leaks += 1
    for s in stores.values():
        s.close()
    return {"scopes": list(slices), "atoms_per_scope": 200,
            "cross_scope_lookups": checked, "leaks": leaks}


def section_supersession(tmp, validated):
    """c. retract the marked ~5%; excluded by default, visible on request."""
    store = AtomStore("super", path=os.path.join(tmp, "super.db"))
    _fill_store(store, validated)
    marked = [(rec, v) for rec, v in validated if rec["supersede"]]
    retracted = sum(store.retract(v.canonical, reason="benchmark supersession")
                    for rec, v in marked)
    excluded = sum(store.query_pattern(v.ast) == [] for rec, v in marked)
    visible = 0
    for rec, v in marked:
        got = store.query_pattern(v.ast, include_superseded=True)
        visible += len(got) == 1 and got[0]["superseded"]
    active = store.counts()
    store.close()
    n = len(marked)
    return {"marked": n, "retracted": retracted, "excluded_by_default": excluded,
            "visible_with_include_superseded": visible,
            "excluded_pct": round(100.0 * excluded / n, 3) if n else 0.0,
            "counts_after": active}


_CRASH_CHILD = r"""
import os, sys
sys.path[:0] = os.environ.get("ASA_BENCH_PATH", "").split(os.pathsep)
from atomspace_agent.store import AtomStore
from atomspace_agent.validate import validate_atom
path, k = sys.argv[1], int(sys.argv[2])
store = AtomStore("crash", path=path)
for i in range(10**9):  # "forever" — the crash cuts it short mid-run
    v = validate_atom(f"(Inheritance file:crash/f{i}.py module:crash-m{i % 7})")
    store.assert_atom(v.canonical, v.ast, source_type="tool_result")
    if i + 1 == k:
        os._exit(1)  # hard crash: no close(), no WAL checkpoint
"""


def section_crash_recovery(tmp, k=250):
    """d. child process os._exit(1)s mid-assert-loop; DB must reopen clean."""
    path = os.path.join(tmp, "crash.db")
    env = {**os.environ,
           "ASA_BENCH_PATH": os.pathsep.join(sys.path[:3])}
    proc = subprocess.run([sys.executable, "-c", _CRASH_CHILD, path, str(k)],
                          capture_output=True, text=True, timeout=120, env=env)
    crashed = proc.returncode == 1
    # raw sqlite reopen: integrity + internal consistency
    conn = sqlite3.connect(path)
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    atom_rows = conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0]
    term_atoms = conn.execute("SELECT COUNT(DISTINCT atom_id) FROM terms").fetchone()[0]
    prov_atoms = conn.execute("SELECT COUNT(DISTINCT atom_id) FROM provenance").fetchone()[0]
    conn.close()
    # product-level reopen
    store = AtomStore("crash", path=path)
    counts = store.counts()
    post = store.assert_atom("(Inheritance file:crash/after.py module:crash-m0)",
                             ("Inheritance", "file:crash/after.py", "module:crash-m0"),
                             source_type="tool_result")
    store.close()
    clean = (crashed and integrity == "ok" and atom_rows == k
             and term_atoms == k and prov_atoms == k
             and counts["total"] == k and post["status"] == "added")
    return {"child_exit_code": proc.returncode, "asserts_before_crash": k,
            "integrity_check": integrity, "atom_rows": atom_rows,
            "terms_consistent": term_atoms == k, "provenance_consistent": prov_atoms == k,
            "reopened_counts": counts, "post_crash_assert": post["status"],
            "clean": clean, "child_stderr": (proc.stderr or "")[-300:]}


def section_hydration(store, n):
    """e. active_atoms(limit=n) + sexpr.parse of every atom."""
    t0 = time.monotonic()
    recs = store.active_atoms(limit=n)
    for rec in recs:
        sexpr.parse(rec["atom"])
    ms = round((time.monotonic() - t0) * 1000, 1)
    return {"n": n, "hydrated": len(recs), "hydrate_ms": ms,
            "gate_ms": HYDRATE_GATES_MS.get(n)}


def section_retransmission(store, n):
    """f. stateless baseline (n premises re-sent on each of M calls) vs the
    persisted store (n one-time writes + by_terms neighborhoods)."""
    rng = random.Random(SEED + 1)
    terms = [f"module:m{rng.randrange(GROUPS)}" for _ in range(RETRANSMIT_CALLS)]
    baseline = n * RETRANSMIT_CALLS
    read_atoms = 0
    t0 = time.monotonic()
    for term in terms:
        read_atoms += len(store.by_terms([term]))
    read_ms = round((time.monotonic() - t0) * 1000, 1)
    candidate = n + read_atoms  # one-time writes + neighborhood reads
    reduction = 1.0 - candidate / baseline
    return {"n": n, "calls": RETRANSMIT_CALLS,
            "baseline_atoms_transmitted": baseline,
            "candidate_atoms_transmitted": candidate,
            "one_time_writes": n, "neighborhood_reads": read_atoms,
            "avg_neighborhood": round(read_atoms / RETRANSMIT_CALLS, 1),
            "read_ms": read_ms, "reduction": round(reduction, 4)}


def main():
    sizes = [1000, 10000] + ([50000] if "--large" in sys.argv else [])
    results = {"sizes": sizes, "corpus": {str(n): corpus_summary(n) for n in sizes},
               "per_size": {}}
    failures = []

    with tempfile.TemporaryDirectory(prefix="asa_bench_") as tmp:
        os.environ["ATOMSPACE_AGENT_HOME"] = os.path.join(tmp, "home")

        for n in sizes:
            validated = _validated(build_corpus(n))
            store = AtomStore(f"size-{n}", path=os.path.join(tmp, f"size_{n}.db"))
            added, write_ms = _fill_store(store, validated)
            rec = {"asserted_added": added, "write_ms": write_ms}
            if added != n:
                failures.append(f"[n={n}] only {added}/{n} atoms added (corpus not unique?)")

            rec["hydration"] = section_hydration(store, n)
            gate_ms = rec["hydration"]["gate_ms"]
            if rec["hydration"]["hydrated"] != n:
                failures.append(f"[n={n}] hydrated {rec['hydration']['hydrated']}/{n}")
            if gate_ms is not None and rec["hydration"]["hydrate_ms"] >= gate_ms:
                failures.append(f"[n={n}] hydrate {rec['hydration']['hydrate_ms']}ms "
                                f">= gate {gate_ms}ms")

            rec["retransmission"] = section_retransmission(store, n)
            if rec["retransmission"]["reduction"] < REDUCTION_GATE:
                failures.append(f"[n={n}] re-transmission reduction "
                                f"{rec['retransmission']['reduction']} < {REDUCTION_GATE}")
            store.close()
            results["per_size"][str(n)] = rec

        validated_1k = _validated(build_corpus(1000))
        results["fidelity"] = section_fidelity(tmp, validated_1k)
        if results["fidelity"]["fidelity_pct"] != 100.0 or results["fidelity"]["import_rejected"]:
            failures.append(f"fidelity {results['fidelity']['fidelity_pct']}% "
                            f"({results['fidelity']['import_rejected']} import rejections)")

        results["scope_isolation"] = section_scope_isolation(tmp)
        if results["scope_isolation"]["leaks"]:
            failures.append(f"cross-scope leakage: {results['scope_isolation']['leaks']} atoms")

        results["supersession"] = section_supersession(tmp, validated_1k)
        sup = results["supersession"]
        if not (sup["marked"] and sup["retracted"] == sup["marked"]
                and sup["excluded_by_default"] == sup["marked"]
                and sup["visible_with_include_superseded"] == sup["marked"]):
            failures.append(f"supersession: marked={sup['marked']} retracted={sup['retracted']} "
                            f"excluded={sup['excluded_by_default']} "
                            f"visible={sup['visible_with_include_superseded']}")

        results["crash_recovery"] = section_crash_recovery(tmp)
        if not results["crash_recovery"]["clean"]:
            failures.append(f"crash recovery not clean: {results['crash_recovery']}")

    results["gate"] = {"passed": not failures, "failures": failures}
    with open(os.path.join(_HERE, "atomstore_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    size_rows = []
    for n in sizes:
        r = results["per_size"][str(n)]
        h, rt = r["hydration"], r["retransmission"]
        gate = f"< {int(h['gate_ms'])} ms" if h["gate_ms"] else "(no gate)"
        size_rows.append(
            f"| {n:,} | {r['write_ms']:.0f} ms | {h['hydrate_ms']} ms {gate} "
            f"| {rt['baseline_atoms_transmitted']:,} | {rt['candidate_atoms_transmitted']:,} "
            f"| **{rt['reduction'] * 100:.1f}%** |")

    fid = results["fidelity"]
    iso = results["scope_isolation"]
    cr = results["crash_recovery"]
    md = "\n".join([
        "# T0.2 — AtomStore persistence, scoping, hydration",
        "",
        f"Deterministic corpus (`random.Random({SEED})`, all 5 heads, all 5 source_types, "
        f"~5% supersession-marked). Baseline for section f = a **stateless** engine that "
        f"re-sends all n premises on each of {RETRANSMIT_CALLS} inference calls; candidate = "
        "the persisted store (each atom written once, reads via `by_terms` neighborhoods).",
        "",
        "| Corpus | write | hydrate (active_atoms + parse) | baseline atoms sent "
        "| candidate atoms sent | reduction |",
        "| --- | --- | --- | --- | --- | --- |",
        *size_rows,
        "",
        "| Section | Result | Gate |",
        "| --- | --- | --- |",
        f"| a. round-trip fidelity (export_metta -> fresh import, n={fid['n']}) "
        f"| {fid['identical']}/{fid['n']} identical stv ({fid['fidelity_pct']}%), "
        f"{fid['import_rejected']} rejected | 100% |",
        f"| b. scope isolation (2 projects + global, {iso['cross_scope_lookups']} "
        f"cross-scope lookups) | {iso['leaks']} leaks | 0 |",
        f"| c. supersession ({sup['marked']} marked) | {sup['excluded_by_default']}/"
        f"{sup['marked']} excluded by default; {sup['visible_with_include_superseded']}/"
        f"{sup['marked']} visible with include_superseded | 100% / 100% |",
        f"| d. crash recovery (child os._exit(1) after {cr['asserts_before_crash']} asserts) "
        f"| integrity_check={cr['integrity_check']}, rows={cr['atom_rows']}, "
        f"reopen+assert={cr['post_crash_assert']} | clean |",
        "",
        "Pre-registered gates: fidelity 100%; cross-scope leakage 0; supersession-exclusion "
        "100%; crash recovery clean; hydrate 1k<500ms / 10k<3s; re-transmission reduction "
        ">=90% vs the stateless baseline.",
        "",
        f"**GATE: {'PASSED' if not failures else 'FAILED'}**"
        + ("" if not failures else "\n\n" + "\n".join(f"- {f}" for f in failures)),
        "",
        "Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/atomstore_benchmark.py` "
        "(HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python; add `--large` "
        "for the 50k size)",
        "",
    ])
    with open(os.path.join(_HERE, "atomstore_results.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)

    if failures:
        print("\nT0.2 GATE: FAILED")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nT0.2 GATE: PASSED")


if __name__ == "__main__":
    main()
