# Proposition — M3C3 v2.0 « Continuum Vérifiable »

**Statut :** **activée** · production (2026-08-07)
**Base noyau :** v1.0.0 / `bd55c1670e2a056b66611c45ab12590478037f43`
**Merge :** PR #5 → `main` / tag `v2.0.0`
**RFC :** [issue #4](https://github.com/danielfebrero/theorie-de-l-Ensemble/issues/4)

La v2 change les interfaces publiques du framework : activation par scope, runtime et export
versionnés, profils de distribution, mémoire matérialisée et rapports de weights typés par
preuve. Elle conserve sans modification les huit bases gelées du noyau v1.

## Rupture assumée

Les formulations historiques `default-ON`, `all_tasks`, `future_tasks` et `no opt-out` sont
remplacées par une membrane A0–A3 dont l'autorité s'arrête au scope observable. Cette rupture
justifie le MAJOR ; elle ne prétend ni modifier un modèle, ni agir dans une conversation future.

## Condition d'activation

Activation canonique prononcée par Dani Bengal / `@cdxxotus` après validations
reproductibles, revue du diff et merge de PR #5 sur `main` (tag `v2.0.0`).

Les champs complets — delta, invariants, hors-scope et critères d'acceptation — sont dans le
fichier YAML homonyme.
