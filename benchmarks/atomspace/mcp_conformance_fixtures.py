"""T0.3 fixtures: scripted tool-surface conformance cases.

`build_cases(ctx)` returns an ORDERED pipeline of ~50 cases covering all 11
transport-agnostic tool handlers (`atomspace_agent.tools`): atom_assert,
atom_assert_batch, atom_query, infer, revise, atom_retract, scope_info,
hybrid_recall, bootstrap_project, snapshot_export, snapshot_import. Order
matters — later cases depend on state earlier cases created (dup/revised
statuses, contradiction surfacing, supersession visibility, export->import).

Each case: {name, tool, kwargs, expect} where expect is declarative:
  ok               required boolean
  keys             keys that must be present in the result
  status           expected result["status"] (str or list of alternatives)
  equals           {key: value} exact matches
  error_contains   substring of result["error"]
  hint             True -> a non-empty repair hint must be present
  check            callable(result) -> list of failure strings (custom)
No tool call may RAISE: a raised exception is recorded by the harness as a
crash (gate: zero crashes), regardless of the case's expect block.

INJECTIONS below is the firewall corpus from Hyperon-MCP tests/test_core.py —
every entry must come back as a structured error with a repair hint.

ctx keys (provided by the benchmark): proj, proj2 (never written), proj4
(tiny scope for hybrid_recall latency), tmp, repo (git repo to bootstrap),
nonrepo (plain dir), hostile_seed (path to a seed file with an injection).

Run with the Hyperon-MCP venv python:
    HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python
"""

import os

# Explicit 12-hex project scope keys (scopes.resolve accepts these directly).
PROJ = "beefbeefbeef"    # main pipeline scope
PROJ2 = "cafecafecafe"   # stays EMPTY: empty-scope infer / hybrid_recall
PROJ4 = "ace0ace0ace0"   # tiny 2-atom scope: hybrid_recall latency case
INTERLEAVE_SCOPE = "feedfeedfeed"  # used by the 2-client interleaving section

# Firewall corpus — verbatim from Hyperon-MCP tests/test_core.py INJECTIONS.
INJECTIONS = [
    ("inject-pycall", "(Implication (py-call os.system) (affected file:x))"),
    ("inject-import", "(Evaluation (Predicate x) (List (import! &self evil)))"),
    ("inject-equation", "(Inheritance (= (foo) bar) module:x)"),
    ("inject-superpose", "(Implication (superpose a) (affected b))"),
    ("inject-bind", "(Evaluation (Predicate bind!) (List a b))"),
    ("inject-exec-bang", "(Inheritance !exec module:x)"),
    ("inject-smuggle-trailing", "(Inheritance a b) (Inheritance c d)"),
    ("inject-bad-head", "(Recommend city defend)"),
    ("inject-var-in-stored", "(Inheritance $x module:y)"),
    ("inject-bad-arity", "(Not a b)"),
]

CHAIN_A = "(Implication (affected file:chain/a.py) (affected file:chain/b.py))"
CHAIN_B = "(Implication (affected file:chain/b.py) (affected file:chain/c.py))"
CHAIN_TRANSITIVE = "(Implication (affected file:chain/a.py) (affected file:chain/c.py))"


