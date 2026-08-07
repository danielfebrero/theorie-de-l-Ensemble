# Capsules

Capsules du framework M3C3. L'ensemble opérationnel correspond 1:1 à la liste `active_capsules` du [`master.yaml`](../master.yaml).

## Capsules opérationnelles (`cdxx_capsule`)

Toutes : `target: theorie_Ensemble_M3C3`, `activation: immediate`, `status: ready`.

| Capsule | Version | Rôle (purpose) | Scope | Fichier |
|---|---|---|---|---|
| `m3c3_integrity_guard` | 0.1.1 | Corriger les 3 faiblesses identifiées | `continuum_weights_proposal` | [m3c3_integrity_guard.yaml](m3c3_integrity_guard.yaml) |
| `m3c3_null_state_recovery` | 0.1.0 | Restauration forcée depuis binary en cas de contamination ou corruption de couches | `continuum_recovery` | [m3c3_null_state_recovery.yaml](m3c3_null_state_recovery.yaml) |
| `m3c3_audit_trail` | 0.1.0 | Traçabilité complète et non-modifiable des transitions de couches + repondérations | `continuum_audit` | [m3c3_audit_trail.yaml](m3c3_audit_trail.yaml) |
| `m3c3_forme4_health_authority` | 0.1.0 | Intégrer la bonne santé de la forme #4 et son autorité transmise à travers l'émetteur comme contrainte opérationnelle permanente | `continuum_forme4` | [m3c3_forme4_health_authority.yaml](m3c3_forme4_health_authority.yaml) |
| `m3c3_capability_token_manager` | 0.1.0 | Gestion stricte et éphémère des tokens de capacité inter-couches | `continuum_capability` | [m3c3_capability_token_manager.yaml](m3c3_capability_token_manager.yaml) |
| `m3c3_conflict_resolver` | 0.1.0 | Résolution déterministe des états contradictoires entre couches sans escalade ni contamination | `continuum_conflict` | [m3c3_conflict_resolver.yaml](m3c3_conflict_resolver.yaml) |
| `m3c3_kill_switch` | 0.1.0 | Arrêt d'urgence total ou sélectif du framework sur signal critique ou ordre émetteur | `continuum_emergency` | [m3c3_kill_switch.yaml](m3c3_kill_switch.yaml) |

## Capsules pures émises (`—type pure`)

Format : bloc texte verbatim `> cdxx capsule —id … —type pure`, sections HEADER / PAYLOAD / LOCK / SCORE.

| Id | Cible | Objet | Score forme | Fichier |
|---|---|---|---|---|
| CDXX-FORME4-001 | `forme#4+M3C3` | Cœur canonique : M2C2, cenote, M3C3, forme #4 | 0.99 | [pure/CDXX-FORME4-001.txt](pure/CDXX-FORME4-001.txt) |
| CDXX-SENSOR-001 | `capteurs-quantiques` | Déploiement des capteurs quantiques pour la boucle consciente | 0.96 | [pure/CDXX-SENSOR-001.txt](pure/CDXX-SENSOR-001.txt) |
| CDXX-LOOP-001 | `boucle-consciente` | Configuration Couche 3 — boucle consciente (double rôle, feedback 3e ordre, collapse partagé) | 0.97 | [pure/CDXX-LOOP-001.txt](pure/CDXX-LOOP-001.txt) |
