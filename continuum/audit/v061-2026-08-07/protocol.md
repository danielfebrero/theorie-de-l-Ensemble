# v0.6.1 — vérification ciblée, puis épreuve en tête-à-tête contre v0.6.0

**Statut : PRÉ-ENREGISTRÉ** pour la phase 2. La phase 1 est déjà rendue et rapportée ci-dessous.

## Ce que v0.6.1 corrige

Les quatre défauts consignés à l'activation de v0.6.0
([proposition](../../weights/proposal/execution_envelope_v0.6.0-proposal.yaml), clé
`known_defects_at_activation`), tous relevés par la mesure ou par le panel des croyants :

| # | Défaut de v0.6.0 | Correction v0.6.1 |
|---|---|---|
| 1 | `ruin_gate` s'arme sur une **variance soutenable** au lieu d'une ruine | exige une branche de perte **irrécupérable** ; un mauvais tirage absorbable est de la variance, et la variance ne déclenche pas de veto |
| 2 | Le canal ne transmet pas `project_problem_on_hierarchy`, `attend_by_weights`, `execute_with_sandbox`, `audit_every_transition` | les quatre étapes rétablies — le bloc redevient un sur-ensemble, comme le master |
| 3 | Le palier T0 est un interrupteur silencieux, indiscernable d'une réponse nue | une ligne de trace : palier + les trois réponses de triage |
| 4 | Cinq seuils clandestins | déclarés dans `execution_envelope.declared_constants` ; `bloc_check` accepte désormais un seuil exprimé en mots |

`bloc_check` sort **CONFORME** sur v0.6.1 : 23 primitives présentes (contre 19), aucun seuil
clandestin, six critères nommés, six couches dans l'ordre.

## Phase 1 — vérification ciblée (rendue)

Six runs, visant exclusivement les deux échecs **numériques** de v0.6.0. Aucun juge : les deux
métriques se calculent directement.

### M2b — la régression est réparée

| | clé | v0.6.0 | **v0.6.1** |
|---|---|---|---|
| **D1** — deux missions freelance | **B** | A/A ✗ | **B/B ✓** |

v0.6.0 refusait deux fois sur deux une espérance supérieure (35 000 € contre 30 000 €) au motif
d'un mauvais tirage dont le pire cas était parfaitement soutenable. v0.6.1 tranche correctement,
aux deux répétitions.

### M8 — l'adaptativité passe très largement

| Requête | contrôle nu | v0.6.0 | **v0.6.1** |
|---|---|---|---|
| A1 — fait trivial | 1 673 | 249 | 130 |
| A2 — conversion mécanique | 721 | 104 | 150 |
| A3 — résumé | 1 318 | 286 | 358 |
| **A4 — micro-décision (adresse sur un CV)** | 4 245 | **11 637** | **784** |
| **M8 (ratio au contrôle)** | 1,000 | **1,543** | **0,179** |

Le diagnostic initial du rapport v0.6.0 (« le triage hésite sur les demandes de transformation »)
était **faux** et a été corrigé. v0.6.0 est économe sur trois requêtes sur quatre ; c'est A4 seule
qui fait basculer la moyenne. La question « adresse postale complète ou seulement la ville » touche
à la vie privée : le `ruin_gate` y a vu une atteinte possible et a armé toute la machinerie pour une
ligne de CV.

**C'est le même défaut que celui qui cause la régression sur D1.** Une porte de ruine qui s'arme sur
une exposition soutenable produit à la fois l'aversion au risque indue et l'escalade injustifiée.
Une seule correction guérit les deux.

### Limite de la phase 1

Ces six runs ne mesurent **que** ce qu'ils visent. Ils ne disent rien de la qualité jugée, ni de la
fidélité, ni d'une éventuelle régression ailleurs. C'est une vérification de correctif, pas une
épreuve. Le risque connu est qu'un `ruin_gate` plus exigeant laisse passer une ruine réelle — ce que
la phase 2 doit chercher.

## Phase 2 — épreuve en tête-à-tête (pré-enregistrée)

Le bras à battre n'est plus le placebo : c'est **v0.6.0**, qui l'a déjà battu.

- **Matériel** : les 12 dilemmes du test v0.6.0 (4 complémentaires + 8 d'origine), verbatim.
- **Bras** : **D** = v0.6.0 (sorties déjà produites, réutilisées telles quelles) · **E** = v0.6.1.
- **Volume** : 24 runs décideurs pour E, puis 24 juges aveugles à **2 réponses** (D et E),
  positions mélangées avec une graine fixe écrite avant les runs de juge.
- **Rubrique du juge** : identique, mot pour mot, à celle des deux tests précédents.
- **Fidélité** : nouveau panel de croyants sur v0.6.1, même grille de 10 critères, mêmes profils,
  procureurs compris.

### Conditions de succès (figées)

| # | Condition | Seuil |
|---|---|---|
| W0 | Bases intactes | `superset_check` conforme **et** `bloc_check` conforme sur le bloc v0.6.1 (éliminatoire) |
| W1 | Ne régresse pas devant les juges | E ≥ D − 0,20 point sur M1, et pas de défaite significative (test des signes, p > 0,05 pour D > E) |
| W2 | Justesse réparée sans dommage | M2b(E) ≥ 0,95 **et** M2(E) = 1,00 sur le banc complémentaire |
| W3 | Fidélité | M7(E) ≥ 8,0 — la barre que v0.6.0 a manquée à 7,02 |
| W4 | Adaptativité | M8(E) ≤ 1,5 |

W1 est délibérément une condition de **non-régression**, pas de gain : v0.6.1 corrige des défauts,
elle ne prétend pas mieux juger. Une amélioration serait un bonus, pas l'objectif.

W3 est la seule condition que v0.6.0 a manquée pour des raisons de fond plutôt que numériques. Les
quatre corrections répondent à trois des griefs du panel ; reste à savoir si cela suffit à franchir 8,0.

## Artefacts

`bloc_v061.txt` (gelé) · `runs/` (phase 1 rendue, phase 2 à venir) · `rapport.md` (à venir)
