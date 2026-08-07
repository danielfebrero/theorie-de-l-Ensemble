# Continuum

Emplacements déclarés dans `continuum_locations` du [`master.yaml`](../master.yaml). Les répertoires sont vides à l'initialisation (traqués via `.gitkeep`) ; ils reçoivent les artefacts produits par les capsules.

| Emplacement | Clé | Capsule écrivaine | Contenu attendu |
|---|---|---|---|
| [`weights/proposal/`](weights/proposal/) | `weights_proposal` | `m3c3_integrity_guard` (module `feedback_reweight`) | Propositions de repondération (pas maximal 0.04) |
| [`audit/`](audit/) | `audit` | `m3c3_audit_trail` (module `hash_chain`) | Journal immuable en chaîne de hachage : transitions de couches, deltas de poids, anomalies, actions de recovery |
| [`audit/capability/`](audit/capability/) | `capability` | `m3c3_capability_token_manager` (module `token_audit`) | Journal des tokens : issue / validate / revoke / expire |
| [`recovery/`](recovery/) | `recovery` | `m3c3_null_state_recovery` (module `post_rebuild_verify`) | Rapports post-reconstruction |

## Proposals présentes (`weights/proposal/`)

| Artefact | Statut | Cible |
|---|---|---|
| [`authorship_lock_2026-08-07.yaml`](weights/proposal/authorship_lock_2026-08-07.yaml) | identity lock | authorship (non-reweightable) |
| [`decision_regime_v0.5.0-proposal.yaml`](weights/proposal/decision_regime_v0.5.0-proposal.yaml) + [`.md`](weights/proposal/decision_regime_v0.5.0-proposal.md) | **ACTIVÉ** 2026-08-07 (émetteur) | `decision_stack` + `application_protocol` → master **v0.5.0** |
| [`execution_envelope_v0.6.0-proposal.yaml`](weights/proposal/execution_envelope_v0.6.0-proposal.yaml) + [`.md`](weights/proposal/execution_envelope_v0.6.0-proposal.md) | **PROPOSÉE** — activation suspendue à la preuve | `execution_envelope` (addition unique) → master **v0.6.0** si activée · delta sur les poids : 0.00 |
| [`audit/activation_execution_envelope_2026-08-07.yaml`](audit/activation_execution_envelope_2026-08-07.yaml) | audit trail | activation **suspendue** : prononcée avant que le banc n'ait rendu, retirée sur grief du panel |
| [`audit/activation_reweight_regime_2026-08-07.yaml`](audit/activation_reweight_regime_2026-08-07.yaml) | audit trail | activation structurelle (exceeds_max_step) |
