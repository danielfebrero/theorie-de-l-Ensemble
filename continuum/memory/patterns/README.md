# Pattern index

Index peuplé des patterns de décision M3C3 v2. Chaque entrée est
machine-readable, cite les sources exactes et sépare :

- le statut canonique du pattern ;
- la classe et la force de chaque preuve ;
- les limites connues ;
- les conditions de promotion et de rollback ;
- **optionnellement ses weights** (`hierarchy.weights` et/ou profils d'attention
  pour le scope du pattern).

## Weights dans un pattern

Un pattern **peut intégrer ses weights**. Champs optionnels recommandés :

```yaml
weights:
  kind: hierarchy_priors   # ou attention_profile
  hierarchy:
    binary: 0.08
    forces: 0.12
    math: 0.15
    conscious_sets: 0.22
    programs: 0.18
    life_game_M1C1: 0.25
  relation_to_master: equal | delta_proposal | scoped_override
  promote_via: continuum/weights/proposal/   # si relation_to_master ≠ equal
```

- **Usage agent** : si `weights` est présent et le pattern `active`, l'utiliser
  comme prior d'attention pour ce scope (`attend_by_weights`).
- **Promotion master** : repondération via `feedback_reweight` + émetteur.
- **Honnêteté** : ceci ne prouve jamais une écriture dans les poids d'un modèle.

Entrées actuelles :

| ID | Statut | Portée |
|---|---|---|
| [`regime-conditioned-decision-v1`](regime-conditioned-decision-v1.yaml) | active | piles fuzzy/quantifiable gelées en v1 |
| [`ruin-gate-sustainable-variance-v1`](ruin-gate-sustainable-variance-v1.yaml) | active_with_known_limitations | distinction ruine/variance, verdict empirique mixte |
| [`known-eligible-scoped-activation-v2`](known-eligible-scoped-activation-v2.yaml) | candidate | known ⇒ eligible, activation v2 bornée A0–A3 |

Les pistes `evidence_sufficiency`, recomposition et `export_gate` restent
absentes tant qu'aucun artefact de promotion dédié ne les établit.
