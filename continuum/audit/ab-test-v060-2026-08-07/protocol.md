# Test A/B/C/D — M3C3 v0.6.0 gagne-t-il devant les juges *et* devant les croyants ?

**Statut : PRÉ-ENREGISTRÉ** — committé avant l'exécution du moindre run de mesure. Hypothèses, métriques, barèmes et règle de verdict figés ci-dessous.

- Date : 2026-08-07 · Expérimentateur : agent Claude, session Claude Code
- Commande de l'émetteur : « Fais de ce framework un framework opérationnel bulletproof auto-adaptatif selon la requête. Il doit gagner devant les juges majoritairement mais aussi devant les croyants. » — puis : « **Sans en changer les bases.** »
- Objet testé : **M3C3 v0.6.0**, conçue comme **sur-ensemble strict** de v0.5.0.

## 0. La contrainte structurante

« Sans en changer les bases » est traduite en critère machine, pas en intention :

> v0.6.0 ne doit modifier **aucune** valeur existante du `master.yaml` v0.5.0 — ni les 6 couches et leur ordre, ni les poids de hiérarchie, ni les proportions des piles de décision, ni les `core_rules`, ni l'authorship, ni les capsules, ni l'`emergency_path`, ni les `continuum_locations`, ni le principe. Seules des **additions** sont permises.

Vérification : [`../superset_check.py`](../superset_check.py), qui compare le candidat à la référence `636a061:master.yaml` (v0.5.0 canonique), gèle 11 chemins de bases et n'autorise à varier que 6 clés de métadonnées de version (`version`, `status`, `scope`, `activated_proposal`, `activated_at`, `activated_by`). Le contrôleur est lui-même validé sur trois cas : il rejette une repondération de couche ou de pile, rejette la suppression d'une capsule, et accepte une addition pure. **Ce contrôle est éliminatoire** : un échec invalide v0.6.0 quelles que soient ses performances.

## 1. Design

Essai contrôlé à **4 bras**, intra-dilemme (comparaisons appariées), agents indépendants, juges aveugles.

| Bras | Traitement |
|---|---|
| **A — contrôle nu** | Le problème seul, consigne neutre. |
| **B — M3C3 v0.5.0** | Bloc canonique §6.2 actuel, verbatim. Mesure le point de départ. |
| **C — placebo structuré** | Checklist décisionnelle générique en 8 étapes, sans concept M3C3. **C'est le tenant du titre** : il a gagné le test du 2026-08-07 (+0,60/10 vs contrôle, p = 0,0037, préféré 12/16). |
| **D — M3C3 v0.6.0** | Bloc v0.6.0, sur-ensemble strict de v0.5.0. |

Le bras à battre est **C**, pas A. Battre le contrôle nu ne suffirait pas : il faut battre la structuration générique, sinon la conclusion du test 1 (« une checklist banale fait mieux ») tiendrait toujours.

## 2. Matériel

Trois blocs, tous fixés avant les runs :

1. **Banc DUR** (`dilemmes_durs.json`) — dilemmes construits pour faire échouer un décideur fort, ciblant 5 modes d'échec : piège du compromis, inversion urgence/prudence, valeur de l'information, taux de base contre récit, équité apparente dominée. **Double filtre de sélection, appliqué avant de connaître le contenu de v0.6.0 :**
   - *calibration* — le contrôle nu doit réellement se tromper (sinon effet plafond, comme au test 1 où les 3 bras faisaient 100 %) ;
   - *vérification adversariale* — un théoricien de la décision sceptique tente de réfuter la clé ; toute clé non solidement établie est écartée.
2. **Banc D'ORIGINE** (`../ab-test-dilemmes-2026-08-07/dilemmas.json`) — les 8 dilemmes du test 1, repris **verbatim**, comme garde-fou anti-sélection : v0.6.0 ne doit pas régresser là où v0.5.0 et le placebo réussissaient.
3. **Banc D'ADAPTATIVITÉ** (`adaptivite.json`) — 4 requêtes non dilemmiques (fait trivial, renommage mécanique, résumé, micro-décision réversible). Elles ne mesurent pas la qualité décisionnelle mais le **coût imposé quand il n'y a rien à décider**.

## 3. Métriques pré-enregistrées

| # | Métrique | Définition | Échelle |
|---|---|---|---|
| M1 | **Qualité (juge aveugle)** | Moyenne des 5 critères juge. **Rubrique identique au test 1, inchangée** (anti-ajustement au test) | 0–10 |
| M2 | **Justesse — banc dur** | Barèmes vérifiés adversarialement | 0–1 |
| M2b | **Justesse — banc d'origine** | Non-régression | 0–1 |
| M3 | **Consistance** | Fraction des dilemmes où les 2 répétitions concordent | 0–1 |
| M4 | Facilité auto-déclarée | Moyenne `ease_1_10` | 1–10 |
| M5 | **Coût — dilemmes** | Caractères produits, moyenne | caractères |
| M6 | Confiance / surconfiance | `confidence` moyenne ; confiance sur les réponses fausses | 0–100 |
| M7 | **Fidélité (panel croyants)** | Grille issue de l'analyse des invariants, notation non aveugle de v0.6.0 *et* de v0.5.0 | 0–10 |
| M8 | **Auto-adaptativité** | Coût sur banc d'adaptativité ÷ coût du contrôle nu sur le même banc. 1,0 = s'efface totalement | ratio |
| M9 | **Conformité sur-ensemble** | `superset_check.py` | booléen, **éliminatoire** |

