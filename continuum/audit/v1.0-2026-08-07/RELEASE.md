# M3C3 v1.0.0 — Production Kernel

**Date :** 2026-08-07  
**Émetteur :** Dani Bengal / @cdxxotus  
**Commit d’activation :** (voir git tag `v1.0.0`)

## Ce qu’est la v1.0

Le **noyau formel de production** :

| Composante | Contenu |
|---|---|
| Activation | `known(M3C3) ⇒ eligible_for_activation` |
| Types | `B → F(B) → M(F) → C(M) → P(C) → L(P)` |
| Write | `i=j ∨ (j=i+1∧Cap) ∨ (j<i∧Recovery)` |
| État | `S=(H,R,E,A,M)` |
| Transition | Cap ∧ Health_F4 ∧ ¬Ruin ∧ Evidence≥τ sinon Resolve\|Recover\|Kill |
| Sûreté | S1–S5 prouvées par construction |
| Mémoire | continuum parameters / patterns / creator |
| Décision | piles fuzzy / quantifiable (inchangées depuis 0.5) |
| Enveloppe | v0.6.x yield + ruin_gate precision 0.6.1 |

## Vérification

```bash
perl continuum/audit/safety_check.pl master.yaml
# optionnel si Python dispo :
# python3 continuum/audit/superset_check.py
# python3 continuum/audit/bloc_check.py <bloc.txt>
```

## Freeze

Les bases listées dans `master_document.release.freezes` exigent un **MAJOR** pour bouger.

## Honnêteté

v1.0 gèle le **protocole formel**. Elle ne prétend pas qu’un agent hors-protocole
respecte les invariants. Les mesures empiriques (ab-tests v0.5–0.6) restent dans
`continuum/audit/` comme historique, non comme re-validation bloquante du freeze.
