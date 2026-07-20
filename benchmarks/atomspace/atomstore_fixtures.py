"""T0.2 fixtures: deterministic atom corpus generator for the AtomStore benchmark.

`build_corpus(n)` returns n UNIQUE atom records spanning all 5 whitelisted
schema heads (Inheritance / Implication / Similarity / Evaluation / Not) with
file:/module:/dep: namespaced terms, a provenance mix over all 5 source_types,
and ~5% of records marked for supersession. The only randomness is a seeded
`random.Random(1001)` — the corpus is replay-identical across runs/hosts.

Records: {atom, head, source_type, stv (or None -> provenance-derived),
supersede: bool}. Term groups (module:m<g>, dep clusters) are shared across
~n/GROUPS atoms so `store.by_terms` neighborhoods are non-trivial — that
sharing is what the re-transmission section measures.

Run with the Hyperon-MCP venv python:
    HYPERON_MCP_PY=/home/rojo-dev/Repos/Hyperon-MCP/.venv/bin/python
    $HYPERON_MCP_PY benchmarks/atomspace/atomstore_fixtures.py   # prints summary
"""

import random

SEED = 1001
GROUPS = 17          # term-sharing fan-in: ~n/17 atoms per module:m<g> group
SUPERSEDE_RATE = 0.05
SOURCE_TYPES = ("game_state", "user", "llm", "knowledge_prior", "tool_result")
HEADS = ("Inheritance", "Implication", "Similarity", "Evaluation", "Not")


def build_corpus(n, seed=SEED):
    """n unique, validator-clean atom records (deterministic for a given seed)."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        g = i % GROUPS
        head = HEADS[i % len(HEADS)]
        if head == "Inheritance":
            atom = f"(Inheritance file:src/pkg{g}/mod_{i}.py module:m{g})"
        elif head == "Implication":
            atom = (f"(Implication (affected file:src/pkg{g}/mod_{i}.py)"
                    f" (affected file:src/pkg{g}/mod_{i + 1}.py))")
        elif head == "Similarity":
            atom = f"(Similarity module:m{g} module:aux-{i})"
        elif head == "Evaluation":
            atom = (f"(Evaluation (Predicate depends-on)"
                    f" (List module:m{g} dep:pkg-{i}))")
        else:  # Not
            atom = (f"(Not (Evaluation (Predicate depends-on)"
                    f" (List module:m{g} dep:legacy-{i})))")
        stv = None
        if rng.random() < 0.5:  # half explicit stvs, half provenance-derived
            stv = (round(rng.uniform(0.05, 1.0), 4), round(rng.uniform(0.05, 0.99), 4))
        out.append({
            "atom": atom,
            "head": head,
            "source_type": rng.choice(SOURCE_TYPES),
            "stv": stv,
            "supersede": rng.random() < SUPERSEDE_RATE,
        })
    return out


def corpus_summary(n):
    corpus = build_corpus(n)
    by_head, by_source = {}, {}
    for rec in corpus:
        by_head[rec["head"]] = by_head.get(rec["head"], 0) + 1
        by_source[rec["source_type"]] = by_source.get(rec["source_type"], 0) + 1
    return {"n": n, "seed": SEED, "by_head": by_head, "by_source_type": by_source,
            "supersede_marked": sum(r["supersede"] for r in corpus),
            "explicit_stv": sum(r["stv"] is not None for r in corpus)}


if __name__ == "__main__":
    import json
    print(json.dumps({str(n): corpus_summary(n) for n in (1000, 10000)}, indent=2))
