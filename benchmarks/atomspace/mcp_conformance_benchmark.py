"""T0.3 — tool-surface conformance for the 11 atomspace-agent tools.

Drives the transport-agnostic handlers in `atomspace_agent.tools` through the
scripted pipeline in `mcp_conformance_fixtures.build_cases` (happy paths,
dup/revised statuses, contradiction surfacing, the full injection-firewall
corpus, stv/source_type/scope failure taxonomy, supersession visibility,
empty-scope inference, bootstrap, export/import round-trips). Structural
conformance is checked on each case's FIRST run; every non-inference case is
then repeated 5x for latency (p50/p95 per tool).

Also runs:
  * two-client interleaving — two multiprocessing.Processes assert 100 atoms
    each (50 overlapping canonicals) into the SAME project scope: zero lost
    updates (final count == unique canonicals) and zero exceptions;
  * a real stdio transport probe (if `mcp` is importable): spawns
    `python -m atomspace_agent.server`, does initialize + tools/list + one
    tools/call round-trip; reported as stdio_transport ok/failed/skipped
    (report-only — not one of the pre-registered gates).

Pre-registered gates (benchmark-docs/atomspace.md): 100% case conformance;
zero crashes (no tool call may raise); lossless 2-client interleaving;
p95 < 150 ms per tool excluding `infer` and `bootstrap_project`.

Run with the Hyperon-MCP venv python:
    HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python
    $HYPERON_MCP_PY benchmarks/atomspace/mcp_conformance_benchmark.py

Writes mcp_conformance_results.{json,md} next to this script; exits 1 on any
gate failure. All state lives in a tempdir via ATOMSPACE_AGENT_HOME. The
MeTTa runtime is warmed once before timing (process-lifetime one-time cost,
excluded from per-call latency by design — an MCP server process loads it at
startup, not per tool call).
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
import multiprocessing
import os
import statistics
import subprocess
import sys
import tempfile
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from mcp_conformance_fixtures import (HOSTILE_SEED, INTERLEAVE_SCOPE,  # noqa: E402
                                      build_cases)

LATENCY_REPEATS = 5
LATENCY_GATE_MS = 150.0
LATENCY_EXEMPT_TOOLS = {"infer", "bootstrap_project"}
INTERLEAVE_PER_CLIENT = 100
INTERLEAVE_OVERLAP = 50
INTERLEAVE_TRIALS = 3  # fresh scope per trial: first-open races are probabilistic


# --- case runner --------------------------------------------------------------

def _check_expect(result, expect):
    """Declarative structural checks; returns a list of failure strings."""
    fails = []
    if result.get("ok") is not expect["ok"]:
        fails.append(f"ok={result.get('ok')!r}, expected {expect['ok']}")
    for key in expect.get("keys", []):
        if key not in result:
            fails.append(f"missing key {key!r}")
    if "status" in expect:
        want = expect["status"]
        want = want if isinstance(want, (list, tuple)) else [want]
        if result.get("status") not in want:
            fails.append(f"status={result.get('status')!r}, expected {want}")
    for key, val in expect.get("equals", {}).items():
        if result.get(key) != val:
            fails.append(f"{key}={result.get(key)!r}, expected {val!r}")
    if "error_contains" in expect:
        if expect["error_contains"].lower() not in str(result.get("error", "")).lower():
            fails.append(f"error {result.get('error')!r} lacks {expect['error_contains']!r}")
    if expect.get("hint") and not result.get("hint"):
        fails.append("no repair hint on a structured error")
    if "check" in expect and not fails:
        try:
            fails.extend(expect["check"](result))
        except Exception as exc:  # noqa: BLE001 — a check crash is a case failure
            fails.append(f"check raised {type(exc).__name__}: {exc}")
    return fails


def run_cases(cases):
    from atomspace_agent import tools
    conformance, latencies, crashes = [], {}, []
    for case in cases:
        fn = getattr(tools, case["tool"])
        exempt = case["tool"] in LATENCY_EXEMPT_TOOLS
        repeats = 1 if exempt else LATENCY_REPEATS
        case_fails, crashed = None, None
        for i in range(repeats):
            t0 = time.monotonic()
            try:
                result = fn(**case["kwargs"])
            except Exception as exc:  # noqa: BLE001 — a raise IS the defect under test
                crashed = f"{type(exc).__name__}: {exc}"
                if i == 0:
                    case_fails = [f"RAISED instead of structured error — {crashed}"]
                    crashes.append({"case": case["name"], "tool": case["tool"],
                                    "exception": crashed,
                                    "traceback": traceback.format_exc(limit=3)})
                continue
            finally:
                ms = (time.monotonic() - t0) * 1000
                if not exempt:
                    latencies.setdefault(case["tool"], []).append(ms)
            if i == 0:
                case_fails = _check_expect(result, case["expect"])
        conformance.append({"name": case["name"], "tool": case["tool"],
                            "pass": not case_fails, "failures": case_fails or []})
    return conformance, latencies, crashes


# --- two-client interleaving ----------------------------------------------------

def _interleave_atom(i):
    return f"(Inheritance file:interleave/f{i}.py module:il{i % 5})"


def _interleave_worker(scope, indices, home, barrier, queue):
    try:
        os.environ["ATOMSPACE_AGENT_HOME"] = home
        from atomspace_agent import tools
        barrier.wait(timeout=60)  # both clients open the fresh scope together
        ok = 0
        for i in indices:
            r = tools.atom_assert(_interleave_atom(i), scope=scope,
                                  source_type="tool_result")
            ok += bool(r.get("ok"))
        queue.put({"ok_calls": ok, "error": None})
    except Exception:  # noqa: BLE001
        queue.put({"ok_calls": -1, "error": traceback.format_exc(limit=5)})


def run_interleaving(home):
    """INTERLEAVE_TRIALS trials, each on a FRESH scope (concurrent first-open of
    a new scope DB is part of the contract two host sessions rely on). Both
    clients start behind a barrier and write the 50 SHARED canonicals first,
    so duplicate-assert convergence is actually contended, not staggered."""
    from atomspace_agent import tools
    overlap = list(range(INTERLEAVE_PER_CLIENT - INTERLEAVE_OVERLAP,
                         INTERLEAVE_PER_CLIENT))  # 50..99, shared
    schedules = (overlap + list(range(0, INTERLEAVE_PER_CLIENT - INTERLEAVE_OVERLAP)),
                 overlap + list(range(INTERLEAVE_PER_CLIENT,
                                      2 * INTERLEAVE_PER_CLIENT - INTERLEAVE_OVERLAP)))
    unique = len({_interleave_atom(i) for sched in schedules for i in sched})
    trials = []
    for t in range(INTERLEAVE_TRIALS):
        scope = f"feedfeed{t:04x}"  # fresh 12-hex scope key per trial
        queue = multiprocessing.Queue()
        barrier = multiprocessing.Barrier(2)
        procs = [multiprocessing.Process(
            target=_interleave_worker, args=(scope, sched, home, barrier, queue))
            for sched in schedules]
        for p in procs:
            p.start()
        reports = [queue.get(timeout=120) for _ in procs]
        for p in procs:
            p.join(timeout=30)
        total = tools.scope_info(scope=scope)["atom_counts"]["total"]
        errors = [r["error"] for r in reports if r["error"]]
        ok_calls = sum(r["ok_calls"] for r in reports if r["ok_calls"] >= 0)
        trials.append({"scope": scope, "final_count": total, "ok_calls": ok_calls,
                       "exceptions": errors,
                       "lossless": (not errors and total == unique
                                    and ok_calls == 2 * INTERLEAVE_PER_CLIENT)})
    return {"clients": 2, "asserts_per_client": INTERLEAVE_PER_CLIENT,
            "unique_canonicals": unique, "trials": trials,
            "lossless_trials": sum(t["lossless"] for t in trials),
            "lossless": all(t["lossless"] for t in trials)}


# --- stdio transport probe (report-only) -----------------------------------------

def stdio_probe(home):
    try:
        import mcp  # noqa: F401
    except ImportError:
        return {"status": "skipped", "reason": "mcp not importable"}
    import asyncio

    async def probe():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "atomspace_agent.server"],
            env={**os.environ, "ATOMSPACE_AGENT_HOME": home})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = sorted(t.name for t in listed.tools)
                call = await session.call_tool("scope_info", {"scope": "global"})
                return {"status": "ok" if len(names) == 11 and not call.isError
                                  else "failed",
                        "tools_listed": len(names), "tool_names": names,
                        "call_is_error": bool(call.isError)}

    try:
        return asyncio.run(asyncio.wait_for(probe(), timeout=60))
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


# --- setup ------------------------------------------------------------------------

def _make_repo(tmp):
    root = os.path.join(tmp, "repo")
    pkg = os.path.join(root, "pkg")
    os.makedirs(pkg)
    open(os.path.join(pkg, "__init__.py"), "w").close()
    with open(os.path.join(pkg, "a.py"), "w", encoding="utf-8") as f:
        f.write("import pkg.b\n")
    with open(os.path.join(pkg, "b.py"), "w", encoding="utf-8") as f:
        f.write("x = 1\n")
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as f:
        f.write("# Benchmark Repo\n## Setup\n## Conventions\n")
    subprocess.run(["git", "init", "-q", root], check=True, capture_output=True)
    return root


def _percentile(samples, q):
    s = sorted(samples)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def main():
    results = {}
    failures = []

    with tempfile.TemporaryDirectory(prefix="asa_mcp_bench_") as tmp:
        home = os.path.join(tmp, "home")
        os.environ["ATOMSPACE_AGENT_HOME"] = home
        os.environ["ATOMSPACE_AGENT_INFER_INPROCESS"] = "1"

        nonrepo = os.path.join(tmp, "nonrepo")
        os.makedirs(nonrepo)
        hostile = os.path.join(tmp, "hostile_seed.metta")
        with open(hostile, "w", encoding="utf-8") as f:
            f.write(HOSTILE_SEED)
        ctx = {"tmp": tmp, "repo": _make_repo(tmp), "nonrepo": nonrepo,
               "hostile_seed": hostile}

        # Warm the MeTTa runtime once (server-startup cost, not per-call).
        from atomspace_agent.runtime import get_runtime
        warm = get_runtime()
        results["runtime_backend"] = warm.name

        cases = build_cases(ctx)
        conformance, latencies, crashes = run_cases(cases)
        results["cases_total"] = len(conformance)
        results["cases_passed"] = sum(c["pass"] for c in conformance)
        results["conformance"] = conformance
        results["crashes"] = crashes
        failed_cases = [c for c in conformance if not c["pass"]]
        if failed_cases:
            failures.append(f"{len(failed_cases)}/{len(conformance)} cases failed "
                            f"conformance: {[c['name'] for c in failed_cases]}")
        if crashes:
            failures.append(f"{len(crashes)} tool call(s) RAISED instead of returning "
                            f"a structured error: {[c['case'] for c in crashes]}")

        lat_table = {}
        for tool, samples in sorted(latencies.items()):
            p50 = round(_percentile(samples, 0.50), 2)
            p95 = round(_percentile(samples, 0.95), 2)
            lat_table[tool] = {"n": len(samples), "p50_ms": p50, "p95_ms": p95,
                               "mean_ms": round(statistics.fmean(samples), 2)}
            if p95 >= LATENCY_GATE_MS:
                failures.append(f"latency: {tool} p95 {p95}ms >= {LATENCY_GATE_MS}ms")
        results["latency_ms"] = lat_table

        results["interleaving"] = run_interleaving(home)
        if not results["interleaving"]["lossless"]:
            inter = results["interleaving"]
            detail = "; ".join(
                f"trial {i}: count {t['final_count']}/{inter['unique_canonicals']}, "
                f"{t['ok_calls']}/{2 * INTERLEAVE_PER_CLIENT} ok calls, "
                f"{len(t['exceptions'])} exception(s)"
                + (f" [{t['exceptions'][0].strip().splitlines()[-1]}]"
                   if t["exceptions"] else "")
                for i, t in enumerate(inter["trials"]) if not t["lossless"])
            failures.append(f"interleaving not lossless "
                            f"({inter['lossless_trials']}/{INTERLEAVE_TRIALS} clean trials): "
                            f"{detail}")

        results["stdio_transport"] = stdio_probe(home)

    results["gate"] = {"passed": not failures, "failures": failures}
    with open(os.path.join(_HERE, "mcp_conformance_results.json"), "w",
              encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    inter = results["interleaving"]
    stdio = results["stdio_transport"]
    lat_rows = [f"| {tool} | {v['n']} | {v['p50_ms']} | {v['p95_ms']} |"
                for tool, v in results["latency_ms"].items()]
    fail_rows = [f"- `{c['name']}` ({c['tool']}): " + "; ".join(c["failures"])
                 for c in results["conformance"] if not c["pass"]]
    md = "\n".join([
        "# T0.3 — MCP tool-surface conformance",
        "",
        f"**{results['cases_total']} scripted cases** over all 11 tool handlers "
        f"(`atomspace_agent.tools`, backend: {results['runtime_backend']}): statuses "
        "(added/dup/revised + conflict flag), the full injection-firewall corpus from the "
        "product's test suite, stv/source_type/scope failure taxonomy, supersession "
        "visibility, empty-scope inference, bootstrap, and export/import round-trips "
        "(including a hostile seed file).",
        "",
        "| Cases passed | Crashes (tool call raised) | 2-client interleaving | stdio transport |",
        "| --- | --- | --- | --- |",
        f"| {results['cases_passed']}/{results['cases_total']} | {len(results['crashes'])} "
        f"| {inter['lossless_trials']}/{INTERLEAVE_TRIALS} lossless trials "
        f"(2x{INTERLEAVE_PER_CLIENT} asserts, {inter['unique_canonicals']} unique canonicals, "
        f"fresh scope per trial) -> {'lossless' if inter['lossless'] else 'LOSSY'} "
        f"| {stdio['status']} ({stdio.get('tools_listed', '—')} tools listed) |",
        "",
        "Per-tool latency over 5 runs/case (warm runtime; `infer` and "
        "`bootstrap_project` are exempt per the pre-registered gate):",
        "",
        "| Tool | samples | p50 ms | p95 ms |",
        "| --- | --- | --- | --- |",
        *lat_rows,
        "",
        *((["Failed cases:", ""] + fail_rows + [""]) if fail_rows else []),
        *((["Interleaving trials (2 processes, overlapping canonicals, fresh scope each):",
            ""]
           + [f"- trial {i} ({t['scope']}): count {t['final_count']}/"
              f"{inter['unique_canonicals']}, {t['ok_calls']}/{2 * INTERLEAVE_PER_CLIENT} "
              f"ok calls, {len(t['exceptions'])} exception(s)"
              + (f" — `{t['exceptions'][0].strip().splitlines()[-1]}`"
                 if t["exceptions"] else "")
              for i, t in enumerate(inter["trials"])]
           + [""]) if not inter["lossless"] else []),
        "Findings (non-gating): an unknown scope key format (e.g. `not-a-valid-scope!`) "
        "silently falls back to cwd resolution rather than returning a structured error — "
        "covered by `query-unknown-scope-format` as documented behavior.",
        "",
        "Known interleaving failure modes (which one a given run hits is a race): "
        "(1) concurrent FIRST-open of a new scope DB — `PRAGMA journal_mode=WAL` raises "
        "`sqlite3.OperationalError: database is locked` (AtomStore.__init__, store.py:92); "
        "(2) two clients asserting the same canonical — `assert_atom`'s SELECT-then-INSERT "
        "races to `sqlite3.IntegrityError: UNIQUE constraint failed: atoms.canonical` "
        "(store.py:117-127), contradicting the store's documented \"concurrent duplicate "
        "asserts converge\" contract.",
        "",
        "Pre-registered gates: 100% case conformance; zero crashes; lossless 2-client "
        f"interleaving; p95 < {LATENCY_GATE_MS:.0f} ms per tool excluding inference/bootstrap.",
        "",
        f"**GATE: {'PASSED' if not failures else 'FAILED'}**"
        + ("" if not failures else "\n\n" + "\n".join(f"- {f}" for f in failures)),
        "",
        "Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/mcp_conformance_benchmark.py` "
        "(HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python)",
        "",
    ])
    with open(os.path.join(_HERE, "mcp_conformance_results.md"), "w",
              encoding="utf-8") as f:
        f.write(md)
    print(md)

    if failures:
        print("\nT0.3 GATE: FAILED")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nT0.3 GATE: PASSED")


if __name__ == "__main__":
    main()
