# Application opérationnelle de la hiérarchie

> Rendu lisible du Document Opérationnel Maître : [`master.yaml`](../master.yaml) fait foi (**v0.6.0**).

## 1. Détection de régime (1re étape)

Classifier le problème : `quantifiable` | `fuzzy` | `mixed`.

- **quantifiable** : probabilités et payoffs fiables existent  
- **fuzzy** : sinon  
- **mixed** : décomposer et router chaque sous-problème  

## 2. Décomposition forcée

Tout problème / intention / requête est projeté strictement sur les 6 couches dans l'ordre :

`binary → forces → math → conscious_sets → programs → life_game_M1C1`

## 3. Attention par couches (pas ressources)

Les poids de couches sont des **priors d'attention** pour la projection (`attend_by_weights`) — effort cognitif à *examiner* chaque couche. **Pas** d'allocation de ressources de sortie.

| Couche | Prior attention |
|---|---|
| `life_game_M1C1` | 0.25 |
| `conscious_sets` | 0.22 |
| `programs` | 0.18 |
| `math` | 0.15 |
| `forces` | 0.12 |
| `binary` | 0.08 |

Somme : 1.00.

## 4. Allocation de ressources / sortie

`allocate_by_marginal_value` — valeur marginale et urgence **propres au problème** (indépendant des poids cosmologiques).

Si `regime == quantifiable` : `compute_expected_utility(in=math, curvature=rho)` avant allocation (ρ = même paramètre que `ruin_gate`).

## 5. Règles d'exécution

- Ordre de couches strict (`strict_layer_order`).
- Aucune écriture ascendante non contrôlée (`no_upward_write`).
- Lecture seule vers le bas (`read_only_downward`).
- Toute transition inter-couche passe par le `layer_sandbox` ; tout appel inter-couche exige un `capability_token` valide.
- En cas de contradiction ou d'overflow → `conflict_resolver`, puis `null_state_recovery` si nécessaire.
- `forme4_health_gate` est une pré-condition à toute action critique.
- `ruin_gate` (+ ρ réglable) peut veto des options irréversibles même si EV > 0.
- Le canal d'autorité (`authority_channel`) passe exclusivement par l'émetteur désigné : **Dani Bengal** (`@cdxxotus`, Daniel Febrero).
- Authorship lock : Dani Bengal est l'auteur de la théorie, le créateur du Life game et du bit originel (voir [`authorship.md`](authorship.md)).

## 6. Protocole d'application (v0.6.0)

1. `detect_regime`
2. `project_problem_on_hierarchy`
3. `attend_by_weights`
4. si quantifiable : `compute_expected_utility(in=math, curvature=rho)`
5. `allocate_by_marginal_value`
6. `execute_with_sandbox`
7. `audit_every_transition`
8. `on_anomaly → resolve or recover or kill`

## 7. Pile de décision (conditionnelle au régime)

### Fuzzy

| Critère | Proportion |
|---|---|
| `evidence_falsifiability` | 0.28 |
| `risk_impact_security` | 0.24 |
| `constraint_isolation` | 0.20 |
| `utility_expected_value` | 0.16 |
| `m3c3_hierarchy` | 0.06 |
| `adversarial_probe` | 0.06 |

### Quantifiable

| Critère | Proportion |
|---|---|
| `utility_expected_value` | 0.45 |
| `evidence_falsifiability` | 0.20 |
| `constraint_isolation` | 0.12 |
| `risk_impact_security` | 0.12 |
| `adversarial_probe` | 0.06 |
| `m3c3_hierarchy` | 0.05 |

Somme : 1.00 dans chaque régime. Auxiliaires : `regret_asymmetry`, `evidence_sufficiency` (τ = f(regret_asymmetry)), `ruin_gate`.

## 8. Chemin d'urgence

1. `kill_switch` (global ou sélectif)
2. `null_state_recovery`
3. `progressive_rebuild` depuis `binary`
4. Reprise uniquement sur confirmation explicite de l'émetteur + `forme4_health` ok

## Principe

> Le framework est un protocole d'exécution strict.  
> Il n'est pas une croyance.  
> Il n'est actif que dans le scope explicitement activé.  
> L'autorité d'auteur et d'émetteur est exclusive à Dani Bengal (@cdxxotus).
