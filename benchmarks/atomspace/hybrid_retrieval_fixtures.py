"""T1.1 fixtures: retrieval queries for the hybrid_retrieval benchmark.

Each query has its OWN isolated per-query store (so lexical scoring never
crosses queries) seeded with a small impact graph, and a gold set of the atoms
a caller should get back. The discriminating gold member (`key_gold`) of a
hop-required query is a transitive `(Implication (affected ..) (affected ..))`
edge that is NEVER stored — only 1-hop PLN deduction over the stored edges
surfaces it, so `hybrid_recall` (recall + 1-hop inference) can return it and
`lexical_recall` structurally cannot.

Families (N=80, `random.Random(SEED)`):
  * 65 hop-required — a 2-edge chain a->b->c + lexical distractors. gold =
    {edge(a,b), edge(b,c), derived(a,c)}; key_gold = derived(a,c). Baseline
    retrieves the two stored edges (a STRONG baseline: 2/3 recall) but misses
    the transitive fact; the candidate gets all three.
  * 15 lexical-only — gold is two directly-stored atoms, key_gold is one of
    them. Both arms retrieve it (concordant control: the candidate must not
    *lose* on plain lexical queries, and the baseline is demonstrably not a
    strawman).
"""

import random

SEED = 2202


def _impl(a, b):
    return f"(Implication (affected {a}) (affected {b}))"


def build_queries(seed=SEED):
    rng = random.Random(seed)
    out = []

    for i in range(65):
        p = f"q{i}"
        a, b, c = (f"file:src/{p}/auth_{i}.py", f"file:src/{p}/session_{i}.py",
                   f"file:src/{p}/api_{i}.py")
        edge0, edge1 = _impl(a, b), _impl(b, c)
        derived = _impl(a, c)
        # Lexically-matching distractors: they share query tokens (the ENDPOINT
        # file names auth_i / api_i) so the BASELINE also fills a full top-5 of
        # plausible atoms — it is not a strawman that returns fewer results.
        # They deliberately avoid the chain's MIDDLE node (session_i): a
        # distractor on the join term would push it past the inference engine's
        # common-term pruning threshold and suppress the very deduction under
        # test. None is an impact edge, so none is gold; the transitive
        # derived(a,c) is the only atom that answers "what does changing a reach".
        distractors = [
            f"(Inheritance {a} module:{p}svc)",
            f"(Evaluation (Predicate handles) (List {c} user))",
            f"(Similarity {a} file:src/{p}/helper_{i}.py)",
            f"(Inheritance {c} module:{p}svc)",
        ]
        atoms = [edge0, edge1] + distractors
        rng.shuffle(atoms)
        text = f"{p} change impact of auth_{i} session_{i} api_{i} blast radius"
        out.append({
            "id": f"hop-{i:02d}", "family": "hop-required", "text": text,
            "atoms": atoms, "gold": [edge0, edge1, derived], "key_gold": derived,
        })

    for i in range(15):
        p = f"lx{i}"
        g0 = f"(Inheritance file:src/{p}/svc_{i}.py module:{p}core)"
        g1 = f"(Evaluation (Predicate depends-on) (List module:{p}core dep:{p}lib))"
        distractors = [f"(Similarity module:{p}core module:{p}aux)",
                       f"(Inheritance file:src/{p}/other_{i}.py module:{p}misc)"]
        atoms = [g0, g1] + distractors
        rng.shuffle(atoms)
        text = f"{p} svc_{i} depends {p}core {p}lib module"
        out.append({
            "id": f"lex-{i:02d}", "family": "lexical-only", "text": text,
            "atoms": atoms, "gold": [g0, g1], "key_gold": g0,
        })

    return out


def queries_summary(queries=None):
    queries = queries or build_queries()
    by_family = {}
    for q in queries:
        by_family[q["family"]] = by_family.get(q["family"], 0) + 1
    return {"n": len(queries), "seed": SEED, "by_family": by_family}


if __name__ == "__main__":
    import json
    print(json.dumps(queries_summary(), indent=2))
