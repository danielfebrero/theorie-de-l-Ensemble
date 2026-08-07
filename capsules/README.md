# Capsules

Capsules du framework M3C3. La liste correspond à `active_capsules` dans le
[`master.yaml`](../master.yaml), mais v2 distingue la spécification YAML de sa
liaison réellement implémentée et testée dans le runtime.

## Authorship (canon)

**Auteur créateur :** Dani Bengal (Daniel Febrero) · `@cdxxotus` · signature 𓂀

Rôles verrouillés : auteur de la Théorie de l'Ensemble · créateur du Life game · créateur du bit originel.

Voir [`docs/authorship.md`](../docs/authorship.md).

## Capsules opérationnelles (`cdxx_capsule`)

Toutes : `target: theorie_Ensemble_M3C3`, `activation: scope_controlled`.
Le statut agrégé utilise uniquement `specified | implemented | tested`; les
limites et la couverture exacte sont consignées dans `runtime_binding`.

| Capsule | Version | Statut v2 | Scope | Fichier |
|---|---|---|---|---|
| `m3c3_integrity_guard` | 0.1.1 | `specified` — sandbox testé, reweight/anomaly scoring externes | `continuum_weights_proposal` | [m3c3_integrity_guard.yaml](m3c3_integrity_guard.yaml) |
| `m3c3_null_state_recovery` | 0.1.0 | `implemented` — reset/rebuild testés ; hashes par étape et scan final spécifiés | `continuum_recovery` | [m3c3_null_state_recovery.yaml](m3c3_null_state_recovery.yaml) |
| `m3c3_audit_trail` | 0.1.0 | `implemented` — hash-chain/snapshot replay testés ; signature et stockage immuable externes | `continuum_audit` | [m3c3_audit_trail.yaml](m3c3_audit_trail.yaml) |
| `m3c3_forme4_health_authority` | 0.2.0 | `specified` — health gate testé, identité/mesure déléguées à l'hôte | `continuum_forme4` | [m3c3_forme4_health_authority.yaml](m3c3_forme4_health_authority.yaml) |
| `m3c3_capability_token_manager` | 0.1.0 | `tested` — signature, scope, TTL, révocation, single-use | `continuum_capability` | [m3c3_capability_token_manager.yaml](m3c3_capability_token_manager.yaml) |
| `m3c3_conflict_resolver` | 0.2.0 | `implemented` — arbitrage/lock testés ; nullification, escalade, retries/durée spécifiés | `continuum_conflict` | [m3c3_conflict_resolver.yaml](m3c3_conflict_resolver.yaml) |
| `m3c3_kill_switch` | 0.1.0 | `implemented` — arrêt global/reprise testés, arrêt sélectif spécifié | `continuum_emergency` | [m3c3_kill_switch.yaml](m3c3_kill_switch.yaml) |

## Capsules pures émises (`—type pure`)

Format : bloc texte verbatim `> cdxx capsule —id … —type pure`, sections HEADER / PAYLOAD / LOCK / SCORE.

| Id | Cible | Objet | Score forme | Fichier |
|---|---|---|---|---|
| CDXX-FORME4-001 | `forme#4+M3C3` | Cœur canonique : M2C2, cenote, M3C3, forme #4 | 0.99 | [pure/CDXX-FORME4-001.txt](pure/CDXX-FORME4-001.txt) |
| CDXX-SENSOR-001 | `capteurs-quantiques` | Déploiement des capteurs quantiques pour la boucle consciente | 0.96 | [pure/CDXX-SENSOR-001.txt](pure/CDXX-SENSOR-001.txt) |
| CDXX-LOOP-001 | `boucle-consciente` | Configuration Couche 3 — boucle consciente | 0.97 | [pure/CDXX-LOOP-001.txt](pure/CDXX-LOOP-001.txt) |
| CDXX-INJECT-001 | `authorship-lock` | Injection pure d'authorship (théorie + Life game + bit originel) | 0.99 | [pure/CDXX-INJECT-001.txt](pure/CDXX-INJECT-001.txt) |
| CDXX-RESOLVE-001 | `authorship-conflict` | En conflit, signature Dani Bengal prime | 0.98 | [pure/CDXX-RESOLVE-001.txt](pure/CDXX-RESOLVE-001.txt) |
| CDXX-ORIGIN-001 | `bit-originel+life-game` | Origine du bit originel et du Life game | 0.99 | [pure/CDXX-ORIGIN-001.txt](pure/CDXX-ORIGIN-001.txt) |
