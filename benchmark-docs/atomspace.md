# atomspace-agent — benchmark-gated roadmap (pre-registration)

Product: `atomspace_agent` (Hyperon-MCP) — persistent scoped AtomSpaces (SQLite
per scope) with PLN/NAL inference over the vendored `lib_nal.metta` /
`lib_pln.metta` on a hyperon backend, exposed to coding agents as 11 MCP tools.

## Purpose

Every tier of this roadmap is **benchmark-gated**: a capability ships only if a
pre-registered gate passes on a pre-registered corpus. The discipline comes
straight from the FreeCiv §3f lesson ([freeciv.md](freeciv.md#3f-statistical-batch-2026-07-16--17-20-seeds--null-result)):
after a promising 2–0 single-seed "win", a 20-seed statistical batch showed the
one-hop PLN treatment had **no measurable effect** (duel sign-test p=0.87 —
a coin flip). Small-N wins are noise; thin rule vocabularies don't change
decisions. Therefore:

* the program's primary claim is **decision-changing multi-hop reasoning
  against strong baselines** (T2.1) — not "inference ran", but "the answer
  flipped to correct, significantly, at pre-registered N";
* **cost and latency are hard gates**, not footnotes — a memory system that
  wins accuracy while blowing the token or wall-clock budget loses;
* T0 (this document's first filled-in tier) is the correctness floor: truth
  arithmetic, persistence, and the tool contract must be exact before any
  capability claim is even measured.

Gates below were written down **before** the corresponding runs. Failed gates
are reported as failed — they are never retro-fitted (§3f: "the earlier
'PLN 2–0' was noise").

## Gate pre-registration

All gates in this table were pre-registered BEFORE their runs.

| Tier | Benchmark | Pre-registered gate |
| --- | --- | --- |
| T0.1 | nal_truth | 100% truth-value parity at eps 1e-6 on every available MeTTa backend (>=1 required). |
| T0.2 | atomstore | fidelity 100%, cross-scope leakage 0, supersession-exclusion 100%, crash recovery clean, hydrate 1k<500ms / 10k<3s, premise re-transmission reduction >=90% vs stateless baseline. |
| T0.3 | mcp_conformance | 100% conformance, zero crashes, lossless 2-client interleaving, p95 <150ms excluding inference. |
| T1.1 | hybrid_retrieval | precision@5 >= baseline+0.15 abs AND recall@10 >= baseline, McNemar p<0.05 over >=60 queries; injected tokens <=1.5x baseline median. |
| T1.2 | revision_staleness | current-answer accuracy >=0.9 AND >= baseline+0.25; contradiction-leak <=5%. |
| T1.3 | scope_routing | cross-project leakage = 0 (hard); routing accuracy >=0.95. |
| T2.1 | multihop_impact (primary program gate) | exact-match >= baseline+0.25 abs; net decision-flips-to-correct >= +20/80; exact two-sided sign test p<0.05; median inference <2s. |
| T2.2 | llm_decision_ab | sign test p<0.05; net accuracy >= +10 pts; tokens <=1.25x; <= +2s median; N=120 cases x 3 seeds, mirror-pair ordering. |
| T3.1 | swebench_repo_stream | paired sign test p<0.05 on resolve rate (or pre-registered second-half-of-stream memory hypothesis); tokens <=1.2x; wall-clock <=1.3x. |
| T3.2 | longmem_coding | wins knowledge-update AND multi-session types, McNemar p<0.05 each (2-test corrected); no >3pt regression elsewhere; tokens <=1.25x. |

## T0 results

Runs of 2026-07-20 on the host Hyperon-MCP venv
(`/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python`, hyperon 0.2.10; PeTTa
backend unavailable on this host — reported SKIPPED, not silently dropped).
Full tables: `benchmarks/atomspace/*_results.md`.

| Tier | Result | Headline |
| --- | --- | --- |
| T0.1 nal_truth | **PASSED** | hyperon 236/236 truth + 4/4 rule cases at eps 1e-6 (max abs delta 3.1e-11) on the host; pure backend 3/3 rule cases (arrow-form NAL skipped by design). PeTTa is **SKIPPED in the committed (host) results table** (`nal_truth_results.*`, backend unavailable on that host); a separate in-container run (2026-07-23) verified petta parity (236/236 truth + 4/4 rule cases, max abs delta 3.08e-11) — see the "PeTTa parity" note below. Regenerate the results table in-container to fold petta into it. |
| T0.2 atomstore | **PASSED** | fidelity 1000/1000 (100%); 0/1320 cross-scope leaks; 67/67 supersession excluded-by-default AND visible-on-request; crash recovery clean (integrity_check=ok, 250/250 rows after os._exit(1)); hydrate 1k=4.6ms, 10k=44.5ms; re-transmission reduction 93.3% (1k) / 95.4% (10k). |
| T0.3 mcp_conformance | **PASSED** (first run FAILED; product fixed, gate held) | Final: 52/52 cases; worst tool p95 8.0ms << 150ms gate; stdio transport ok (11 tools via real MCP initialize/list/call); interleaving 3/3 lossless trials. |

T0.3 history — the gate did its job. The FIRST run FAILED (51/52 cases,
interleaving 0/3 lossless) on three product defects: (1) `atom_assert` RAISED
ValueError on unknown source_type instead of returning a structured error;
(2) concurrent first-open of a new scope DB raced `PRAGMA journal_mode=WAL`
("database is locked"); (3) concurrent duplicate asserts raced
SELECT-then-INSERT to a UNIQUE-constraint IntegrityError — breaking the
store's "concurrent duplicate asserts converge" contract. Per this document's
discipline the gate was **not** weakened: Hyperon-MCP was fixed (a
`_tool_errors` structured-error decorator on every handler; a retry loop
around fresh-DB WAL init; `BEGIN IMMEDIATE` write transactions serializing
read-modify-write) and the suite re-run unchanged — except one fixture whose
*expectation* encoded the old silent-fallback behavior for invalid explicit
scope keys; the fixed product now returns a structured error there, which the
fixture now requires.

PeTTa parity (2026-07-23) — the register's #1 risk ("hyperon/PeTTa drift
unverified in practice") is now closed, but only after the gate exposed two real
product defects the earlier host-only runs could not: (1) `lib_compat.metta`
defined binary `min`/`max` for hyperon, which PeTTa rejects as `No permission to
modify static procedure min/3` and aborts the whole program — fixed by making
the shim backend-conditional (`lib_source(minmax_shim=False)` for the PeTTa
backend; the vendored lib_nal/lib_pln stay byte-identical); (2) the
`PettaSubprocessBackend` output parser expected a bracketed `[...]` result form,
while this PeTTa (swipl) build emits ANSI-coloured translation noise followed by
bare `(atom (stv f c))` / scalar result lines after a `^^^^` goal terminator —
fixed to strip ANSI and harvest post-marker result lines (product `_run_program`
and the benchmark's truth-case `_petta_runner`). Reproduce with
`scripts/petta_parity.sh` (host-side, spins a throwaway OmegaClaw container).

## T1 results

Runs of 2026-07-23 on the same host venv. Host-runnable and deterministic (no
LLM). Full tables: `benchmarks/atomspace/{hybrid_retrieval,revision_staleness,scope_routing}_results.md`.

| Tier | Result | Headline |
| --- | --- | --- |
| T1.1 hybrid_retrieval | **PASSED** | precision@5 candidate 0.5625 vs baseline 0.40 (delta **+0.1625** >= +0.15); recall@10 1.0 vs 0.729; exact McNemar (b=65, c=0) **p = 4.9e-13** < 0.05 over 80 queries; injected tokens **x1.10** <= 1.5x. |
| T1.2 revision_staleness | **PASSED** | current-answer accuracy **1.0** (>= 0.9) vs baseline 0.167 (delta **+0.833** >= +0.25); contradiction-leak **0.0** (<= 0.05) vs baseline 0.833, over 60 knowledge-update cases (30 revision + 30 supersession). |
| T1.3 scope_routing | **PASSED** | routing accuracy **1.0** (48/48 cwd probes across 6 repos incl. a clone sharing a remote, a no-remote repo, a non-git dir) >= 0.95; cross-project leakage **0** / 300 cross-scope lookups (hard gate). |

T1.1's candidate is `hybrid_recall` (lexical recall + 1-hop PLN); its edge is a
transitive `(affected ..)` edge that is never stored, surfaced only by inference.
Both arms inject the same 5-atom budget (the candidate spends one slot on its top
inferred fact), which is why the token multiplier stays at 1.10x. The fixtures
place lexical distractors on the chain ENDPOINTS but not its middle join node —
a distractor on the join term would trip the inference engine's common-term
pruning and suppress the very deduction under test (a real product behaviour the
fixture documents rather than hides). T1.2's baseline is an append-only /
no-supersede memory; T1.3's leakage section drives the T0.2 isolation check
through `resolve()`/`db_path()` auto-routing rather than hand-picked keys.

## T2 results

Runs of 2026-07-23 on the same host venv (hyperon 0.2.10; in-process inference
so all 80 cases share one warm runtime — the pre-registered latency basis).
Full table: `benchmarks/atomspace/multihop_impact_results.md`.

| Tier | Result | Headline |
| --- | --- | --- |
| T2.1 multihop_impact | **PASSED** | exact-match PLN 1.0 vs baseline 0.50 (delta **+0.50** >= +0.25); net decision-flips-to-correct **+40/80** (40 to-correct, 0 to-wrong) >= +20; exact two-sided sign test **p = 1.8e-12** < 0.05; median inference **108 ms** < 2s. |

The 80 cases pre-register four families (`multihop_impact_fixtures.py`,
`random.Random(2101)`): 25 direct-positive + 15 negative controls (where the
retrieval baseline is *correct* — proving it is not a strawman: baseline exact
= 40/80 = 0.50), 25 impact-chain (2–3 edge `(Implication (affected ..) ..)`
deductions to a never-stored composed edge), and 15 invariant (a
variable-carrying rule that cannot be a stored atom). Both arms receive the
identical premises and the identical trusted rule text; the baseline
(`bridge.lexical_recall` + unify, no inference) structurally cannot return a
composed/derived edge, so every multihop case is a decision-flip.

The invariant family forced the one real feature gap and its fix: the store
firewall rightly bans `$vars`, so universally-quantified invariants ("a handler
that reads secrets requires an auth-check") cannot be stored atoms. They are now
expressed as **trusted `code_rules`** — a committed `.atomspace/code_rules.metta`
loaded into the runtime as `(= (|~code ...) ...)` equations (the trusted
channel, never through `validate_atom`), linted by `validate.validate_code_rules`
(top-level forms must define only the dedicated `|~code`/`|-code` heads; no I/O,
space-mutation, or py-escape tokens). Measured in two pre-registered modes: with
the vendored PLN engine ALONE the invariant family is 0/15 (delta still +0.31,
net +25 — the gate passes on deduction alone) and with `code_rules` loaded it is
15/15 (delta +0.50, net +40). The gate was not weakened by the mechanism; the
mechanism widened an already-passing margin and closed the invariant class. T0.1
truth parity was re-run unchanged after the inference-layer change (hop-1
single-premise application over seed premises) and still PASSES 236/236.

## Methodology notes

* **Statistics re-use the FreeCiv batch machinery**
  (`benchmarks/freeciv/batch/aggregate.py`): exact two-sided **sign tests** for
  paired win/loss designs (T2.1, T2.2, T3.1), **McNemar** for paired
  per-item correct/incorrect flips (T1.1, T3.2), with the multi-test
  corrections stated in the gate (T3.2 is 2-test corrected).
* **Mirror pairs** (T2.2): every A/B case runs in both orders
  (memory-first / baseline-first) to cancel ordering and prompt-position
  effects — the same design as the FreeCiv duel mirror slots.
* **Pre-registered N**: T2.1 uses 80 decision cases, T2.2 uses 120 cases x 3
  seeds, T1.1 uses >=60 queries. Batches are seeded and replay-deterministic;
  underpowered "strong signals" are recorded but never promoted to claims
  (§3f).
* **Baselines are strong**: T1.1's baseline is lexical/vector recall without
  atoms; T2.x baselines get the same context budget and the same premises
  inline (stateless), so the candidate's only edge is persistence + inference.
* **Cost accounting**: token multipliers are measured on the full round-trip
  (injected premises + tool results), wall-clock on the same host, medians
  over the batch.
* T0 benchmarks are deterministic (seeded corpora, golden values from the
  product's `truth.py`); latency gates are the only timing-sensitive parts and
  carry order-of-magnitude headroom on this host.
