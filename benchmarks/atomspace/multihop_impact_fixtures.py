"""T2.1 fixtures: decision cases for the multihop_impact benchmark.

The primary program gate measures whether multi-hop PLN chaining changes
DECISIONS a strong retrieval baseline gets wrong. Each case is a yes/no
decision over a seeded per-case store, where the correct answer is reachable by
inference (PLN deduction, or a trusted `code_rules` invariant) but NOT by
retrieval alone — the answer atom is never stored, only its premises are.

Case families (N=80, pre-registered, deterministic `random.Random(SEED)`):

  * 25 direct-positive  — the answer atom IS stored (a 1-hop/hop-0 fact).
    Baseline retrieves it -> YES; PLN matches it -> YES. Control proving the
    baseline is not broken.
  * 25 impact-chain      — a 2-3 edge `(Implication (affected ..) (affected ..))`
    chain to a NEVER-STORED composed edge. Baseline can't compose -> NO (wrong);
    PLN deduction chains it -> YES. Wins with the vendored engine, no rules.
  * 15 invariant         — needs a variable-carrying rule ("a handler that reads
    secrets requires an auth-check") that cannot be a stored atom (the firewall
    bans $vars). Baseline -> NO (wrong); the vendored engine alone -> NO (the
    feature gap); PLN + `code_rules` -> YES. These flip only once the trusted
    `code_rules.metta` mechanism exists.
  * 15 negative          — no valid chain exists (query crosses disconnected
    components), gold = NO. Baseline -> NO (correct); PLN must NOT hallucinate a
    conclusion -> NO (correct). Guards against a degenerate always-yes PLN and
    makes exact-match meaningful.

Expected (all rules available): baseline exact ~40/80 = 0.50; PLN exact ~1.0;
net flips-to-correct ~40 (>= gate +20); sign-test p ~ 0.5**40 << 0.05.

The `CODE_RULES` constant is the trusted rule text the invariant family needs;
it is loaded into the PLN runtime AND offered inline to the baseline (same
premises + same rules to both arms, per the methodology). It defines only the
dedicated `|~code` head so it can never redefine a vendored PLN pattern.
"""

import random

SEED = 2101

# The invariant families (must stay in sync with CODE_RULES conditions below).
# Each: a predicate learned to require a control when two facts hold about $x.
_INVARIANTS = (
    # (role, trigger_predicate, trigger_object, required_control)
    ("handler", "reads", "secrets", "auth-check"),
    ("handler", "writes", "db", "input-validation"),
    ("endpoint", "accepts", "upload", "size-limit"),
)

# Trusted, committed, PR-reviewed rule text. Loaded as (= ...) equations under
# the dedicated |~code head (never |~pln), so the linter can guarantee it cannot
# redefine vendored truth functions or PLN patterns. Variables ($x) are legal
# here precisely because this is the trusted channel, not the atom store. The
# truth of the conclusion is the vendored Truth__ModusPonens of the two premise
# truth values, so confidence decays exactly as PLN would (no bespoke arithmetic).
CODE_RULES = "\n".join(
    f"(= (|~code ((Inheritance $x {role}) $t1) "
    f"((Evaluation (Predicate {pred}) (List $x {obj})) $t2)) "
    f"((Evaluation (Predicate requires) (List $x {ctrl})) "
    f"(Truth__ModusPonens $t1 $t2)))"
    for (role, pred, obj, ctrl) in _INVARIANTS
)

_HIGH_STV = (0.95, 0.9)   # tool_result-grade premises


def _impl(a, b):
    return f"(Implication (affected {a}) (affected {b}))"


def _case(cid, kind, family, premises, question, gold, needs_code_rules=False):
    return {
        "id": cid,
        "kind": kind,               # "direct" | "multihop" | "negative"
        "family": family,           # "direct-*" | "impact-chain" | "invariant" | "negative-*"
        "premises": [[p, list(stv)] for p, stv in premises],
        "question": question,       # ground query atom (canonical-ish)
        "gold": gold,               # True (derivable/stored) | False
        "needs_code_rules": needs_code_rules,
    }


def build_cases(seed=SEED):
    """80 deterministic decision cases. Distinct file names per case keep the
    per-case stores independent even though each already has its own scope db."""
    rng = random.Random(seed)
    cases = []

    # -- 25 direct-positive: the answer atom is stored (both arms should win) --
    for i in range(25):
        g = i % 5
        if i % 3 == 0:
            atom = f"(Inheritance file:src/d{i}/svc_{i}.py module:core{g})"
        elif i % 3 == 1:
            atom = _impl(f"file:src/d{i}/a_{i}.py", f"file:src/d{i}/b_{i}.py")
        else:
            atom = f"(Evaluation (Predicate depends-on) (List module:core{g} dep:lib-{i}))"
        cases.append(_case(f"direct-{i:02d}", "direct", "direct", [(atom, _HIGH_STV)],
                           atom, True))

    # -- 25 impact-chain: composed edge is never stored; PLN deduction wins ----
    for i in range(25):
        length = 2 if i % 2 == 0 else 3        # 2 or 3 edges
        base = f"file:src/chain{i}"
        nodes = [f"{base}/n{k}_{i}.py" for k in range(length + 1)]
        premises = [(_impl(nodes[k], nodes[k + 1]), _HIGH_STV) for k in range(length)]
        rng.shuffle(premises)                  # order independence
        question = _impl(nodes[0], nodes[-1])  # endpoints — never a stored edge
        assert question not in [p for p, _ in premises]
        cases.append(_case(f"impact-{i:02d}", "multihop", "impact-chain",
                           premises, question, True))

    # -- 15 invariant: needs a variable-carrying code_rule to fire ------------
    for i in range(15):
        role, pred, obj, ctrl = _INVARIANTS[i % len(_INVARIANTS)]
        x = f"file:src/inv{i}/mod_{i}.py"
        premises = [
            (f"(Inheritance {x} {role})", _HIGH_STV),
            (f"(Evaluation (Predicate {pred}) (List {x} {obj}))", _HIGH_STV),
        ]
        rng.shuffle(premises)
        question = f"(Evaluation (Predicate requires) (List {x} {ctrl}))"
        cases.append(_case(f"invariant-{i:02d}", "multihop", "invariant",
                           premises, question, True, needs_code_rules=True))

    # -- 15 negative: two disconnected chains; the cross query has no path -----
    for i in range(15):
        c1 = [f"file:src/negA{i}/p{k}_{i}.py" for k in range(3)]
        c2 = [f"file:src/negB{i}/q{k}_{i}.py" for k in range(3)]
        premises = [(_impl(c1[0], c1[1]), _HIGH_STV), (_impl(c1[1], c1[2]), _HIGH_STV),
                    (_impl(c2[0], c2[1]), _HIGH_STV), (_impl(c2[1], c2[2]), _HIGH_STV)]
        rng.shuffle(premises)
        question = _impl(c1[0], c2[2])   # component A -> component B: unreachable
        cases.append(_case(f"negative-{i:02d}", "negative", "negative",
                           premises, question, False))

    return cases


def cases_summary(cases=None):
    cases = cases or build_cases()
    by_family, by_kind = {}, {}
    for c in cases:
        by_family[c["family"]] = by_family.get(c["family"], 0) + 1
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    return {"n": len(cases), "seed": SEED, "by_family": by_family, "by_kind": by_kind,
            "needs_code_rules": sum(c["needs_code_rules"] for c in cases),
            "invariants": len(_INVARIANTS)}


if __name__ == "__main__":
    import json
    print(json.dumps(cases_summary(), indent=2))
    print("\nCODE_RULES:\n" + CODE_RULES)
