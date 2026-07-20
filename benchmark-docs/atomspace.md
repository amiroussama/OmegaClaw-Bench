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
| T0.1 nal_truth | **PASSED** | hyperon 236/236 truth cases + 4/4 rule cases at eps 1e-6 (max abs delta 3.1e-11); pure backend 3/3 rule cases (arrow-form NAL skipped by design); petta SKIPPED. |
| T0.2 atomstore | **PASSED** | fidelity 1000/1000 (100%); 0/1320 cross-scope leaks; 67/67 supersession excluded-by-default AND visible-on-request; crash recovery clean (integrity_check=ok, 250/250 rows after os._exit(1)); hydrate 1k=4.4ms, 10k=43.7ms; re-transmission reduction 93.3% (1k) / 95.4% (10k). |
| T0.3 mcp_conformance | **PASSED** (first run FAILED; product fixed, gate held) | Final: 52/52 cases; worst tool p95 4.7ms << 150ms gate; stdio transport ok (11 tools via real MCP initialize/list/call); interleaving 3/3 lossless trials. |

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
