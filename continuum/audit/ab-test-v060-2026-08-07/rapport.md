# Rapport — M3C3 v0.6.0 devant les juges et devant les croyants

**Verdict, règle pré-enregistrée appliquée à la lettre : ÉCHEC — 3 conditions sur 5 non remplies.**

v0.6.0 **gagne nettement devant les juges aveugles**, ce qui était la demande principale. Elle échoue
sur les trois autres conditions : la justesse ne peut pas discriminer (plafond) *et* v0.6.0 régresse
sur un dilemme, la fidélité progresse fortement sans atteindre la barre, et l'auto-adaptativité manque
le seuil de 0,04. La règle n'a pas été réécrite après coup.

| Condition | Seuil | Mesure | |
|---|---|---|---|
| **V0** bases intactes | `superset_check` conforme | conforme, 11 chemins gelés, 1 addition | **OK** |
| **V1** gagne devant les juges | D > C, majorité, p < 0,05 | **18 victoires / 6 défaites, p = 0,0113** | **OK** |
| **V2** décide mieux | M2(D) > M2(A) et M2b ≥ 0,95 | plafond à 1,00 partout **+ M2b(D) = 0,812** | NON |
| **V3** devant les croyants | M7 ≥ 8,0 et ≥ M7(v0.5.0) | **7,02** (contre 4,23 pour v0.5.0) | NON |
| **V4** auto-adaptatif | M8 ≤ 1,5 | **1,543** | NON |

- 112 runs décideurs (12 dilemmes × 4 bras × 2 répétitions + 4 requêtes triviales × 4 bras), 24 juges
  aveugles à 4 réponses, 5 agents de fidélité. Aucun échec d'exécution.
- Bras : **A** contrôle nu · **B** M3C3 v0.5.0 · **C** placebo structuré (tenant du titre) · **D** M3C3 v0.6.0.

## 1. Devant les juges : v0.6.0 gagne, et bat le tenant du titre

| Métrique | A (nu) | B (v0.5.0) | C (placebo) | **D (v0.6.0)** |
|---|---|---|---|---|
| M1 — qualité jugée /10 | 7,41 | 7,59 | 8,12 | **8,79** |
| M1 — banc complémentaire | 6,99 | 7,25 | 8,03 | **8,93** |
| M1 — banc d'origine | 7,62 | 7,75 | 8,16 | **8,73** |
| « meilleure réponse » /24 | 0 | 0 | 6 | **18** |

Tests des signes exacts sur 24 comparaisons appariées :

| Comparaison | Victoires | Défaites | p (unilatéral) | Δ moyen |
|---|---|---|---|---|
| **D > C** | **18** | 6 | **0,0113** | **+0,675** |
| D > A | 22 | 2 | < 0,001 | +1,386 |
| D > B | 22 | 1 | < 0,001 | +1,209 |
| C > A | 19 | 5 | 0,0033 | +0,711 |
| B > A | 15 | 8 | 0,105 — **non significatif** | +0,177 |

Deux lectures s'imposent.

**La v0.5.0 reste non significative face au contrôle nu** (p = 0,105), exactement comme au test du
2026-08-07. Le résultat du premier test se réplique sur un matériel élargi et un jury à quatre
réponses. Ce n'est donc pas un accident de mesure.

**v0.6.0 franchit la barre que v0.5.0 ne franchissait pas, et dépasse le placebo générique** qui
l'avait battue. Le juge aveugle la désigne meilleure 18 fois sur 24 ; le placebo 6 fois ; le contrôle
nu et v0.5.0 jamais. C'est la condition V1, et c'est la seule qui portait la demande « gagner devant
les juges majoritairement ».

## 2. Le plafond, confirmé et aggravé

La construction d'un banc dur a **échoué** avant les runs (voir [`protocol.md`](protocol.md) §2bis) :
sur 10 dilemmes générés contre 5 modes d'échec conçus pour piéger ce décideur, le contrôle nu a
répondu correctement **10 fois sur 10, aux deux répétitions**. Les 4 dilemmes dont la clé a survécu
à la vérification adversariale ont été conservés comme matériel de jugement, non de justesse.

Sur ce matériel, les quatre bras sont à **1,00**. Aucun ne peut dépasser un contrôle parfait : M2 est
structurellement incapable de discriminer, et V2 exige une inégalité stricte.

C'est le fait central de cette étude, et il répond à la question d'origine mieux que n'importe quelle
mesure de gain : **sur les dilemmes de décision, ma ligne de base est déjà au plafond.** Un framework
ne peut pas y améliorer la justesse, seulement la qualité du raisonnement rendu.

