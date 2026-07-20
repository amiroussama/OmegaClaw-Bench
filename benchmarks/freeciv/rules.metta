; FreeCiv strategy rules for the PLN-vs-plain-LLM A/B experiment.
;
; Each rule is a PLN **Implication** premise "situation => conclusion". Paired with an observed
; fact sentence via (|~ fact rule) — the lib_pln two-premise operator (lib_pln.metta:306; NOTE: |-
; is the arrow-form NAL operator and does NOT fire on word-form Inheritance/Implication — PLN
; word-form needs |~) — lib_pln's Modus Ponens clause
;   (|~pln ($A $T1) ((Implication $A $B) $T2)) -> ($B (Truth__ModusPonens $T1 $T2))
; derives the grounded conclusion: the rule's variable unifies with the fact's entity, so
;   ((Inheritance City_1 Undefended) (stv 1.0 0.99))  +  the Undefended rule
;     |~  ((Recommend City_1 Defend) (stv 0.9 0.71))   [verified in-container]
;
; MULTI-HOP CHAINING (Issue: enrich PLN reasoning). Beyond the one-hop `situation => Recommend`
; rules, we add rules whose conclusion is an INTERMEDIATE predicate (State/Priority), so a second
; rule fires on THAT to reach a specific recommendation:
;   (Inheritance $c Undefended) => (State $c NeedsGarrison)   [hop 1]
;   (State $c NeedsGarrison)     => (Priority $c Military)     [hop 2]
;   (Priority $c Military)       => (Recommend $c BuildDefender) [hop 3]
; reason.derive drives this as a bounded Python fixpoint: each pass runs the interpreter, parses
; ALL derived (atom (stv f c)) sentences, adds the new ones to the premise set, and re-runs until
; no new atoms or a hop cap. Chained Modus Ponens decays confidence (0.99 -> ~0.8 -> ~0.58 -> ~0.38),
; so rule truth values are high-ish and a confidence floor prunes over-decayed conclusions.
;
; The fact vocabulary matches what benchmarks/freeciv/adapter.py emits
; (Inheritance <city> Undefended | LowFood ; Inheritance <unit> Type_settlers ;
;  Evaluation (Predicate Threatens) (List <enemy> <target>)) plus LLM-proposed facts.
;
; CLASSIFICATION (see benchmarks/freeciv/docs/atomspace-mapping.md):
; Every rule below is a STRATEGIC HEURISTIC ("situation => recommended action / assessment"), NOT a
; game-world law. Heuristics are intentionally uncertain — frequency < 1.0 and/or confidence
; < 0.99. There are currently NO game-world-law atoms; hard legality ("a settler can found a
; city", "you cannot move an enemy's unit") is enforced procedurally by actions.validate_action,
; not asserted as atoms. If a game-world law is ever added as an atom it MUST carry (stv 1.0 0.99).
; The trailing `; class: ... ; fires: ... ; rationale: ...` annotation on each Recommend-conclusion
; rule is parsed by benchmarks/freeciv/rulesparse.py into docs/MAPPING.md — keep it in sync.
; (Intermediate-predicate rules — conclusion is State/Priority, not Recommend — are internal
; reasoning steps: they are NOT parsed into MAPPING.md and only fire in-container via the fixpoint.)

(= (freeciv-rules)
   (superpose (
     ; --- direct one-hop rules (also matched by the host-side rulesparse matcher) ---------------
     ((Implication (Inheritance $c Undefended) (Recommend $c Defend)) (stv 0.9 0.8))   ; class: heuristic ; fires: yes ; rationale: an undefended city is usually worth defending
     ((Implication (Inheritance $c LowFood) (Recommend $c Food)) (stv 0.9 0.8))        ; class: heuristic ; fires: yes ; rationale: a food-deficit city should prioritize food
     ((Implication (Inheritance $u Type_settlers) (Recommend $u Settle)) (stv 0.8 0.7)); class: heuristic ; fires: yes ; rationale: a settler is usually best spent founding a city
     ; NOTE: this Evaluation-form rule does not fire under the current lib_pln Evaluation clauses
     ; (Defend/Food/Settle Inheritance-form rules DO fire); kept for future PLN-rule work.
     ((Implication (Evaluation (Predicate Threatens) (List $e $t)) (Recommend $t Retreat)) (stv 0.85 0.75)) ; class: heuristic ; fires: no ; rationale: a threatened unit may retreat (Evaluation-form, inert under current lib_pln)

     ; --- multi-hop chains: intermediate predicates compose into specific recommendations --------
     ; garrison chain (from Undefended): NeedsGarrison -> Military priority -> build a defender
     ((Implication (Inheritance $c Undefended) (State $c NeedsGarrison)) (stv 0.9 0.9))
     ((Implication (State $c NeedsGarrison) (Priority $c Military)) (stv 0.9 0.9))
     ((Implication (Priority $c Military) (Recommend $c BuildDefender)) (stv 0.9 0.9))     ; class: heuristic ; fires: no ; rationale: a city needing a garrison should build a defender (3-hop chain; fires in-container via the fixpoint)
     ; growth chain (from LowFood): NeedsGrowth -> irrigate the surrounding tiles
     ((Implication (Inheritance $c LowFood) (State $c NeedsGrowth)) (stv 0.9 0.9))
     ((Implication (State $c NeedsGrowth) (Recommend $c Irrigate)) (stv 0.9 0.9))          ; class: heuristic ; fires: no ; rationale: a food-short city should irrigate for growth (2-hop chain; fires in-container via the fixpoint)
     ; expansion chain (from a settler): ReadyToExpand -> found a new city now
     ((Implication (Inheritance $u Type_settlers) (State $u ReadyToExpand)) (stv 0.85 0.9))
     ((Implication (State $u ReadyToExpand) (Recommend $u FoundCity)) (stv 0.9 0.9))       ; class: heuristic ; fires: no ; rationale: a settler ready to expand should found a city (2-hop chain; fires in-container via the fixpoint)
   )))

; Pair one observed fact sentence with every rule and return the derived conclusions
; (nondeterministic). A non-matching (fact, rule) pair yields nothing. Multi-hop composition is
; driven by reason.derive re-feeding derived intermediate atoms as premises on the next pass.
(= (recommend-for $fact)
   (let $r (freeciv-rules) (|~ $fact $r)))
