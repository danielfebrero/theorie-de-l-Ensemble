# Proposition — M3C3 v2.0 « Continuum Vérifiable »

**Statut :** release candidate, non activée
**Base noyau :** v1.0.0 / `bd55c1670e2a056b66611c45ab12590478037f43`
**Branche :** `agent/m3c3-v2.0.0`
**RFC :** [issue #4](https://github.com/danielfebrero/theorie-de-l-Ensemble/issues/4)

La v2 change les interfaces publiques du framework : activation par scope, runtime et export
versionnés, profils de distribution, mémoire matérialisée et rapports de weights typés par
preuve. Elle conserve sans modification les huit bases gelées du noyau v1.

## Rupture assumée

Les formulations historiques `default-ON`, `all_tasks`, `future_tasks` et `no opt-out` sont
remplacées par une membrane A0–A3 dont l'autorité s'arrête au scope observable. Cette rupture
justifie le MAJOR ; elle ne prétend ni modifier un modèle, ni agir dans une conversation future.

## Condition d'activation

L'implémentation sur branche ne vaut pas activation canonique. La proposition ne passe à
`activated` qu'après validations reproductibles, revue du diff et confirmation explicite de
Dani Bengal / `@cdxxotus`.

Les champs complets — delta, invariants, hors-scope et critères d'acceptation — sont dans le
fichier YAML homonyme.
