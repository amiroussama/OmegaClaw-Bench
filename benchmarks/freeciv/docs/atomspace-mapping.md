# The FreeCiv AtomSpace mapping — reviewer's guide

This guide is for **domain experts** (FreeCiv/game reviewers, PLN reviewers) who want to
inspect and improve how the benchmark turns game state into the atoms PLN reasons over — without
reading the Python. It exists because the current mapping was produced iteratively with an LLM,
and (per Khellar Crawford) symbolic induction via LLM-generated atoms is not yet reliable enough
to trust blindly: **AtomSpace correctness is the first priority — if the atoms are wrong, every
downstream inference is wrong.**

The machine-generated companion to this guide is [`MAPPING.md`](MAPPING.md) — the full,
always-current inventory of every atom form, rule, and action. Read this guide once; review
`MAPPING.md` on every change.

## 1. What the AtomSpace is here

Each turn, the benchmark takes the game state the proxy sends and converts it into a set of PLN
**fact atoms**, loads them alongside the **rule atoms** in `rules.metta`, and runs one-hop
Modus Ponens to derive **recommendation atoms**:

```
game state ──adapter.facts_from_state──▶ fact atoms ─┐
                                                     ├─(|~ fact rule)─▶ (Recommend <entity> <action>)
rules.metta ────────────────────────────▶ rule atoms ┘
```

Example (verified in-container):

```
((Inheritance City_1 Undefended) (stv 1.0 0.99))          ; observed fact
+ ((Implication (Inheritance $c Undefended) (Recommend $c Defend)) (stv 0.9 0.8))   ; rule
|~  ((Recommend City_1 Defend) (stv 0.9 0.71))            ; derived recommendation
```

Every atom carries a **truth value** `(stv frequency confidence)`, both in `[0,1]`.

## 2. The four classes of atoms

### 2.1 Game-world laws
Hard rules of the game ("a settler can found a city", "you cannot move an enemy's unit", "a move
target must be on the map"). **None exist as atoms today** — legality is enforced procedurally by
`actions.validate_action` before any action is submitted (see `MAPPING.md` §4). *Convention if a
law is ever asserted as an atom:* it must carry `(stv 1.0 0.99)` — frequency 1, near-certain
confidence. This is the "laws of physics" idea: they are always true.

### 2.2 Current-state facts
What is observably true this turn. Two provenances:
- **observed** `(stv 1.0 0.99)` — read directly from the state (unit type, position, gold, score,
  researched techs). We are certain of these.
- **derived** `(stv 1.0 0.9)` — computed by a small heuristic over the state
  (`LowFood` = food deficit; relative-strength label). Slightly lower confidence because the
  heuristic could be wrong.

Every form, with its plain-English reading and the exact state field it comes from, is in
`MAPPING.md` §1.

### 2.3 Action preconditions & effects
Per action type: the required fields and ownership/bounds checks (`MAPPING.md` §4). These mirror
the validator. *Effects* (what an action changes) are handled by the game engine, not modeled as
atoms.

### 2.4 Inferred strategic facts & rules
The `Implication` rules in `rules.metta` (`MAPPING.md` §2): **11** in total after the multi-hop
expansion — 7 with a `Recommend` conclusion (the count the AtomSpace snapshot reports) plus 4
intermediate `State`/`Priority` chain rules. These are **strategic heuristics**, not laws — "an
undefended city is usually worth defending". That is why their truth is intentionally uncertain
(frequency 0.8–0.9, confidence 0.7–0.8) and **must never be 1.0**. The three direct one-hop
Inheritance-form rules (Defend/Food/Settle) fire under the host PLN engine; the Threatens rule is
Evaluation-form and currently inert (kept for future work); the multi-hop chains fire in-container
via the `reason.derive` fixpoint.

## 3. How to review a mapping change

1. **Read the diff of `MAPPING.md`.** It is regenerated from the code, so a real mapping change
   shows up there. Regenerate it yourself if the PR forgot to:
   ```
   python3 benchmarks/freeciv/mapping_inventory.py --write
   ```
2. **Walk the checklist** in §4 against the diff.
3. **Spot-check a real state** — see the atoms and recommendations a captured game state produces:
   ```
   python3 benchmarks/freeciv/viz/dump_atoms.py --state benchmarks/freeciv/samples/real_state_turn1.json
   ```
4. **Trust CI.** `Autotests/test_freeciv_mapping.py` fails if `MAPPING.md` is stale, if a fact
   escapes the documented vocabulary, or if a heuristic rule illegally claims certainty.

## 4. Review checklist

### Completeness
- [ ] Every state category the proxy sends (units, cities, resources, techs, strategic, threats)
      appears in `MAPPING.md` §1 with at least one atom form.
- [ ] Every atom form in `MAPPING.md` is exercised by at least one fixture or captured sample
      (enforced by `test_vocabulary_fully_exercised`).
- [ ] Every rule premise references an atom form the adapter actually emits — e.g. `Type_settlers`
      (runtime lowercase), **not** `Type_Settler`.
- [ ] Every action type in the schema appears in `MAPPING.md` §4 with its preconditions.

### Confidence values
- [ ] Directly-observed facts carry `(stv 1.0 0.99)`; derived/heuristic facts carry `(stv 1.0 0.9)`
      — no other values without a documented reason.
- [ ] Game-world laws (if any) carry `(stv 1.0 0.99)`; **no** strategic heuristic carries
      frequency 1.0.
- [ ] Rule truth values are in `[0,1]` and the resulting Modus-Ponens confidence is sensible
      (premise confidence × rule confidence — check the worked example in §5).

### Provenance
- [ ] Every fact row names its source state path (e.g. `units[].type`, `cities[].food_surplus`).
- [ ] Derived facts state their derivation in plain English (LowFood: `food_surplus < 0`;
      Undefended: no owned unit on the city tile).
- [ ] Each rule cites its rationale in a `rules.metta` comment (parsed into `MAPPING.md` §2).

### Consistency
- [ ] Entity tokens are consistent across facts, rules, and action linkage
      (`City_<id>` / `Unit_<id>` / `Tech_<name>` — matching `_ACTOR_TOKEN`).
- [ ] No two atom forms encode the same information differently (one form per relation).
- [ ] Renamed/removed atoms: `rules.metta` **and** `MAPPING.md` updated in the same change (the
      drift test enforces this).
- [ ] `MAPPING.md` regenerated in this PR if `adapter.py`, `rules.metta`, or `schemas.py` changed.

## 5. Worked end-to-end example

The fixture `pln_settler_to_found_city` (in `fixtures.py`) is a minimal, deterministic case that
walks the full chain — state → fact → rule → recommendation → action:

```
state:   one owned unit {id: 301, type: "settlers", ...}, no cities
fact:    (Inheritance Unit_301 Type_settlers)                      (stv 1.0 0.99)   [observed]
rule:    (Implication (Inheritance $u Type_settlers) (Recommend $u Settle))  (stv 0.8 0.7)
derive:  (Recommend Unit_301 Settle)                              [Modus Ponens]
action:  {"type": "unit_build_city", "unit_id": 301}             [validate_action: legal]
link:    the action's actor unit_id 301 -> token Unit_301 == the recommendation entity
```

`test_action_to_atom_golden_fixture` asserts every step of this chain, so it is a live,
regression-guarded example — not just documentation.
