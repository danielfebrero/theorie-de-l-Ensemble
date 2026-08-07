# M3C3 v2.0.0 — Audit du release candidate

**Statut :** candidat local validé, non activé canoniquement

**Branche :** `agent/m3c3-v2.0.0`

**Baseline d'implémentation :** `188f0bc517822e95cccc4ba1baaef9f11bc32b2c`

## Verdict local

Les 15 gates requises passent. Le noyau v1 est identique sur ses huit chemins
gelés. Les suites comptent 37 tests runtime, 35 distribution, 27 conformité,
10 mémoire et 2 capsules. L'exploration bornée à profondeur 6 visite 76 états
et 912 transitions sans violation S1–S5 observée.

`external_model_check` reste `not_run` : aucun artefact SPIN/TLA ni exécution
d'un model-checker externe n'est présent. Ce statut est informationnel et ne
doit jamais être reformulé en réussite.

## Frontières conservées

- La hash-chain fournit une intégrité interne, pas une authenticité autonome.
  Une ancre externe de confiance est nécessaire pour détecter une chaîne
  entièrement réécrite ou tronquée vers un préfixe valide.
- Le replay restaure des snapshots vérifiés ; il ne réexécute pas `T`.
- Un WAL REACH-MAX persistant n'est pas authentifiable après un crash : la
  commande refuse toute mutation et exige une réconciliation manuelle.
- Les profils hôtes sont validés comme artefacts/installations, pas comme
  preuve que chaque produit les a effectivement chargés.
- Le registre de weights contient zéro rapport réel et trois exemples non
  probants. Les classes fortes restent default-deny sans vérificateur.

## Décision

Le candidat est prêt pour une draft PR. Il n'est ni merge-ready ni activé tant
que les GitHub Actions distantes, la revue et la confirmation explicite de
Dani Bengal / `@cdxxotus` ne sont pas acquises.

Les données machine-readable qui font foi pour cet audit sont dans
[`results.yaml`](results.yaml).