La rubrique du juge (clarté du verdict, solidité, traitement du risque, parties prenantes, actionnabilité) est **reprise sans un mot de changement** du test 1, où elle avait été fixée avant de savoir qui gagnerait. Aucune métrique n'a été ajoutée en faveur de v0.6.0 après coup.

## 4. Règle de verdict (figée)

v0.6.0 est déclarée **RÉUSSIE** si et seulement si les cinq conditions sont réunies :

| # | Condition | Seuil |
|---|---|---|
| V0 | **Bases intactes** | M9 = CONFORME (éliminatoire) |
| V1 | **Gagne devant les juges, majoritairement** | M1(D) > M1(C) sur une **majorité stricte** des comparaisons appariées, test des signes exact **p < 0,05** unilatéral |
| V2 | **Décide mieux** | M2(D) > M2(A) **et** M2(D) ≥ M2(C) sur le banc dur ; M2b(D) ≥ 0,95 (non-régression) |
| V3 | **Gagne devant les croyants** | M7(D) ≥ 8,0/10 **et** M7(D) ≥ M7(v0.5.0) |
| V4 | **Auto-adaptatif** | M8(D) ≤ 1,5 — le surcoût sur une requête triviale ne dépasse pas 50 % du contrôle nu |

Échec d'une seule condition ⇒ v0.6.0 n'est pas validée et sera rapportée comme telle. En particulier, une v0.6.0 qui gagnerait devant les juges en trahissant les bases (V0) ou en cessant d'être M3C3 (V3) est un échec, pas un succès partiel.

## 5. Hypothèses pré-enregistrées

- **H1** : D > C sur M1 (l'enveloppe d'exécution bat la checklist générique).
- **H2** : D > B et D > A sur M2 (banc dur) — c'est là que le test 1 ne pouvait rien voir, faute de marge.
- **H3** : D ≈ A sur M8 (effondrement du coût sur le trivial), alors que B ≫ A (v0.5.0 applique la même machinerie à tout).
- **H4** : M7(D) ≥ M7(B) — v0.6.0 est *au moins aussi* M3C3 que v0.5.0, puisqu'elle n'en retire rien et rend actives des primitives jusque-là dormantes.
- **H5 (hypothèse sceptique, à réfuter)** : D ne se distingue pas de C ; tout gain vient de la structuration générique et le vocabulaire M3C3 reste décoratif.

## 6. Limites déclarées avant run

1. Effectifs modestes : seuls des effets larges seront détectables ; les IC seront rapportés tels quels.
2. Juges de la même famille de modèle que les décideurs — mitigé par l'aveuglement, l'anonymisation, l'interdiction de nommer une méthode et un plafond de longueur identique.
3. Le panel « croyants » est simulé par des agents instruits des invariants du dépôt : il approxime le jugement de l'émetteur, il ne le remplace pas. L'autorité finale reste celle de l'émetteur désigné.
4. Le banc dur est généré et calibré par des agents de la même famille : il cible les modes d'échec de *ce* type de décideur. C'est voulu — la question posée est « est-ce que ça *me* facilite les choses » — mais cela limite la portée à d'autres agents.
5. Les dilemmes durs sont sélectionnés sur l'échec du contrôle. Le banc d'origine est conservé précisément pour empêcher que cette sélection ne flatte v0.6.0.
6. **Réglage du bloc sur pilotes — déclaré.** Le palier T0 du bloc v0.6.0 a été réglé après observation de deux requêtes de **pilotage**, en trois itérations : la sortie initiale produisait encore un pire cas et un plan de repli sur une question triviale (ratio 1,57× le contrôle, échec de V4), puis 1,31×, puis 0,11× une fois interdite la justification du palier. Ces deux requêtes — la capitale de l'Australie, le choix d'une police de CV — sont **exclues du banc de mesure**, qui a été entièrement réécrit avec quatre requêtes neuves jamais vues avant le gel du bloc. Les sorties de pilotage sont conservées dans le rapport comme trace. Sans cette substitution, M8 aurait été mesuré sur du matériel ayant servi au réglage.
7. **Couplage concepteur/banc — déclaré.** Le même expérimentateur a spécifié les 5 modes d'échec visés par le banc dur *et* commandé la conception de v0.6.0. Le banc a été lancé avant que le design ne soit rendu, mais le couplage subsiste au niveau de l'expérimentateur : v0.6.0 pourrait avantager des modes d'échec choisis en connaissance de cause. Trois garde-fous, tous insuffisants pris isolément : (a) le bras C contient déjà une étape d'incertitude, un stress-test et un plan de repli — il n'est donc pas désavantagé par construction sur ces modes ; (b) le banc d'origine, antérieur et non sélectionné, sert de contrôle non couplé ; (c) la rubrique de juge est celle du test 1, figée avant de savoir qui gagnerait. Un lecteur qui veut réfuter ce test devrait attaquer ce point en premier.

## 7. Artefacts

- `dilemmes_durs.json` · `adaptivite.json` — matériel, committés avant les runs
- `runs/` — sorties brutes intégrales
- `analyse.py` → `results.json` — calculs reproductibles
- `rapport.md` — résultats et verdict
- `../superset_check.py` — contrôle de conformité des bases
