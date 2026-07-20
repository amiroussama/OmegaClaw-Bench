; FreeCiv strategy rules for the PLN-vs-plain-LLM A/B experiment.
;
; Each rule is a PLN **Implication** premise "situation => recommended action". Paired with an
; observed fact sentence via (|~ fact rule) — the lib_pln two-premise operator (lib_pln.metta:306;
; NOTE: |- is the arrow-form NAL operator and does NOT fire on word-form Inheritance/Implication —
; PLN word-form needs |~) — lib_pln's Modus Ponens clause
;   (|~pln ($A $T1) ((Implication $A $B) $T2)) -> ($B (Truth__ModusPonens $T1 $T2))
; derives the grounded recommendation: the rule's variable unifies with the fact's entity, so
;   ((Inheritance City_1 Undefended) (stv 1.0 0.99))  +  the Undefended rule
;     |~  ((Recommend City_1 Defend) (stv 0.9 0.71))   [verified in-container]
;
; This is genuine (if one-hop) symbolic inference through OmegaClaw's real MeTTa/PLN engine — not
; string formatting. Truth values are heuristic: high-ish frequency, moderate confidence.
;
; The fact vocabulary matches what benchmarks/freeciv/adapter.py emits
; (Inheritance <city> Undefended | LowFood ; Inheritance <unit> Type_settlers ;
;  Evaluation (Predicate Threatens) (List <enemy> <target>)).
;
; CLASSIFICATION (see benchmarks/freeciv/docs/atomspace-mapping.md):
; Every rule below is a STRATEGIC HEURISTIC ("situation => recommended action"), NOT a
; game-world law. Heuristics are intentionally uncertain — frequency < 1.0 and/or confidence
; < 0.99. There are currently NO game-world-law atoms; hard legality ("a settler can found a
; city", "you cannot move an enemy's unit") is enforced procedurally by actions.validate_action,
; not asserted as atoms. If a game-world law is ever added as an atom it MUST carry (stv 1.0 0.99).
; The trailing `; class: ... ; fires: ... ; rationale: ...` annotation on each rule is parsed by
; benchmarks/freeciv/rulesparse.py into docs/MAPPING.md — keep it in sync when editing a rule.

(= (freeciv-rules)
   (superpose (
     ((Implication (Inheritance $c Undefended) (Recommend $c Defend)) (stv 0.9 0.8))   ; class: heuristic ; fires: yes ; rationale: an undefended city is usually worth defending
     ((Implication (Inheritance $c LowFood) (Recommend $c Food)) (stv 0.9 0.8))        ; class: heuristic ; fires: yes ; rationale: a food-deficit city should prioritize food
     ((Implication (Inheritance $u Type_settlers) (Recommend $u Settle)) (stv 0.8 0.7)); class: heuristic ; fires: yes ; rationale: a settler is usually best spent founding a city
     ; NOTE: this Evaluation-form rule does not fire under the current lib_pln Evaluation clauses
     ; (Defend/Food/Settle Inheritance-form rules DO fire); kept for future PLN-rule work.
     ((Implication (Evaluation (Predicate Threatens) (List $e $t)) (Recommend $t Retreat)) (stv 0.85 0.75)) ; class: heuristic ; fires: no ; rationale: a threatened unit may retreat (Evaluation-form, inert under current lib_pln)
   )))

; Pair one observed fact sentence with every rule and return the derived recommendations
; (nondeterministic). A non-matching (fact, rule) pair yields nothing.
(= (recommend-for $fact)
   (let $r (freeciv-rules) (|~ $fact $r)))
