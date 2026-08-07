# Proposal — Recalibrage M3C3 : décision régime-conditionnée

| Champ | Valeur |
|---|---|
| Id | `reweight_regime_conditioned` |
| Version | **0.5.0-proposal** |
| Base | `master.yaml@0.4.0` |
| Statut | **`awaiting_emitter_validation`** (non activé) |
| `exceeds_max_step` | **true** |
| Cible | `decision_stack` + `application_protocol` |
| Activation | Dani Bengal / `@cdxxotus` uniquement |

YAML canonique : [`decision_regime_v0.5.0-proposal.yaml`](decision_regime_v0.5.0-proposal.yaml)

---

## Variables

```yaml
evidence_sufficiency: {threshold_tau: "f(regret_asymmetry)"}
# + regime, regret_asymmetry, ruin_gate (voir YAML)
```

---

## `decision_stack_by_regime`

### fuzzy (somme 1.00)

| Critère | v0.4.0 | proposé |
|---|---|---|
| evidence_falsifiability | 0.30 | **0.28** |
| risk_impact_security | 0.25 | **0.24** |
| constraint_isolation | 0.20 | **0.20** |
| utility_expected_value | 0.15 | **0.16** |
| m3c3_hierarchy | 0.07 | **0.06** |
| adversarial_probe | 0.03 | **0.06** |

### quantifiable (somme 1.00)

| Critère | proposé |
|---|---|
| utility_expected_value | **0.45** |
| evidence_falsifiability | **0.20** |
| constraint_isolation | **0.12** |
| risk_impact_security | **0.12** |
| adversarial_probe | **0.06** |
| m3c3_hierarchy | **0.05** |

> ⚠️ Vecteur quantifiable **excède** `max_step: 0.04` → ajout structurel, validation émetteur explicite.

---

## `application_protocol_patch`

```text
1. detect_regime                         # nouvelle 1re étape
2. project_problem_on_hierarchy
3. attend_by_weights                     # ex-allocate_by_weights (attention seule)
4. if regime == quantifiable:
     compute_expected_utility(in=math, curvature=rho)
5. allocate_by_marginal_value            # valeur/urgence du problème
6. execute_with_sandbox
7. audit_every_transition
8. on_anomaly: resolve | recover | kill
```

---

## Invariants / hors scope

```yaml
unchanged: [binary_fact_assumption_split, forme4_health_gate, adversarial_probe, kill_switch]
out_of_scope: [authorship, CDXX_capsules, forme4, cenote]
```

**Master v0.4.0 reste la source de vérité** tant que non activé.
