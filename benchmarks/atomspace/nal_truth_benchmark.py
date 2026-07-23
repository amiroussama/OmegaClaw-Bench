"""T0.1 — cross-backend truth-value conformance for atomspace-agent.

Every available MeTTa backend (hyperon in-process, PeTTa subprocess) must
reproduce the product's golden truth values (`atomspace_agent.truth`, the
formula-by-formula Python mirror of the vendored lib_nal.metta/lib_pln.metta)
within EPSILON=1e-6, over the full deterministic corpus from
`atomspace_agent.conformance.truth_cases()` — and derive the rule-level
RULE_CASES conclusions end to end via `backend.infer_pair`.

PurePythonBackend runs RULE_CASES only: its truth arithmetic IS the golden
reference, so value-level comparison against it would be circular. Arrow-form
NAL rule cases (`-->`) are skipped on the pure backend (documented product
limitation: arrow-form NAL needs a MeTTa runtime).

Pre-registered gate (benchmark-docs/atomspace.md):
  * 100% pass at epsilon 1e-6 for EVERY available MeTTa backend;
  * at least ONE MeTTa backend must be available (else FAIL);
  * unavailable backends are reported as SKIPPED (not silently ignored).

Run with the Hyperon-MCP venv python:
    HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python
    $HYPERON_MCP_PY benchmarks/atomspace/nal_truth_benchmark.py

Writes nal_truth_results.{json,md} next to this script; exits 1 on gate failure.
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
import re
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from atomspace_agent import sexpr  # noqa: E402
from atomspace_agent.runtime import (HyperonBackend, PettaSubprocessBackend,  # noqa: E402
                                     PurePythonBackend, lib_source)
from nal_truth_fixtures import (EPSILON, MIN_RULE_CASES, MIN_TRUTH_CASES,  # noqa: E402
                                RULE_CASES, corpus_summary, truth_cases)


# --- truth-value runners (mirror tests/conformance/test_truth_golden.py) -----

def _hyperon_runner():
    from hyperon import MeTTa
    m = MeTTa()
    m.run(lib_source())

    def run(query):
        out = []
        for rs in m.run(query):
            for atom in rs if isinstance(rs, list) else [rs]:
                out.append(str(atom))
        return out
    return run


_PETTA_RESULT_RE = re.compile(r"^\s*\[(.*)\]\s*$")
_PETTA_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_PETTA_NUM_RE = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")


def _petta_runner():
    """Raw PeTTa runner for truth-value cases: the backend's `_run_program`
    filters output down to ((atom) (stv f c)) conclusion pairs, which would drop
    bare stv/scalar truth-case results — so truth cases go through the same
    subprocess protocol but keep the raw result-line contents.

    Uses ``lib_source(minmax_shim=False)`` (PeTTa provides binary min/max
    natively; the hyperon shim aborts it with `No permission to modify static
    procedure min/3`), strips ANSI, and accepts BOTH the legacy bracketed form
    and this PeTTa build's bare trailing ``(stv f c)`` / scalar result lines."""
    backend = PettaSubprocessBackend()
    lib = lib_source(minmax_shim=False)

    def run(query):
        fd, path = tempfile.mkstemp(suffix=".metta", prefix="asa_bench_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(lib + "\n" + query + "\n")
            proc = subprocess.run(backend.cmd + [path], cwd=backend.cwd,
                                  capture_output=True, text=True,
                                  timeout=backend.timeout)
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        lines = [_PETTA_ANSI_RE.sub("", ln).strip() for ln in out.splitlines()]
        # This PeTTa build prints the evaluation result AFTER the final prolog-
        # goal terminator (a `^^^^` marker); everything before is the verbose
        # metta->prolog translation dump (which contains stray constants like 0).
        last_marker = max((i for i, ln in enumerate(lines) if ln.startswith("^^^")),
                          default=-1)
        texts = []
        for line in lines[last_marker + 1:]:
            if not line:
                continue
            m = _PETTA_RESULT_RE.match(line)
            if m:
                texts.append(m.group(1).replace(",", " "))
            elif line.startswith("(stv ") or _PETTA_NUM_RE.match(line):
                texts.append(line)   # bare result line (single query per subprocess)
        return texts
    return run


def _parse_value(texts):
    """Interpret backend output as an (f, c) stv, a scalar, or None (empty)."""
    for t in texts:
        try:
            exprs = sexpr.parse_all(t)
        except sexpr.SexprError:
            continue
        for e in exprs:
            if isinstance(e, tuple) and len(e) == 3 and e[0] == "stv":
                return (float(e[1]), float(e[2]))
            if isinstance(e, str):
                try:
                    return float(e)
                except ValueError:
                    continue
    return None


def _run_truth_cases(run, cases):
    """Evaluate every golden case; return metrics + failure details."""
    n_pass, failures = 0, []
    max_df, max_dc = 0.0, 0.0
    for case in cases:
        got = _parse_value(run(case["metta"]))
        want = case["expected"]
        ok = False
        if want is None:
            ok = got is None
            if not ok:
                failures.append(f"{case['name']}: expected empty, got {got}")
        elif isinstance(want, tuple):
            if got is None or not isinstance(got, tuple):
                failures.append(f"{case['name']}: expected stv {want}, got {got}")
            else:
                df, dc = abs(got[0] - want[0]), abs(got[1] - want[1])
                max_df, max_dc = max(max_df, df), max(max_dc, dc)
                ok = df <= EPSILON and dc <= EPSILON
                if not ok:
                    failures.append(f"{case['name']}: {got} != {want}")
        else:
            if got is None or isinstance(got, tuple):
                failures.append(f"{case['name']}: expected scalar {want}, got {got}")
            else:
                df = abs(got - want)
                max_df = max(max_df, df)
                ok = df <= EPSILON
                if not ok:
                    failures.append(f"{case['name']}: {got} != {want}")
        n_pass += ok
    return {"run": len(cases), "pass": n_pass, "fail": len(cases) - n_pass,
            "max_abs_delta_f": max_df, "max_abs_delta_c": max_dc,
            "failures": failures[:20]}


def _run_rule_cases(backend):
    """Rule-level pair cases through backend.infer_pair (skips arrow-form NAL
    on the pure backend)."""
    n_run, n_pass, failures = 0, 0, []
    max_df, max_dc = 0.0, 0.0
    skipped = 0
    for case in RULE_CASES:
        if backend.name == "pure" and "-->" in case["p1"][0]:
            skipped += 1
            continue
        n_run += 1
        got = dict(backend.infer_pair(case["p1"], case["p2"], engine=case["engine"]))
        ok = True
        for atom, (f, c) in case["must_contain"].items():
            if atom not in got:
                ok = False
                failures.append(f"{case['name']}: missing {atom}; got {list(got)[:5]}")
                continue
            stv = got[atom]
            df, dc = abs(stv.f - f), abs(stv.c - c)
            max_df, max_dc = max(max_df, df), max(max_dc, dc)
            if df > EPSILON or dc > EPSILON:
                ok = False
                failures.append(f"{case['name']}: {atom} stv {tuple(stv)} != {(f, c)}")
        n_pass += ok
    return {"run": n_run, "pass": n_pass, "fail": n_run - n_pass, "skipped": skipped,
            "max_abs_delta_f": max_df, "max_abs_delta_c": max_dc,
            "failures": failures[:20]}


def main():
    summary = corpus_summary()
    cases = list(truth_cases())
    metta_backends = {
        "hyperon": (HyperonBackend.available(), HyperonBackend, _hyperon_runner),
        "petta": (PettaSubprocessBackend.available(), PettaSubprocessBackend, _petta_runner),
    }

    results = {"corpus": summary, "backends": {}}
    failures = []

    if summary["truth_cases"] < MIN_TRUTH_CASES or summary["rule_cases"] < MIN_RULE_CASES:
        failures.append(f"corpus shrank: {summary['truth_cases']} truth / "
                        f"{summary['rule_cases']} rule cases "
                        f"(pre-registered minimum {MIN_TRUTH_CASES}/{MIN_RULE_CASES})")

    available = [n for n, (avail, _, _) in metta_backends.items() if avail]
    if not available:
        failures.append("no MeTTa backend available (hyperon or petta required)")

    for name, (avail, cls, make_runner) in metta_backends.items():
        if not avail:
            results["backends"][name] = {"status": "SKIPPED",
                                         "reason": "backend not available on this host"}
            continue
        t0 = time.monotonic()
        run = make_runner()
        truth = _run_truth_cases(run, cases)
        rules = _run_rule_cases(cls())
        elapsed = round(time.monotonic() - t0, 2)
        results["backends"][name] = {"status": "RUN", "truth": truth, "rules": rules,
                                     "elapsed_s": elapsed}
        if truth["fail"]:
            failures.append(f"[{name}] {truth['fail']}/{truth['run']} truth cases off "
                            f"golden by > {EPSILON}")
        if rules["fail"]:
            failures.append(f"[{name}] {rules['fail']}/{rules['run']} rule cases failed")

    # Pure backend: rule cases only (its arithmetic IS the golden reference —
    # value-level self-comparison would be circular; this checks the rule
    # DISPATCH layer against the same expected conclusions).
    pure_rules = _run_rule_cases(PurePythonBackend())
    results["backends"]["pure"] = {
        "status": "RUN (rule cases only — truth arithmetic is the golden reference)",
        "rules": pure_rules}
    if pure_rules["fail"]:
        failures.append(f"[pure] {pure_rules['fail']}/{pure_rules['run']} rule cases failed")

    results["gate"] = {"passed": not failures, "failures": failures}
    with open(os.path.join(_HERE, "nal_truth_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    def _fmt_delta(v):
        return f"{v:.2e}" if v else "0"

    rows = []
    for name in ("hyperon", "petta", "pure"):
        rec = results["backends"][name]
        if rec["status"] == "SKIPPED":
            rows.append(f"| {name} | SKIPPED | — | — | — | — |")
            continue
        t = rec.get("truth")
        r = rec["rules"]
        tcell = f"{t['pass']}/{t['run']}" if t else "n/a (golden ref)"
        dmax = max((t["max_abs_delta_f"] if t else 0), (t["max_abs_delta_c"] if t else 0),
                   r["max_abs_delta_f"], r["max_abs_delta_c"])
        rows.append(f"| {name} | RUN | {tcell} | {r['pass']}/{r['run']}"
                    f"{' (+%d skipped arrow-form)' % r['skipped'] if r.get('skipped') else ''} "
                    f"| {_fmt_delta(dmax)} | {rec.get('elapsed_s', '—')} |")

    md = "\n".join([
        "# T0.1 — NAL/PLN truth-value cross-backend conformance",
        "",
        f"Corpus: **{summary['truth_cases']} golden truth cases** "
        f"({summary['by_family']['nal']} NAL / {summary['by_family']['pln']} PLN; "
        f"{summary['by_expected_kind']['stv']} stv, {summary['by_expected_kind']['scalar']} scalar, "
        f"{summary['by_expected_kind']['empty']} expected-empty) + "
        f"**{summary['rule_cases']} rule-level pair cases**, epsilon **{EPSILON}**.",
        "Golden reference: `atomspace_agent.truth` (pure-Python mirror of the vendored "
        "lib_nal.metta / lib_pln.metta). Every available MeTTa backend must reproduce it exactly;",
        "the pure backend runs rule cases only (its arithmetic IS the reference).",
        "",
        "| Backend | Status | Truth cases pass | Rule cases pass | max abs Δ | s |",
        "| --- | --- | --- | --- | --- | --- |",
        *rows,
        "",
        "Pre-registered gate: 100% truth-value parity at eps 1e-6 on every available MeTTa "
        "backend; >=1 MeTTa backend required; unavailable backends reported as SKIPPED.",
        "",
        f"**GATE: {'PASSED' if not failures else 'FAILED'}**"
        + ("" if not failures else "\n\n" + "\n".join(f"- {f}" for f in failures)),
        "",
        "Reproduce: `$HYPERON_MCP_PY benchmarks/atomspace/nal_truth_benchmark.py` "
        "(HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python)",
        "",
    ])
    with open(os.path.join(_HERE, "nal_truth_results.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)

    if failures:
        print("\nT0.1 GATE: FAILED")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nT0.1 GATE: PASSED")


if __name__ == "__main__":
    main()
