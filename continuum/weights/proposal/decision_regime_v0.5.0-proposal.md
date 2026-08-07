# Proposal — Recalibrage M3C3 : décision régime-conditionnée

| Champ | Valeur |
|---|---|
| Id | `reweight_regime_conditioned` |
| Version | **0.5.0** |
| Base | `master.yaml@0.4.0` |
| Statut | **ACTIVÉ** |
| Activé le | 2026-08-07 |
| Activé par | Dani Bengal / `@cdxxotus` (émetteur) |
| Master après | **v0.5.0** |
| `exceeds_max_step` | true (ajout structurel validé par émetteur) |

YAML : [`decision_regime_v0.5.0-proposal.yaml`](decision_regime_v0.5.0-proposal.yaml)  
Audit : [`../../audit/activation_reweight_regime_2026-08-07.yaml`](../../audit/activation_reweight_regime_2026-08-07.yaml)

## Stacks actifs

**Fuzzy** 0.28 / 0.24 / 0.20 / 0.16 / 0.06 / 0.06  
**Quantifiable** 0.45 / 0.20 / 0.12 / 0.12 / 0.06 / 0.05

## Protocole actif

`detect_regime` → `project_problem_on_hierarchy` → `attend_by_weights` → (si quantifiable: `compute_expected_utility`) → `allocate_by_marginal_value` → sandbox → audit → anomaly

Authorship / CDXX / forme#4 / cenote : inchangés.
