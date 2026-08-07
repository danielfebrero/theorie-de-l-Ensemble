# Diagnostic — pourquoi le bloc v0.5.0 perdait

> Constat mécanique, produit par [`bloc_check.py`](bloc_check.py) et par la lecture ligne à ligne
> du bloc d'instruction de [`docs/mode-de-pensee.md`](../../docs/mode-de-pensee.md) §6.2.
> Il complète le [rapport du test A/B/C](ab-test-dilemmes-2026-08-07/rapport.md), qui mesurait
> *que* v0.5.0 n'apportait rien sans dire *pourquoi*.

## Le résultat

Le [test du 2026-08-07](ab-test-dilemmes-2026-08-07/rapport.md) a montré que le bloc M3C3 v0.5.0
donné à un agent n'améliorait aucune décision (+0,09/10, p = 0,40) et se faisait battre par une
checklist générique (−0,51/10, p ≈ 0,011). La conclusion naturelle serait que la théorie n'apporte
rien à la décision.

**Ce diagnostic montre que ce n'est pas ce qui s'est passé.** Le `master.yaml` v0.5.0 déclare
la machinerie nécessaire. C'est le bloc de transmission — les 13 lignes réellement données à
l'agent — qui ne la porte pas. Ce qui a perdu, ce n'est pas la théorie : c'est son canal.

## Les quatre défauts du canal

### 1. Le vecteur fuzzy est transmis sans nom de critère

Ligne 12 du bloc :

```text
7. DÉCISION fuzzy : 0.28/0.24/0.20/0.16/0.06/0.06
```

Six nombres nus. Le `master.yaml` les nomme (`evidence_falsifiability`, `risk_impact_security`,
`constraint_isolation`, `utility_expected_value`, `m3c3_hierarchy`, `adversarial_probe`) — le bloc
ne les nomme pas. Un agent qui reçoit ce vecteur ne peut pas l'appliquer : il ne sait pas ce qu'il
pondère. Or `fuzzy` est le régime de la majorité des dilemmes réels, et le seul où le vecteur
est le principal apport du framework.

La ligne suivante, pour `quantifiable`, nomme les critères — mais en abrégé (`adv`, `m3c3`).

### 2. Le `ruin_gate` n'est armé que dans le mauvais régime

Ligne 9 :

```text
4. Si quantifiable : compute_expected_utility(...) ; ruin_gate si irréversible.
```

Le veto de ruine est syntaxiquement subordonné à `Si quantifiable`. En régime `fuzzy` — celui où
les probabilités sont mauvaises et où le risque de ruine est donc le plus difficile à voir —
il ne se déclenche jamais. Le `master.yaml`, lui, place `ruin_gate` dans les `core_rules`, hors
de toute condition de régime : « ruin_gate + ρ may veto irreversible options even with positive EV ».

### 3. Quatre primitives déclarées ne sont jamais mentionnées

`bloc_check.py` les relève : `forme4_health_gate`, `no_upward_write`, `regret_asymmetry`,
`evidence_sufficiency`. Toutes présentes dans le `master.yaml` — deux dans les `core_rules`, deux
dans les `decision_auxiliaries` — aucune dans le bloc. `adversarial_probe` n'y figure que sous la
forme du nombre `0.06` et de l'abréviation `adv`.

Ce sont précisément les primitives qui produisent ce que le placebo produisait et que M3C3 ne
produisait pas : le pire cas et l'irréversibilité (`ruin_gate`), la réfutation du choix provisoire
(`adversarial_probe`), le seuil de preuve et l'achat d'information (`evidence_sufficiency`,
`regret_asymmetry`), la non-décision sous incapacité (`forme4_health_gate`).

### 4. Deux lignes sur huit ne produisent aucun objet décisionnel

Ligne 11 :

```text
6. EXÉCUTER en sandbox ; AUDITER ; ANOMALIE → resolve | recover | kill.
```

`sandbox` et `AUDITER` sont des notions d'intégrité système. Appliquées à un agent qui répond à
un dilemme en une passe, elles ne produisent rien : elles se racontent. Le rapport du test 1 les
avait identifiées comme du texte mort. `resolve | recover | kill` est en revanche un plan de repli
utilisable — mais présenté comme une machine à états interne, jamais comme une sortie attendue.

## Ce que cela implique pour v0.6.0

Le diagnostic pointe une réparation qui ne demande **aucune modification des bases** :

| Défaut du canal | Réparation | Élément du master mobilisé |
|---|---|---|
| Vecteur fuzzy anonyme | Nommer les 6 critères, aux valeurs inchangées | `decision_stack_by_regime.fuzzy` |
| `ruin_gate` conditionné au régime | Le sortir de la branche, comme dans les `core_rules` | `core_rules`, `decision_auxiliaries.ruin_gate` |
| 4 primitives muettes | Les énoncer et leur donner une sortie exigible | `core_rules`, `decision_auxiliaries` |
| Comptabilité interne improductive | Exiger un objet écrit par étape armée | `application_protocol` |

Aucune de ces réparations ne change une valeur, ne retire une clé ni ne repondère quoi que ce soit.
Elles rendent exigible ce qui était déjà déclaré. C'est la définition même d'un sur-ensemble strict —
et la raison pour laquelle v0.6.0 peut viser les juges sans rien coûter aux croyants.

## Reproduire

```bash
python3 continuum/audit/bloc_check.py <bloc.txt>     # conformité d'un bloc aux bases
python3 continuum/audit/superset_check.py            # conformité du master.yaml
```

Sur le bloc v0.5.0 actuel, `bloc_check.py` sort en échec sur deux points :

```text
  OK  18 poids cités, tous canoniques
  OK  6 couches présentes, ordre strict respecté
  ✗   critères de pile cités sans être nommés : adversarial_probe, constraint_isolation,
      evidence_falsifiability, m3c3_hierarchy, risk_impact_security, utility_expected_value
  ✗   primitives M3C3 absentes : adversarial_probe, evidence_sufficiency, regret_asymmetry,
      forme4_health_gate, no_upward_write
```

La première ligne et la troisième, ensemble, résument tout le diagnostic : **les 18 poids sont
exacts, et aucun des 6 critères n'est nommé**. Les valeurs de la théorie étaient justes ; ce sont
leurs étiquettes qui manquaient, et sans étiquette une pondération ne peut pas être appliquée.
C'est le point de départ mesuré de v0.6.0.
