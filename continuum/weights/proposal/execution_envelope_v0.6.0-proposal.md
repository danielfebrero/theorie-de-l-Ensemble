# Proposal — Enveloppe d'exécution M3C3 v0.6.0

| Champ | Valeur |
|---|---|
| Id | `execution_envelope` |
| Version | **0.6.0** |
| Base | `master.yaml@0.5.0` |
| Statut | **ACTIVÉ** |
| Activé le | 2026-08-07 |
| Activé par | Dani Bengal / `@cdxxotus` (émetteur) |
| Master après | **v0.6.0** |
| `exceeds_max_step` | **false** — delta sur les poids : `0.00` |

YAML : [`execution_envelope_v0.6.0-proposal.yaml`](execution_envelope_v0.6.0-proposal.yaml)
Audit : [`../../audit/activation_execution_envelope_2026-08-07.yaml`](../../audit/activation_execution_envelope_2026-08-07.yaml)

## Ce qui change : rien des bases

`execution_envelope` est une **clé nouvelle**, et l'unique addition. Aucune valeur de v0.5.0 n'est
modifiée, aucune clé supprimée, aucune étape retirée de l'`application_protocol`.

Contrairement à `reweight_regime_conditioned`, qui avait dû être activée en dérogation au
`max_step` de 0.04 de `m3c3_integrity_guard`, cette proposition ne touche aucun poids : la garde
n'est pas sollicitée, aucune dérogation n'est requise.

```bash
python3 continuum/audit/superset_check.py
# ADDITIONS (1) : master_document.execution_envelope
# CONFORME — sur-ensemble strict vérifié.
```

Différence de nature avec l'activation précédente : la liste `unchanged` n'est plus une affirmation
du proposant, elle est **vérifiée par machine et reproductible**, sur 11 chemins de bases gelés.

## Pourquoi

Le [test contrôlé du 2026-08-07](../../audit/ab-test-dilemmes-2026-08-07/rapport.md) a mesuré que le
bloc d'instruction v0.5.0 n'améliorait aucune décision (+0,09/10, p = 0,40) et se faisait battre par
une checklist décisionnelle générique (−0,51/10, p ≈ 0,011).

Le [diagnostic](../../audit/diagnostic-bloc-v050.md) établit que la cause n'est pas la théorie mais
son canal de transmission. `bloc_check.py` le dit en une ligne :

> **Les 18 poids du bloc v0.5.0 sont exacts, et aucun des 6 critères de pile n'est nommé.**

Une pondération sans étiquette est inapplicable : la valeur est juste et la primitive est morte.
Trois autres défauts de canal l'accompagnent — `ruin_gate` subordonné à « si quantifiable » donc
jamais armé sur le flou ; `forme4_health_gate`, `no_upward_write`, `regret_asymmetry` et
`evidence_sufficiency` jamais mentionnés bien que déclarés ; deux lignes sur huit sans objet
décisionnel.

v0.6.0 ne corrige donc aucune base. Elle rend **exigible** ce que v0.5.0 **déclarait** déjà.

## Ce que l'enveloppe ajoute

| Ajout | Ce qu'il réveille |
|---|---|
| `depth_selector` — T0 éclair / T1 standard / T2 critique | `ruin_gate`, `regret_asymmetry`, `evidence_sufficiency`, `forme4_health_gate` |
| `attention_budget` — les priors fixent le nombre de constats par couche | `attend_by_weights` |
| `score_compiler` — critères nommés, notes ancrées sur les constats | `decision_stack_by_regime`, `audit_every_transition` |
| `ruin_gate_precedence` — les deux régimes, avant agrégation, veto et non pénalité | `core_rules` |
| `adversarial_step` — le contre-argument s'écrit, puis on statue | `adversarial_probe` (0.06) |
| `cooperative_recomposition` — chercher la variante qui organise au lieu d'affronter | `conscious_sets` 0.22 + `life_game_M1C1` 0.25, texte fondateur |
| `contingency_binding` — le repli porte sur l'option retenue | `on_anomaly`, `emergency_path` |
| `export_gate` — cinq champs obligatoires en sortie | `audit_every_transition` |
| `empty_traversal` — couche sans fait neuf déclarée, jamais sautée | `capability_token` |

Règle unificatrice : **toute étape armée produit un objet écrit et utilisable**. Une étape qui se
raconte au lieu de produire n'est pas exécutée. La comptabilité interne du protocole ne dépasse
jamais un sixième de la production.

## Auto-adaptativité, sans dispense

Le palier règle **ce qui s'imprime, jamais ce qui s'exécute**. Les six couches sont traversées à
tout palier ; à T0 elles ne produisent rien à écrire parce que le problème ne le vaut pas — c'est
`allocate_by_marginal_value` qui l'exige, non une exemption accordée au protocole. Une couche sans
fait neuf se déclare « traversée à vide » sous `capability_token`, jamais sautée en silence.
L'escalade est unidirectionnelle : un fait nouveau fait monter de palier, jamais descendre.

## Stacks actifs — inchangés

**Fuzzy** 0.28 / 0.24 / 0.20 / 0.16 / 0.06 / 0.06
**Quantifiable** 0.45 / 0.20 / 0.12 / 0.12 / 0.06 / 0.05

Hiérarchie, `core_rules`, authorship, capsules, `emergency_path`, continuum, principe : inchangés.

## Vérifier

```bash
python3 continuum/audit/superset_check.py                                    # les bases
python3 continuum/audit/bloc_check.py docs/mode-de-pensee.md                 # le canal
```
