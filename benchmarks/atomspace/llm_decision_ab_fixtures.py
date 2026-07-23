"""T2.2 fixtures: decision cases + prompt rendering for the LLM A/B.

Same decision substrate as T2.1 (multihop_impact) but scaled to the
pre-registered N=120 and rendered for an LLM. Each case is a yes/no decision;
the two arms differ ONLY in the context they receive:

  * plain arm  — the ground premises as text (stateless, no atomspace).
  * memory arm — the same premises PLUS the atomspace's DERIVED conclusions
    (PLN/NAL chaining + trusted code_rules), i.e. the symbolic reasoning done
    for the model.

Three seeds re-paraphrase the question and shuffle premise order to expose the
result to prompt-surface variance (the gate is N=120 x 3 seeds).
"""

import random

from multihop_impact_fixtures import CODE_RULES, _INVARIANTS, _impl  # noqa: F401

SEED = 2205
N = 120
_HIGH = (0.95, 0.9)


def build_cases(seed):
    """120 decision cases for one seed (40 direct / 40 impact-chain / 20 invariant
    / 20 negative). Premise order and question phrasing vary with the seed."""
    rng = random.Random(seed)
    cases = []

    for i in range(40):
        a, b = f"file:src/s{seed}/d{i}_x.py", f"file:src/s{seed}/d{i}_y.py"
        atom = _impl(a, b)
        cases.append(_mk(f"direct-{i}", "direct", [(atom, _HIGH)], atom, True))

    for i in range(40):
        length = 2 if i % 2 == 0 else 3
        ns = [f"file:src/s{seed}/c{i}_{k}.py" for k in range(length + 1)]
        prem = [(_impl(ns[k], ns[k + 1]), _HIGH) for k in range(length)]
        rng.shuffle(prem)
        cases.append(_mk(f"impact-{i}", "multihop", prem, _impl(ns[0], ns[-1]), True))

    for i in range(20):
        role, pred, obj, ctrl = _INVARIANTS[i % len(_INVARIANTS)]
        x = f"file:src/s{seed}/i{i}.py"
        prem = [(f"(Inheritance {x} {role})", _HIGH),
                (f"(Evaluation (Predicate {pred}) (List {x} {obj}))", _HIGH)]
        rng.shuffle(prem)
        q = f"(Evaluation (Predicate requires) (List {x} {ctrl}))"
        cases.append(_mk(f"invariant-{i}", "multihop", prem, q, True))

    for i in range(20):
        c1 = [f"file:src/s{seed}/nA{i}_{k}.py" for k in range(3)]
        c2 = [f"file:src/s{seed}/nB{i}_{k}.py" for k in range(3)]
        prem = [(_impl(c1[0], c1[1]), _HIGH), (_impl(c1[1], c1[2]), _HIGH),
                (_impl(c2[0], c2[1]), _HIGH), (_impl(c2[1], c2[2]), _HIGH)]
        rng.shuffle(prem)
        cases.append(_mk(f"negative-{i}", "negative", prem, _impl(c1[0], c2[2]), False))

    rng.shuffle(cases)
    return cases


def _mk(cid, kind, premises, question, gold):
    return {"id": cid, "kind": kind, "premises": [[p, list(s)] for p, s in premises],
            "question": question, "gold": gold}


def render_premises(case):
    return "\n".join(f"- {p} (stv {s[0]} {s[1]})" for p, s in case["premises"])


def render_derived(derived):
    if not derived:
        return "(none)"
    return "\n".join(f"- {d['atom']} (stv {d['stv'][0]:.3f} {d['stv'][1]:.3f})" for d in derived)


SYSTEM_PROMPT = (
    "You are a code-reasoning assistant. You are given KNOWN FACTS about a codebase as "
    "symbolic atoms with truth values (stv frequency confidence). Decide whether the QUESTION "
    "atom is TRUE — i.e. entailed by the facts (directly, by transitive impact chaining over "
    "(Implication (affected ..) (affected ..)) edges, or by a stated invariant). Answer with "
    "ONLY a JSON object: {\"answer\": \"YES\"} or {\"answer\": \"NO\"}. Answer NO if it is not "
    "entailed."
)


def user_prompt(case, arm, derived, seed):
    q = case["question"]
    phrasings = [
        f"QUESTION: is this atom true given the facts?\n{q}",
        f"QUESTION: does the codebase entail the following atom?\n{q}",
        f"QUESTION: should you treat this atom as established?\n{q}",
    ]
    parts = ["KNOWN FACTS:", render_premises(case)]
    if arm == "memory":
        parts += ["", "DERIVED (atomspace PLN/NAL + code_rules reasoning):", render_derived(derived)]
    parts += ["", phrasings[seed % len(phrasings)]]
    return "\n".join(parts)


def cases_summary():
    cs = build_cases(SEED)
    by_kind = {}
    for c in cs:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    return {"n_per_seed": len(cs), "by_kind": by_kind, "seed_base": SEED}


if __name__ == "__main__":
    import json
    print(json.dumps(cases_summary(), indent=2))
