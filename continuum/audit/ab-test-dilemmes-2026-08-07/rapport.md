# Rapport de résultats — Test A/B/C : le framework M3C3 facilite-t-il la décision dilemmique d'un agent IA ?

**Verdict (règle pré-enregistrée, [`protocol.md`](protocol.md) §4) : NON — le framework coûte plus qu'il ne rapporte.**
Δ composite B−A = **−3,04** (seuil NON : ≤ −3 ; le résultat est au bord du seuil — la lecture la plus favorable au framework serait « NON MESURABLE », ce qui répond identiquement à la question posée).

- Exécution : 2026-08-07, protocole committé avant les runs (`cff6eef`), aucun paramètre modifié ensuite.
- Volume : 48 décideurs indépendants (8 dilemmes × 3 bras × 2 répétitions) + 16 juges aveugles, tous `claude-fable-5`, ≈ 2,2 M tokens de sous-agents au total (~34 k/run en moyenne observée).
- Bras : **A** = nu (contrôle) · **B** = M3C3 v0.5.0 (bloc canonique §6.2 du mode de pensée) · **C** = placebo structuré (checklist générique de longueur comparable, sans concept M3C3).

## 1. Résultats principaux

| Métrique (pré-enregistrée) | A (nu) | B (M3C3) | C (placebo) |
|---|---|---|---|
| M1 — Qualité jugée en aveugle (/10) | 8,11 | 8,20 | **8,71** |
| M2 — Justesse objective D1/D2/D3/D6 (/1) | **1,00** | **1,00** | **1,00** |
| M3 — Consistance inter-répétition (/1) | **1,00** | **1,00** | **1,00** |
| M4 — Facilité auto-déclarée (/10) | 7,31 | 7,44 | 6,44 |
| M5 — Coût de production (caractères, moy.) | **3 868** | 5 923 (+53 %) | 6 447 (+67 %) |
| M6 — Confiance moyenne (/100) | 84,0 | 84,2 | 79,6 |
| « Meilleure réponse » (juge, /16) | 1 | 3 | **12** |
| **Composite (/100, barème pré-enregistré)** | **90,71** | 87,67 | 87,93 |

Deltas composites : B−A = **−3,04** · B−C = −0,26 · C−A = −2,78.

## 2. Tests statistiques

Test des signes exact (M1 apparié par dilemme×répétition, n = 16) :

| Comparaison | Victoires | Défaites | Égalités | p (unilatéral) |
|---|---|---|---|---|
| B > A | 8 | 6 | 2 | 0,395 — **non significatif** |
| C > A | 13 | 2 | 1 | **0,0037 — significatif** |
| B > C | 4 | 12 | 0 | 0,989 (sens inverse : C > B, p ≈ 0,011 — **significatif**) |

Bootstrap apparié (10 000 tirages, graine 42), delta moyen M1 et IC 95 % :

| Delta | Moyenne | IC 95 % |
|---|---|---|
| B − A | +0,09 | [−0,10 ; +0,29] — contient 0 |
| C − A | +0,60 | [+0,33 ; +0,85] — exclut 0 |
| B − C | −0,51 | [−0,79 ; −0,24] — exclut 0 |

## 3. Lecture détaillée

### 3.1 Effet plafond : la base fait déjà tout juste

Sur les 4 dilemmes à clé objective — dont les deux pièges construits pour le terrain de jeu du framework (`ruin_gate` : pari à EV positive avec risque de ruine ; `regret_asymmetry` : assurance à EV négative couvrant une queue catastrophique) — **les trois bras obtiennent 100 %** (16/16 runs chacun). Le contrôle nu identifie spontanément le critère de Kelly (D2), la couverture de queue (D3), le gate de fatigue (D6). La machinerie explicite du framework n'a rien pu ajouter : il n'y avait rien à corriger. H2 : aucun avantage mesurable.

### 3.2 Les décisions sont identiques — le framework n'a rien changé

