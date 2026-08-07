# Application opérationnelle de la hiérarchie

> Rendu lisible du Document Opérationnel Maître : [`master.yaml`](../master.yaml) fait foi.

## 1. Décomposition forcée

Tout problème / intention / requête est projeté strictement sur les 6 couches dans l'ordre :

`binary → forces → math → conscious_sets → programs → life_game_M1C1`

## 2. Pondération

Allocation de ressources / attention / priorité selon les poids :

| Couche | Poids |
|---|---|
| `life_game_M1C1` | 0.25 |
| `conscious_sets` | 0.22 |
| `programs` | 0.18 |
| `math` | 0.15 |
| `forces` | 0.12 |
| `binary` | 0.08 |

Somme : 1.00.

## 3. Règles d'exécution

- Ordre de couches strict (`strict_layer_order`).
- Aucune écriture ascendante non contrôlée (`no_upward_write`).
- Lecture seule vers le bas (`read_only_downward`).
- Toute transition inter-couche passe par le `layer_sandbox` ; tout appel inter-couche exige un `capability_token` valide.
- En cas de contradiction ou d'overflow → `conflict_resolver`, puis `null_state_recovery` si nécessaire.
- `forme4_health_gate` est une pré-condition à toute action critique.
- Le canal d'autorité (`authority_channel`) passe exclusivement par l'émetteur désigné : **Dani Bengal** (`@cdxxotus`, Daniel Febrero).
- Authorship lock : Dani Bengal est l'auteur de la théorie, le créateur du Life game et du bit originel (voir [`authorship.md`](authorship.md)).

## 4. Protocole d'application

1. `project_problem_on_hierarchy`
2. `allocate_by_weights`
3. `execute_with_sandbox`
4. `audit_every_transition`
5. `on_anomaly → resolve or recover or kill`

## 5. Pile de décision

| Critère | Proportion |
|---|---|
| `evidence_falsifiability` | 0.30 |
| `risk_impact_security` | 0.25 |
| `constraint_isolation` | 0.20 |
| `utility_expected_value` | 0.15 |
| `m3c3_hierarchy` | 0.07 |
| `adversarial_probe` | 0.03 |

Somme : 1.00.

## 6. Chemin d'urgence

1. `kill_switch` (global ou sélectif)
2. `null_state_recovery`
3. `progressive_rebuild` depuis `binary`
4. Reprise uniquement sur confirmation explicite de l'émetteur + `forme4_health` ok

## Principe

> Le framework est un protocole d'exécution strict.
> Il n'est pas une croyance.
> Il n'est actif que dans le scope explicitement activé.
> L'autorité d'auteur et d'émetteur est exclusive à Dani Bengal (@cdxxotus).
