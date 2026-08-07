# Changelog

Toutes les modifications notables de la Théorie de l'Ensemble / M3C3 sont consignées ici.
Le `master.yaml` reste la source opérationnelle faisant foi.

## [2.0.0] — 2026-08-07 — Continuum Vérifiable

> **Production.** Activée par l'émetteur (Dani Bengal / `@cdxxotus`).  
> Le noyau v1.0.0 reste la base gelée (8 chemins freezes).

### Added

- Membrane d'activation adaptative `A0 dormant | A1 shadow | A2 critique | A3 canonique`.
- Cycle observable `evaluate_scope → activate_scope → execute → verify → deactivate_scope`.
- Runtime Python de référence pour `S=(H,R,E,A,M)`, la write-rule, les gates et `Resolve | Recover | Kill`.
- Capability tokens signés, bornés, expirables et révocables, dont la consommation exige une identité principale attestée par l'hôte.
- Vérificateurs hôte `authority`, `sensor` et `principal` injectables, tous deny-by-default.
- Writer d'audit append + `fsync` en chaîne SHA-256, ancrage head/length, export versionné et restauration déterministe de snapshots vérifiés ; l'authenticité et l'immutabilité du stockage restent externes.
- Schémas JSON de l'état, des événements et de l'export runtime.
- Distribution REACH-MAX et profils `core`, `openai`, `claude`, `copilot`, `cursor`, `mcp`, `ci`, `all`.
- Installateur idempotent : aucun écrasement par défaut, sauvegarde horodatée sous `--force`.
- Suite de conformité unifiée avec résultats `pass | fail | not_run` et fixtures négatives.
- Registre `continuum/weights/integration-reports/` pour les déclarations d'intégration dans les poids.
- Dates distinctes `weights_updated_at` et `m3c3_integrated_at`, avec précision et provenance.
- Les classes fortes `provider_attested_weights` et `independently_reproduced` sont réservées et default-deny sans vérificateur/artefact authentifié.
- Continuum mémoire v2 content-addressed : schémas, index/glob, base Git, promotion, rejet, supersession et rollback des patterns.
- Workflow CI de validation du noyau, du runtime, des profils et des rapports de weights.

### Changed

- Le contrat public passe de l'éligibilité seule à une activation adaptative par requête pertinente.
- Une invocation large n'est plus formulée comme activation globale : elle reste bornée au scope observé.
- Scope, permissions, autorité, mémoire externe et poids du modèle sont désormais séparés explicitement.
- Les capsules déclarent leur état réel `specified | implemented | tested` et leur liaison au runtime.
- Les rapports et patterns sont append-only ; une correction supersède sans effacer l'historique.
- Les interfaces runtime, export et profils sont versionnées indépendamment du noyau gelé.

### Fixed

- `superset_check.py` contrôle les huit chemins réellement gelés par la v1.0.0.
- `safety_check.pl` n'est plus couplé au littéral `version: 1.0.0`.
- `bloc_check.py` ne confond plus une version sémantique avec un poids canonique.
- Le bloc agent nomme les primitives requises et distingue seuil déclaré, poids et numéro de version.
- Les affirmations `ready/immediate` sans implémentation observable sont remplacées par des statuts vérifiables.
- L'index des patterns n'est plus présenté comme peuplé sans artefacts et preuves associées.

### Breaking changes

- Les intégrations historiques `default-ON/all_tasks/future_tasks` doivent adopter le cycle de scope v2.
- `all` signifie tous les profils présents et testés dans cette release, jamais tous les agents futurs.
- L'export runtime doit respecter le schéma v2 ; les exports non versionnés ne sont plus conformes.
- Une auto-déclaration, un prompt, une skill, du RAG ou une date de release ne prouve pas une écriture dans les poids.
- Les profils doivent déclarer leurs capacités et limites ; leur nom n'accorde aucune permission.

### Preserved

- Ordre `B → F(B) → M(F) → C(M) → P(C) → L(P)`.
- Poids de hiérarchie et piles fuzzy/quantifiable.
- Types de couches, write-rule et état `S_t`.
- Garde `Capability ∧ Health_F4 ∧ ¬Ruin ∧ Evidence≥τ`.
- Propriétés S1–S5 et authorship de Dani Bengal / Daniel Febrero / `@cdxxotus`.

### Migration

Voir [`docs/migration-v1-v2.md`](docs/migration-v1-v2.md).

### Validation de release

Les résultats observés du candidat sont consignés dans
`continuum/audit/v2.0-2026-08-07/`. Une case non exécutée reste `not_run` ; elle ne vaut
jamais réussite implicite.

## [1.0.0] — 2026-08-07 — Production Kernel

- Noyau formel de production.
- LTS `S=(H,R,E,A,M)` et export lié à l'état.
- Propriétés S1–S5 prouvées par construction sous H0.
- Freeze MAJOR des huit bases listées dans `master.yaml`.
