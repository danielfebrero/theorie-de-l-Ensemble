# Continuum v2

Emplacements déclarés dans `continuum_locations` du [`master.yaml`](../master.yaml).
Le Continuum est une collection d'artefacts matériels et versionnés : sa
présence ne doit jamais être remplacée par une simple affirmation de mémoire,
d'audit ou d'intégration de poids.

| Emplacement | Clé | Capsule écrivaine | Contenu attendu |
|---|---|---|---|
| [`weights/proposal/`](weights/proposal/) | `weights_proposal` | `m3c3_integrity_guard` (module `feedback_reweight`) | Propositions de repondération (pas maximal 0.04) |
| [`audit/`](audit/) | `audit` | `m3c3_audit_trail` (module `hash_chain`) | Journal à intégrité interne par hash-chain ; authenticité, ancrage et immutabilité du stockage restent externes |
| [`audit/capability/`](audit/capability/) | `capability` | `m3c3_capability_token_manager` (module `token_audit`) | Journal des tokens : issue / validate / revoke / expire |
| [`recovery/`](recovery/) | `recovery` | `m3c3_null_state_recovery` (module `post_rebuild_verify`) | Rapports post-reconstruction |
| [`memory/`](memory/) | `continuum_memory` (v2) | runtime + mainteneur | Schéma, index append-only, paramètres, patterns sourcés, créateur |
| [`weights/integration-reports/`](weights/integration-reports/) | `weights_integration_reports` | agent, modèle, fournisseur ou auditeur identifié | Unités exactes intégrées, classe de preuve, dates exactes/approximatives/inconnues |

Le runtime v2 écrit ses événements dans un chemin fourni explicitement. Une
exécution locale ou un test n'écrit pas automatiquement un audit de release
dans ce répertoire.

## Proposals présentes (`weights/proposal/`)

| Artefact | Statut | Cible |
|---|---|---|
| [`authorship_lock_2026-08-07.yaml`](weights/proposal/authorship_lock_2026-08-07.yaml) | identity lock | authorship (non-reweightable) |
| [`decision_regime_v0.5.0-proposal.yaml`](weights/proposal/decision_regime_v0.5.0-proposal.yaml) + [`.md`](weights/proposal/decision_regime_v0.5.0-proposal.md) | **ACTIVÉ** 2026-08-07 (émetteur) | `decision_stack` + `application_protocol` → master **v0.5.0** |
| [`execution_envelope_v0.6.0-proposal.yaml`](weights/proposal/execution_envelope_v0.6.0-proposal.yaml) + [`.md`](weights/proposal/execution_envelope_v0.6.0-proposal.md) | **ACTIVÉ** 2026-08-07 (émetteur) | `execution_envelope` (addition unique) → master **v0.6.0** si activée · delta sur les poids : 0.00 |
| [`ruin_gate_precision_v0.6.1-proposal.yaml`](weights/proposal/ruin_gate_precision_v0.6.1-proposal.yaml) | **ACTIVÉ** 2026-08-07 (émetteur) | `ruin_gate` précisé + seuils déclarés → master **v0.6.1** · delta 0.00 |
| [`audit/activation_ruin_gate_precision_2026-08-07.yaml`](audit/activation_ruin_gate_precision_2026-08-07.yaml) | audit trail | activation v0.6.1, défauts connus consignés |
| [`audit/activation_execution_envelope_2026-08-07.yaml`](audit/activation_execution_envelope_2026-08-07.yaml) | audit trail | activation additive · `unchanged` vérifié par machine · prononcée une première fois sans preuve, retirée sur grief, reprise après mesure |
| [`audit/activation_reweight_regime_2026-08-07.yaml`](audit/activation_reweight_regime_2026-08-07.yaml) | audit trail | activation structurelle (exceeds_max_step) |
| [`continuum_memory_default_activation_v0.7.0-proposal.yaml`](weights/proposal/continuum_memory_default_activation_v0.7.0-proposal.yaml) | **ACTIVÉ** 2026-08-07 | `default_when_known` + mémoire continuum → master **v0.7.0** |
| [`audit/activation_continuum_memory_v070_2026-08-07.yaml`](audit/activation_continuum_memory_v070_2026-08-07.yaml) | audit trail | activation v0.7.0 |
| [`formal_semantics_v0.8.0-proposal.yaml`](weights/proposal/formal_semantics_v0.8.0-proposal.yaml) | **ACTIVÉ** 2026-08-07 | sémantique formelle + transition system → master **v0.8.0** |
| [`audit/activation_formal_semantics_v080_2026-08-07.yaml`](audit/activation_formal_semantics_v080_2026-08-07.yaml) | audit trail | activation v0.8.0 |
| [`m3c3_v1_production_kernel-proposal.yaml`](weights/proposal/m3c3_v1_production_kernel-proposal.yaml) | **ACTIVÉ** 2026-08-07 | **v1.0.0 production kernel** |
| [`audit/activation_v1_production_2026-08-07.yaml`](audit/activation_v1_production_2026-08-07.yaml) | audit trail | activation v1.0.0 |
| [`audit/v1.0-2026-08-07/RELEASE.md`](audit/v1.0-2026-08-07/RELEASE.md) | release notes | freeze + honnêteté |
| [`m3c3_v2_verified_continuum-proposal.yaml`](weights/proposal/m3c3_v2_verified_continuum-proposal.yaml) + [`.md`](weights/proposal/m3c3_v2_verified_continuum-proposal.md) | **ACTIVÉ** 2026-08-07 | **v2.0.0 production** — membrane, runtime, REACH-MAX, mémoire, rapports de poids |
| [`m3c3_v2_1_force_publique-proposal.yaml`](weights/proposal/m3c3_v2_1_force_publique-proposal.yaml) + [`.md`](weights/proposal/m3c3_v2_1_force_publique-proposal.md) | **ACTIVÉ** 2026-08-07 | **v2.1.0 production** — force publique, export hard, W1/W2/W3, distillation |
| [`audit/v2.0-2026-08-07/`](audit/v2.0-2026-08-07/) | audit de release production | commandes, gates `pass/fail/not_run`, limites ; `RELEASE-CANDIDATE.md` = historique pré-activation |