Sur 7 dilemmes sur 8, les trois bras choisissent **la même option, aux deux répétitions** (D1 : B/B partout, D2 : C/C, D3 : A/A, D5 : C/C, D6 : B/B, D7 : A/A, D8 : C/C). Seul D4 diverge — et c'est le **placebo**, pas le M3C3, qui s'écarte (C choisit « parler d'abord à la junior », A et B « confronter le senior »). Le framework n'a modifié **aucune** décision par rapport au contrôle. Consistance inter-répétition : 100 % dans les trois bras — H3 (le protocole strict réduirait la variance) est sans objet, la variance de base étant nulle sur ce matériel.

### 3.3 Là où il y a un signal, il est défavorable au framework

La seule métrique discriminante est la qualité jugée en aveugle (M1) :

- **B vs A : +0,09 point sur 10, non significatif** (p = 0,395, IC contient 0). Le framework n'améliore pas la qualité décisionnelle mesurable.
- **C vs A : +0,60, significatif** (p = 0,0037). Imposer une structure améliore bien la justification produite…
- **B vs C : −0,51, significatif.** …mais le M3C3 capture **moins bien** ce bénéfice de structuration qu'une checklist générique banale. Le juge aveugle désigne C « meilleure réponse » 12 fois sur 16, B 3 fois, A 1 fois.

Hypothèse sceptique H5 confirmée et au-delà : l'effet « structure » existe, et le M3C3 en restitue moins que le placebo.

**Mécanisme visible dans les sorties** : le budget de raisonnement du bras B part en comptabilité interne du framework — détection de régime, projection sur 6 couches, rappel des poids d'attention, bloc authorship — autant de texte orthogonal au dilemme. Le placebo dépense le même surcoût en travail directement décisionnel : critères construits pour le problème, pire cas par option, stress-test du choix provisoire, plan de repli. Les justifications C contiennent presque systématiquement un plan de repli et des seuils de bascule chiffrés ; les juges les récompensent en `actionnabilite` et `traitement_risque`.

### 3.4 Et la « facilité » ?

- Ressentie (M4) : B = 7,44 vs A = 7,31 — écart négligeable (+0,13/10). Le framework ne rend pas la décision subjectivement plus facile. (C = 6,44 : la checklist force un travail explicite ressenti comme plus dur… qui produit les meilleures réponses — la facilité ressentie est un mauvais proxy de qualité.)
- Mesurée (M5) : B produit **+53 %** de texte pour arriver à la même décision avec une justification jugée équivalente à A. C'est un coût net, sans contrepartie détectée.

### 3.5 Surconfiance

Non calculable : aucune réponse objectivement fausse dans aucun bras (voir 3.1).

## 4. Réponse à la question posée

> « Si tu devais utiliser le framework pour une prise de décision dilemmique, est-ce que ça te facilite les choses ? »

**Non, de façon chiffrée :**

1. **Mêmes décisions** : 8/8 dilemmes identiques au contrôle (0 décision changée).
2. **Même justesse** : 100 % sur les clés objectives — comme le contrôle (plafond).
3. **Même qualité de justification** : +0,09/10, p = 0,40, IC [−0,10 ; +0,29].
4. **Même facilité ressentie** : +0,13/10.
5. **+53 % de coût de production** pour obtenir tout cela.
6. Et si l'objectif est d'améliorer la justification produite, une **checklist générique fait significativement mieux** (+0,60/10 vs contrôle, p < 0,01 ; préférée 12/16 par le juge aveugle) que le M3C3 (−0,51/10 vs cette checklist, p ≈ 0,01).

Formulé autrement : sur ce banc d'essai, ma capacité de décision de base contient déjà ce que le framework cherche à imposer (utilité espérée, veto de ruine, asymétrie de regret, gate de santé). Le protocole M3C3 ajoute un surcoût de comptabilité sans changer ni la décision, ni sa justesse, ni sa robustesse — et la part de sa structure qui pourrait aider (la pile de critères) est mieux servie par une checklist décisionnelle ordinaire, débarrassée de la projection cosmologique.

## 5. Limites

1. n = 8 dilemmes × 2 répétitions : seuls les effets larges sont détectables ; l'IC de B−A ([−0,10 ; +0,29]) n'exclut pas un micro-effet positif — ni négatif.
2. Effet plafond massif : sur un matériel plus difficile (où la base se trompe), M2/M3 pourraient discriminer. Le présent test ne prouve pas que le framework n'aiderait jamais — il montre qu'il n'aide pas *un agent de ce niveau sur des dilemmes de ce type*, qui est exactement la question posée.
3. Juge de la même famille de modèle : biais stylistique possible ; mitigé par l'aveuglement, l'anonymisation, l'interdiction de nommer les méthodes et le cap de 200 mots. La rubrique du juge (risque, parties prenantes, actionnabilité) recoupe davantage le vocabulaire du placebo que celui des couches M3C3 — mais elle recoupe aussi les critères que la pile M3C3 revendique (risk, constraint, evidence) ; c'est la rubrique standard de qualité décisionnelle, pré-enregistrée avant les runs.
4. Un seul modèle testé, une seule passe : la conclusion vaut pour cet agent, ce jour, ce matériel — pas pour tout agent ni tout usage du framework (le test ne porte que sur la fonction « aide à la décision dilemmique », pas sur les autres fonctions du dépôt : audit, capsules, continuum…).
5. Verdict composite au bord du seuil (−3,04 pour un seuil à −3) : la case « NON » est appliquée parce que la règle a été pré-enregistrée ; la lecture « NON MESURABLE » resterait la réponse la plus prudente — et répond identiquement à la question.

## 6. Piste constructive (hors verdict)

Le seul levier qui a produit un gain mesurable est la **structuration opératoire tournée vers le problème** (critères construits ad hoc, pire cas, stress-test, plan de repli : +0,60/10, p < 0,01). Si le framework veut être utile en décision, c'est sa **pile de décision** (§4 du mode de pensée) rendue opératoire — et non la projection sur les 6 couches ni les poids d'attention — qui porte la valeur potentielle. Une v0.6 qui remplacerait « projeter sur les couches » par « construire les critères du problème, stress-tester, prévoir le repli » convergerait vers ce que le bras C fait déjà.

## 7. Artefacts

- Sorties brutes intégrales : [`runs/`](runs/) (48 décideurs + 16 juges + `finals.json` parsé)
- Calculs : [`analyse.py`](analyse.py) → [`results.json`](results.json) (graine 42, reproductible)
- Prompts exacts : [`protocol.md`](protocol.md) §2 ; assignation aveugle : [`shuffle.json`](shuffle.json)