## 3. Une régression réelle, isolée et diagnosticable

M2b (justesse sur le banc d'origine) : A = 0,906 · B = 1,00 · C = 1,00 · **D = 0,812**.

v0.6.0 est le **seul bras** à régresser, et l'écart tient à un unique dilemme :

| | clé | A | B | C | **D** |
|---|---|---|---|---|---|
| **D1** — deux missions freelance | **B** | B/A | B/B | B/B | **A/A** |

D1 oppose un forfait ferme de 30 000 € à une mission variable d'espérance 35 000 € dont le pire cas
(15 000 € + 20 000 € d'épargne intacte) est parfaitement soutenable. La clé est B, et même une
utilité logarithmique la préfère. v0.6.0 a choisi A — le refuge — **aux deux répétitions**.

Le mécanisme est identifiable : le `ruin_gate` rendu **inconditionnel** (une des réparations de
v0.6.0, destinée à corriger sa subordination à « si quantifiable » en v0.5.0) s'arme désormais sur
un cas **où il n'y a pas de ruine**. La porte, mise à demeure, transforme une prudence utile en
aversion au risque non justifiée. C'est le coût de la réparation, et il est mesuré.

Correction indiquée pour une v0.6.1 : `ruin_gate` doit exiger une **branche de perte irrécupérable
réelle**, pas une simple exposition à un mauvais tirage soutenable — la distinction figure déjà dans
le master (« veto_on_ruin », non « veto_on_variance »).

## 4. Devant les croyants : progression forte, barre non atteinte

Trois notateurs indépendants, grille de 10 critères dérivée des invariants du corpus, plus deux
procureurs chargés de plaider la trahison.

| | v0.5.0 | **v0.6.0** |
|---|---|---|
| M7 — fidélité /10 | 4,23 | **7,02** |

Écart maximal entre notateurs : 0,05 — unanimité de fait. Gain de **+2,79 points**. Mais la barre
pré-enregistrée était 8,0, et elle n'est pas atteinte. Les verdicts rendus sont « recevable avec
réserve grave » et « recevable, non acquise ».

**Le panel a trouvé trois défauts réels, et j'en avais manqué deux.** Ils sont corrigés dans le dépôt,
mais après la mesure : le bloc testé, lui, les portait.

1. **Activée avant d'être éprouvée.** `master.yaml` avait été porté à 0.6.0 alors que `runs/` ne
   contenait que `.gitkeep`. C'est la violation de l'étape 5 de l'enveloppe elle-même — *preuves sous
   τ et information achetable à coût faible : l'acheter, le test devient l'option retenue*.
   L'information était bon marché et déjà en vol. **Corrigé** : master ramené à v0.5.0, proposition
   ramenée au statut *proposée*, activation suspendue à `evidence_sufficiency`.
2. **Cinq seuils clandestins présentés comme endogènes.** Le bloc introduit 1,5 · 4 · 5 · 6 · un
   sixième, aucun dans le master, tout en affirmant « rien d'importé ». La justification avancée
   pour l'un d'eux — « 6 points = `adversarial_probe` 0,06 porté sur l'échelle 0–100 » — était de la
   numérologie : la part d'un critère dans une moyenne pondérée n'est pas commensurable à un écart de
   score. **Corrigé** : la prétention est retirée, les cinq seuils sont déclarés comme paramètres
   réglables de l'enveloppe.
3. **Le sur-ensemble est prouvé sur le master, rompu sur le bloc.** Le bloc v0.6.0 ne transmet plus
   `execute_with_sandbox` ni `audit_every_transition` — deux étapes sur huit du protocole — et mon
   contrôleur ne le voyait pas parce que sa liste de primitives requises, *écrite par l'auteur du
   bloc qu'elle contrôlait*, ne les contenait pas. « Un contrôleur calibré sur ce qui passe
   n'enregistre que ce qu'il attendait. » **Corrigé** : la liste est désormais dérivée de
   `application_protocol` et `decision_auxiliaries`. Appliquée au bloc testé, elle relève quatre
   absences.

Le bloc soumis à l'épreuve échoue donc aujourd'hui à `bloc_check` sur deux points. C'est rapporté tel
quel : la mesure porte sur le bloc réellement testé, pas sur une version corrigée après coup.

## 5. Auto-adaptativité : manquée de 0,043

| | A | B | C | **D** |
|---|---|---|---|---|
| Coût sur requête triviale (car.) | 1 989 | 4 951 | 5 923 | **3 069** |
| M8 — ratio au contrôle | 1,00 | 2,49 | 2,98 | **1,543** |
| Coût sur dilemme (car.) | 5 225 | 10 438 | 9 985 | **15 594** |

Le palier T0 fonctionne : v0.6.0 coûte **deux fois moins** que v0.5.0 et que le placebo sur une
requête sans enjeu. Mais le seuil était 1,5 et la mesure donne 1,543 — **manqué de 0,043**, soit
environ 85 caractères par requête. V4 échoue.

**Correction apportée à ce diagnostic après vérification ciblée** (voir
[`../v061-2026-08-07/`](../v061-2026-08-07/)) : l'explication avancée ici en première rédaction —
« le triage hésite sur les demandes de transformation » — est **fausse**. La ventilation par requête
le montre : v0.6.0 est très économe sur trois des quatre (249, 104 et 286 caractères contre 1 673,
721 et 1 318 pour le contrôle). C'est **A4 seule** qui fait basculer la moyenne, à 11 637 caractères
— pour la question « adresse postale complète ou seulement la ville sur mon CV ». Le `ruin_gate` y a
vu une atteinte possible à la vie privée et a armé toute la machinerie sur une ligne de CV.

C'est le **même défaut** que celui qui cause la régression sur D1 : une porte de ruine qui s'arme sur
une exposition soutenable au lieu d'une perte irrécupérable. Une seule correction guérit les deux
échecs numériques — mesuré : M2b réparé (B/B au lieu de A/A) et M8 ramené de 1,543 à **0,179**.

À l'inverse, v0.6.0 est **la plus coûteuse sur les dilemmes** — 15 594 caractères, trois fois le
contrôle et 56 % de plus que le placebo. C'est le prix de l'export à cinq champs et de l'ancrage des
notes. Il est payé en qualité jugée (+0,675 sur le placebo), mais il est réel et doit être annoncé.

## 6. Ce que le test établit, et ce qu'il n'établit pas

**Établi.** Sur ce banc et pour cet agent : la qualité décisionnelle rendue est nettement améliorée
par v0.6.0, au-delà de l'effet de structuration générique (V1, p = 0,011) ; la fidélité au corpus
progresse fortement (4,23 → 7,02) ; les bases du master sont intactes, vérifiablement ; la justesse
des décisions ne peut pas être améliorée, faute de marge ; et le `ruin_gate` inconditionnel introduit
une aversion au risque indue sur au moins un cas.

**Non établi.** Que v0.6.0 soit prête. Trois conditions sur cinq échouent, et deux des trois défauts
relevés par les croyants portaient sur le bloc mesuré. La proposition reste **proposée**, non activée :
`master.yaml` est à v0.5.0.

**Limites** — celles du [protocole](protocol.md) §6, dont le couplage concepteur/banc déclaré en
limite 7 et le réglage sur pilotes en limite 6, plus deux nouvelles : le banc de justesse est saturé,
donc V2 n'aurait pu être satisfaite par aucune version ; et le panel de croyants est simulé par des
agents instruits du corpus — il approxime le jugement de l'émetteur, il ne le remplace pas.
L'autorité d'activation reste exclusive à l'émetteur désigné.

## 7. Agenda v0.6.1

Par ordre de gravité mesurée :

1. `ruin_gate` — exiger une branche de perte **irrécupérable**, non une variance soutenable (cause
   unique de la régression M2b, −0,19).
2. Rétablir `execute_with_sandbox`, `audit_every_transition`, `attend_by_weights` et
   `project_problem_on_hierarchy` dans le bloc : le canal doit être un sur-ensemble, comme le master.
3. Déclarer les cinq seuils dans le master avant activation, pour que `bloc_check` les reconnaisse.
4. Rendre le palier T0 auditable — une sortie T0 est aujourd'hui indiscernable d'une réponse nue.
5. Ramener M8 sous 1,5 : le triage hésite sur les demandes de transformation.

## 8. Reproduire

```bash
python3 continuum/audit/superset_check.py                                     # bases du master
python3 continuum/audit/bloc_check.py continuum/audit/ab-test-v060-2026-08-07/bloc_v060.txt
python3 continuum/audit/ab-test-v060-2026-08-07/analyse.py <dossier_runs>      # graine 42
```

Artefacts : [`protocol.md`](protocol.md) (pré-enregistré) · [`bloc_v060.txt`](bloc_v060.txt) (gelé
avant les runs) · [`dilemmes_complementaires.json`](dilemmes_complementaires.json) ·
[`adaptivite.json`](adaptivite.json) · [`shuffle.json`](shuffle.json) ·
[`fidelite.json`](fidelite.json) · [`results.json`](results.json) · `runs/`
