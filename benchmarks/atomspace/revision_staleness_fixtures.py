"""T1.2 fixtures: knowledge-update cases for the revision_staleness benchmark.

Two kinds of "the world changed" (deterministic `random.Random(SEED)`):

  * revision (30) — the SAME canonical atom is re-asserted with new evidence.
    20 "correction" cases assert a WRONG low-confidence value first, then the
    CORRECT high-confidence value; 10 "refine" controls assert a correct value
    twice (so a no-update baseline is right there too — not a strawman). gold =
    the truth sign the authoritative evidence supports.
  * supersession (30) — a fact is retracted and replaced: old
    ``(Inheritance file:F module:legacy)`` -> new ``(Inheritance file:F module:core)``.
    gold current answer = only the NEW module is active.

The candidate is the product store (NAL revision on re-assert, retract-supersede).
The baseline is an append-only / no-merge / no-supersede memory: it keeps what it
learned first and never marks anything stale.
"""

import random

SEED = 2203


def build_cases(seed=SEED):
    rng = random.Random(seed)
    cases = []

    for i in range(20):   # correction: wrong-then-right
        c = f"(Evaluation (Predicate uses) (List module:m{i} dep:lib-{i}))"
        cases.append({"id": f"rev-wrong-{i:02d}", "kind": "revision", "canonical": c,
                      "first_stv": [round(rng.uniform(0.05, 0.25), 3), round(rng.uniform(0.2, 0.4), 3)],
                      "second_stv": [round(rng.uniform(0.85, 0.98), 3), round(rng.uniform(0.8, 0.9), 3)],
                      "gold_true": True})
    for i in range(10):   # refine control: right-then-right
        c = f"(Evaluation (Predicate uses) (List module:r{i} dep:lib-{i}))"
        cases.append({"id": f"rev-refine-{i:02d}", "kind": "revision", "canonical": c,
                      "first_stv": [round(rng.uniform(0.7, 0.85), 3), round(rng.uniform(0.5, 0.6), 3)],
                      "second_stv": [round(rng.uniform(0.85, 0.98), 3), round(rng.uniform(0.8, 0.9), 3)],
                      "gold_true": True})
    for i in range(30):   # supersession: the module moved
        f = f"file:src/pkg{i}/mod_{i}.py"
        cases.append({"id": f"super-{i:02d}", "kind": "supersession", "file": f,
                      "old": f"(Inheritance {f} module:legacy{i})",
                      "new": f"(Inheritance {f} module:core{i})",
                      "old_module": f"module:legacy{i}", "new_module": f"module:core{i}"})

    return cases


def cases_summary(cases=None):
    cases = cases or build_cases()
    by_kind = {}
    for c in cases:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    return {"n": len(cases), "seed": SEED, "by_kind": by_kind}


if __name__ == "__main__":
    import json
    print(json.dumps(cases_summary(), indent=2))