def build_cases(ctx):
    tmp = ctx["tmp"]
    seed_path = os.path.join(tmp, "seed.metta")
    cases = [
        # --- atom_assert: happy path + statuses -----------------------------
        {"name": "assert-added", "tool": "atom_assert",
         "kwargs": {"atom": "(Inheritance file:core/api.py module:core)",
                    "scope": PROJ, "source_type": "user"},
         "expect": {"ok": True, "status": "added", "keys": ["id", "stv", "scope"]}},
        {"name": "assert-dup", "tool": "atom_assert",
         "kwargs": {"atom": "(Inheritance file:core/api.py module:core)",
                    "scope": PROJ, "source_type": "user"},
         "expect": {"ok": True, "status": "dup"}},
        {"name": "assert-conflict-revised", "tool": "atom_assert",
         "kwargs": {"atom": "(Inheritance file:core/api.py module:core)",
                    "scope": PROJ, "stv": [0.1, 0.8], "source_type": "user"},
         "expect": {"ok": True, "status": "revised", "keys": ["prior_stv"],
                    "equals": {"conflict": True}}},
        {"name": "assert-explicit-stv", "tool": "atom_assert",
         "kwargs": {"atom": "(Similarity module:core module:api)",
                    "scope": PROJ, "stv": [0.9, 0.8]},
         "expect": {"ok": True, "status": "added", "equals": {"stv": [0.9, 0.8]}}},
        {"name": "assert-chain-1", "tool": "atom_assert",
         "kwargs": {"atom": CHAIN_A, "scope": PROJ, "source_type": "tool_result"},
         "expect": {"ok": True, "status": "added"}},
        {"name": "assert-chain-2", "tool": "atom_assert",
         "kwargs": {"atom": CHAIN_B, "scope": PROJ, "source_type": "tool_result"},
         "expect": {"ok": True, "status": "added"}},
        {"name": "assert-global-scope", "tool": "atom_assert",
         "kwargs": {"atom": "(Inheritance file:global-note.md module:global-conventions)",
                    "scope": "global", "source_type": "knowledge_prior"},
         "expect": {"ok": True, "status": "added", "equals": {"scope": "global"}}},
        {"name": "assert-p4-edge", "tool": "atom_assert",
         "kwargs": {"atom": "(Implication (affected file:h4/x.py) (affected file:h4/y.py))",
                    "scope": PROJ4, "source_type": "tool_result"},
         "expect": {"ok": True, "status": "added"}},
        {"name": "assert-p4-tree", "tool": "atom_assert",
         "kwargs": {"atom": "(Inheritance file:h4/x.py module:h4)",
                    "scope": PROJ4, "source_type": "tool_result"},
         "expect": {"ok": True, "status": "added"}},
    ]

    # --- atom_assert: firewall (structured error + repair hint, never raise) --
    for name, atom in INJECTIONS:
        cases.append({"name": f"assert-{name}", "tool": "atom_assert",
                      "kwargs": {"atom": atom, "scope": PROJ},
                      "expect": {"ok": False, "hint": True}})

    cases += [
        {"name": "assert-empty-atom", "tool": "atom_assert",
         "kwargs": {"atom": "", "scope": PROJ},
         "expect": {"ok": False, "error_contains": "empty", "hint": True}},
        {"name": "assert-bad-stv-range", "tool": "atom_assert",
         "kwargs": {"atom": "(Inheritance file:stv/r.py module:stv)",
                    "scope": PROJ, "stv": [1.5, 0.5]},
         "expect": {"ok": False, "error_contains": "within [0, 1]"}},
        {"name": "assert-bad-stv-type", "tool": "atom_assert",
         "kwargs": {"atom": "(Inheritance file:stv/t.py module:stv)",
                    "scope": PROJ, "stv": ["x", 0.5]},
         "expect": {"ok": False, "error_contains": "numbers"}},
        # Failure taxonomy: an unknown source_type must be a STRUCTURED error,
        # not an exception — the harness treats a raise as a crash.
        {"name": "assert-bad-source-type", "tool": "atom_assert",
         "kwargs": {"atom": "(Inheritance file:src/ok.py module:ok)",
                    "scope": PROJ, "source_type": "wizard"},
         "expect": {"ok": False, "error_contains": "source_type"}},

        # --- atom_assert_batch ------------------------------------------------
        {"name": "batch-mixed", "tool": "atom_assert_batch",
         "kwargs": {"atoms": ["(Inheritance file:batch/a.py module:batch)",
                              "(Recommend x y)",
                              {"atom": "(Inheritance file:batch/b.py module:batch)",
                               "stv": [0.7, 0.6]}],
                    "scope": PROJ, "source_type": "tool_result"},
         "expect": {"ok": True, "keys": ["summary", "results"],
                    "check": lambda r: (
                        [] if (r["summary"]["rejected"] == 1
                               and r["summary"]["added"] + r["summary"]["dup"] == 2)
                        else [f"batch summary off: {r['summary']}"])}},
        {"name": "batch-empty-list", "tool": "atom_assert_batch",
         "kwargs": {"atoms": [], "scope": PROJ},
         "expect": {"ok": True,
                    "check": lambda r: [] if sum(r["summary"].values()) == 0
                    else [f"non-zero summary for empty batch: {r['summary']}"]}},

        # --- atom_query --------------------------------------------------------
        {"name": "query-vars-bindings", "tool": "atom_query",
         "kwargs": {"pattern": "(Inheritance $f module:core)", "scope": PROJ,
                    "include_global": False},
         "expect": {"ok": True,
                    "check": lambda r: (
                        [] if r["matches"] and all("$f" in m["bindings"] for m in r["matches"])
                        else [f"expected >=1 match with $f binding, got {r['matches']}"])}},
        {"name": "query-ground-exact", "tool": "atom_query",
         "kwargs": {"pattern": "(Inheritance file:core/api.py module:core)",
                    "scope": PROJ, "include_global": False},
         "expect": {"ok": True,
                    "check": lambda r: [] if len(r["matches"]) == 1
                    else [f"expected exactly 1 match, got {len(r['matches'])}"]}},
        {"name": "query-no-match", "tool": "atom_query",
         "kwargs": {"pattern": "(Inheritance file:none.py module:nowhere)",
                    "scope": PROJ, "include_global": False},
         "expect": {"ok": True, "equals": {"matches": []}}},
        {"name": "query-global-union", "tool": "atom_query",
         "kwargs": {"pattern": "(Inheritance $f module:global-conventions)",
                    "scope": PROJ, "include_global": True},
         "expect": {"ok": True,
                    "check": lambda r: (
                        [] if any(m["scope"] == "global" for m in r["matches"])
                        else [f"global union missing: {r['matches']}"])}},
        {"name": "query-malformed-pattern", "tool": "atom_query",
         "kwargs": {"pattern": "(Inheritance file:x", "scope": PROJ},
         "expect": {"ok": False, "hint": True}},
        # Unknown scope key format: implemented behavior is a SILENT fallback to
        # An explicit-but-invalid scope key must be a structured error (fixed in
        # Hyperon-MCP after the first T0.3 run flagged the silent cwd fallback).
        {"name": "query-unknown-scope-format", "tool": "atom_query",
         "kwargs": {"pattern": "(Inheritance $f module:core)",
                    "scope": "not-a-valid-scope!", "cwd": ctx["nonrepo"]},
         "expect": {"ok": False, "error_contains": "invalid scope"}},

        # --- revise ------------------------------------------------------------
        {"name": "revise-existing", "tool": "revise",
         "kwargs": {"atom": "(Similarity module:core module:api)",
                    "stv": [0.4, 0.9], "scope": PROJ},
         "expect": {"ok": True, "status": "revised", "keys": ["prior_stv"]}},
        {"name": "revise-new-atom", "tool": "revise",
         "kwargs": {"atom": "(Inheritance file:revise/new.py module:revise)",
                    "stv": [0.8, 0.7], "scope": PROJ},
         "expect": {"ok": True, "status": "added"}},

        # --- atom_retract + supersession visibility ----------------------------
        {"name": "retract-existing", "tool": "atom_retract",
         "kwargs": {"atom_or_id": "(Inheritance file:batch/a.py module:batch)",
                    "scope": PROJ, "reason": "benchmark retraction"},
         "expect": {"ok": True, "equals": {"retracted": True}}},
        {"name": "retract-missing", "tool": "atom_retract",
         "kwargs": {"atom_or_id": "(Inheritance file:never/asserted.py module:none)",
                    "scope": PROJ},
         "expect": {"ok": True, "equals": {"retracted": False}}},
        {"name": "retract-invalid-atom", "tool": "atom_retract",
         "kwargs": {"atom_or_id": "(Recommend x y)", "scope": PROJ},
         "expect": {"ok": False, "hint": True}},
        {"name": "query-superseded-visible", "tool": "atom_query",
         "kwargs": {"pattern": "(Inheritance file:batch/a.py module:batch)",
                    "scope": PROJ, "include_superseded": True, "include_global": False},
         "expect": {"ok": True,
                    "check": lambda r: (
                        [] if len(r["matches"]) == 1 and r["matches"][0]["superseded"]
                        else [f"superseded atom not visible on request: {r['matches']}"])}},
        {"name": "query-superseded-excluded", "tool": "atom_query",
         "kwargs": {"pattern": "(Inheritance file:batch/a.py module:batch)",
                    "scope": PROJ, "include_global": False},
         "expect": {"ok": True, "equals": {"matches": []}}},

        # --- scope_info ---------------------------------------------------------
        {"name": "scope-info-project", "tool": "scope_info",
         "kwargs": {"scope": PROJ},
         "expect": {"ok": True, "keys": ["atom_counts", "contradictions"],
                    "check": lambda r: (
                        ([] if r["atom_counts"]["total"] >= 5 else
                         [f"total {r['atom_counts']['total']} < 5"])
                        + ([] if r["contradictions"] else
                           ["assert-conflict-revised's f-divergence not surfaced "
                            "in contradictions"]))}},
        {"name": "scope-info-global", "tool": "scope_info",
         "kwargs": {"scope": "global"},
         "expect": {"ok": True, "keys": ["atom_counts"],
                    "check": lambda r: [] if isinstance(r.get("registry"), dict)
                    else [f"global registry missing: {r.get('registry')!r}"]}},

        # --- hybrid_recall -------------------------------------------------------
        {"name": "hybrid-recall-hit", "tool": "hybrid_recall",
         "kwargs": {"text": "which files are affected by h4 x.py", "scope": PROJ4, "k": 3},
         "expect": {"ok": True, "keys": ["symbolic", "derived", "text"],
                    "check": lambda r: [] if r["symbolic"]
                    else [f"no symbolic recall: {r['text']!r}"]}},
        {"name": "hybrid-recall-empty-scope", "tool": "hybrid_recall",
         "kwargs": {"text": "anything at all", "scope": PROJ2, "k": 3},
         "expect": {"ok": True, "equals": {"symbolic": [], "text": "NO_ATOMS_FOUND"}}},

        # --- infer (latency-exempt; the pre-registered p95 gate excludes it) -----
        {"name": "infer-two-hop", "tool": "infer",
         "kwargs": {"query": "(Implication (affected file:chain/a.py) $x)",
                    "scope": PROJ, "max_hops": 2, "min_confidence": 0.1},
         "expect": {"ok": True, "keys": ["matched", "conclusions", "stats"],
                    "check": lambda r: (
                        [] if any(m["atom"] == CHAIN_TRANSITIVE and m["hop"] >= 1
                                  for m in r["matched"])
                        else [f"2-hop {CHAIN_TRANSITIVE} not derived; "
                              f"matched={[m['atom'] for m in r['matched']]}"])}},
        {"name": "infer-empty-scope", "tool": "infer",
         "kwargs": {"query": "(Implication (affected file:chain/a.py) $x)",
                    "scope": PROJ2, "max_hops": 2},
         "expect": {"ok": True, "equals": {"matched": []}}},
        {"name": "infer-malformed-query", "tool": "infer",
         "kwargs": {"query": "(((", "scope": PROJ},
         "expect": {"ok": False, "hint": True}},

        # --- bootstrap_project (latency-exempt) -----------------------------------
        {"name": "bootstrap-tmp-repo", "tool": "bootstrap_project",
         "kwargs": {"repo_root": ctx["repo"]},
         "expect": {"ok": True, "keys": ["report"],
                    "check": lambda r: (
                        [] if (r["report"]["tree"] >= 2 and r["report"]["imports"] >= 1
                               and "seed_path" in r["report"])
                        else [f"bootstrap report thin: {r['report']}"])}},
        {"name": "bootstrap-no-repo", "tool": "bootstrap_project",
         "kwargs": {"cwd": ctx["nonrepo"]},
         "expect": {"ok": False, "error_contains": "no git repository"}},

        # --- snapshot_export / snapshot_import -------------------------------------
        {"name": "export-metta-path", "tool": "snapshot_export",
         "kwargs": {"scope": PROJ, "fmt": "metta", "path": seed_path},
         "expect": {"ok": True, "equals": {"path": seed_path}}},
        {"name": "export-jsonl-content", "tool": "snapshot_export",
         "kwargs": {"scope": PROJ, "fmt": "jsonl"},
         "expect": {"ok": True, "keys": ["content"],
                    "check": lambda r: [] if "file:core/api.py" in r["content"]
                    else ["exported jsonl missing an asserted atom"]}},
        {"name": "import-roundtrip", "tool": "snapshot_import",
         "kwargs": {"path": seed_path, "scope": PROJ},
         "expect": {"ok": True, "keys": ["added", "dup", "revised", "rejected", "total"],
                    "check": lambda r: (
                        ([] if r["total"] > 0 and not r["rejected"] else
                         [f"roundtrip import: total={r['total']} rejected={r['rejected']}"])
                        + ([] if r["added"] + r["dup"] + r["revised"] == r["total"] else
                           [f"import counts do not add up: {r}"]))}},
        {"name": "import-missing-file", "tool": "snapshot_import",
         "kwargs": {"path": os.path.join(tmp, "does-not-exist.metta"), "scope": PROJ},
         "expect": {"ok": False, "error_contains": "cannot read"}},
        {"name": "import-hostile-seed", "tool": "snapshot_import",
         "kwargs": {"path": ctx["hostile_seed"], "scope": PROJ},
         "expect": {"ok": True,
                    "check": lambda r: (
                        ([] if len(r["rejected"]) == 1 else
                         [f"hostile line not rejected: {r['rejected']}"])
                        + ([] if r["added"] + r["dup"] + r["revised"] >= 1 else
                           ["good line not imported"]))}},
    ]
    return cases


HOSTILE_SEED = "\n".join([
    ";; hostile seed: one good atom, one grounded-operation injection",
    "((Inheritance file:seed/good.py module:seed) (stv 0.9 0.8))",
    "((Implication (py-call os.system) (affected file:x)) (stv 1.0 0.9))",
    "",
])
