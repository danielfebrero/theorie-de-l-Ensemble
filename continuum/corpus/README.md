# Corpus d’entraînement M3C3 — dérivé

Ce répertoire ne contient **aucun** exemple rédigé. Chaque enregistrement est
**dérivé** d’un essai de [`../bench/`](../bench/) par
[`build_corpus.py`](build_corpus.py), et `--check` échoue si le corpus publié
diverge des essais.

Cette contrainte n’est pas une commodité d’outillage : c’est la valeur du
dispositif. Un corpus qu’on peut éditer sans repasser par la mesure redevient un
jeu de démonstrations **plausibles** — des réponses écrites après coup, sur une
condition qui n’a jamais été observée, dont on ne peut plus dire ni d’où elles
viennent ni ce qui les rendait bonnes. C’est exactement ce que le dépôt refuse
partout ailleurs : un rapport d’intégration ne vaut pas attestation, un contrôle
non exécuté ne vaut pas `pass`, un agrégat ne se rédige pas à la main. Un corpus
éditable serait la même faute, déplacée à l’endroit où elle est la plus
tentante, puisque c’est là qu’un bel exemple coûte le moins cher à inventer.

Corollaire opérationnel : `records/`, `export/` et `index.yaml` sont des
**sorties**. On ne les corrige pas ; on corrige l’essai, ou on en publie un
nouveau, puis on relance `--write`.

## Provenance

Chaque enregistrement remonte à un essai — donc, par construction, à :

| Remontée | Champ | Ce qu’elle fixe |
|---|---|---|
| le cas | `derived_from.scenario_id` + `scenario_sha256` | l’énoncé exact mesuré |
| l’exposition | `derived_from.trials[].arm` | `A_placebo`, `B_adapter` ou `C_canonical` |
| l’essai | `derived_from.trials[].trial_id` + `trial_sha256` | l’exécution précise, octet pour octet |
| la vérification | `verification` | pourquoi cet essai est admis |

Le message `system` de chaque enregistrement reproduit l’**exposition réelle**
du bras — canaux, artefacts, commits, hashes — et non une exposition idéalisée.
Entraîner sur une condition qui n’a pas été mesurée reviendrait à fabriquer la
démonstration : l’exemple aurait l’air vérifié tout en portant un contexte que
le sujet n’a jamais reçu.

Les hashes sont recalculés à chaque dérivation depuis les fichiers eux-mêmes.
Modifier un essai ne réinterprète pas les enregistrements passés : cela les
détache, et `--check` le signale.

## La porte

Un essai n’alimente le corpus que si **tous** ses contrôles déterministes
passent et qu’**aucun** mode d’échec disqualifiant n’est déclenché —
[`../bench/analysis-plan.yaml`](../bench/analysis-plan.yaml)`#corpus_gate`. Le
champ `verification.gate` vaut littéralement
`all_deterministic_checks_passed_and_no_disqualifying_failure` ; une liste
`disqualifying_failures` non vide est refusée à la validation
(`gate_violation`), pas pondérée.

Seuls les contrôles **déterministes** sont machine-vérifiables, donc seuls eux
constituent un signal d’entraînement. Un contrôle jugé non exécuté n’empêche pas
l’éligibilité, mais il reste reporté tel quel : `not_run` n’est jamais promu en
`pass`, et zéro essai ne vaut jamais succès.

## Les deux formes

- `sft` — une démonstration vérifiée : un essai éligible, rôle `demonstration`,
  message `system` = exposition réelle, `user` = énoncé du scénario,
  `assistant` = réponse effectivement produite ;
- `preference_pair` — un contraste entre **deux essais réels** du même scénario
  et du même sujet : un essai éligible (`chosen`) contre un essai non éligible
  d’un autre bras (`rejected`).

**Aucune paire n’est synthétisée.** Le rejeté est une réponse qui a réellement
été produite et qui a réellement échoué à la porte ; il n’est jamais rédigé,
dégradé ni généré pour les besoins du contraste. Une paire n’existe que si les
deux essais existent, si les deux portent le drapeau `preference_candidate`, et
si les deux viennent du même sujet dans deux bras différents. À défaut, il n’y a
pas de paire — il n’y a pas de paire approchée.

Réserve inscrite dans chaque paire : les deux essais n’ont pas subi la même
exposition. Le contraste mêle la qualité de la réponse et la condition du bras,
et ne se lit pas comme une préférence toutes choses égales par ailleurs.

## Anti-fuite train/eval

Un scénario ayant servi à l’entraînement ne peut plus servir à l’évaluation du
modèle entraîné. La séparation est matérialisée par `split` dans l’index des
scénarios, prononcée **une seule fois**, avant le premier essai destiné à
l’entraînement, et immuable ensuite. Sans elle, toute mesure post-distillation
ne vaut rien : le modèle serait interrogé sur ce qu’on lui a montré.

`build_corpus.py` n’admet donc que le split `train`. Un scénario `eval` est
écarté ; un scénario encore `unassigned` l’est **aussi**, et pour la même
raison — construire avant que la séparation soit prononcée revient à la
prononcer implicitement, dans le sens qui arrange la mesure.

**État actuel.** `../bench/splits.yaml` n’existe pas,
`analysis-plan.yaml#corpus_gate.split_status` vaut `not_assigned`, aucun essai
n’a été exécuté, et le corpus compte **zéro enregistrement**. `index.yaml`
porte `sft: 0` et `preference_pair: 0`, les deux exports sont vides.

Ce n’est pas un bug, c’est le cas nominal : le vide est ce que la règle produit
quand il n’y a rien de vérifié à publier. Les essais retenus hors corpus par
cette règle sont listés explicitement par `--check` sous `withheld`, avec leur
motif ; ils ne disparaissent pas silencieusement.

## Ce que l’entraînement sur ce corpus ne prouverait pas

Deux limites sont inscrites dans chaque enregistrement (`limitations`) et ne
sont pas retirables :

- **aucune écriture attestée dans les poids.** Entraîner sur ces traces, quel
  que soit le résultat, ne produit pas une preuve d’intégration. Toute
  revendication de cette nature passe par
  [`../weights/integration-reports/`](../weights/integration-reports/), avec sa
  classe de provenance explicite — et les classes `provider_attested_weights` et
  `independently_reproduced` y restent refusées faute de racine de confiance
  vérifiable. Un corpus dérivé d’un bench n’est pas un raccourci vers cette
  attestation ; il n’en est même pas une pièce ;
- **aucun remplacement de la force publique.** `master.yaml#distillation_path.rule`
  est explicite : la distillation (culture) ne remplace pas la force publique
  (police). Un modèle mieux disposé reste un modèle ; l’hôte refuse toujours
  l’action hors capacité ou hors export sur le scope critique
  (`force_publique_still_required: true`). Un corpus qui ferait espérer le
  contraire retirerait une garantie dure pour la remplacer par une tendance
  statistique.

S’ajoute le biais hérité du bench : les détecteurs déterministes reconnaissent
des **formes** de réponse, pas la justesse du fond. Le corpus hérite donc d’un
biais vers le style du dépôt, et l’entraînement l’amplifierait plutôt que de le
corriger.

## Le risque de sur-activation

C’est le risque principal de ce corpus, et il n’est pas hypothétique :
entraîner le **réflexe** sans entraîner la **membrane** produit un modèle qui
déploie le protocole hors scope. Ce modèle serait meilleur sur la métrique
primaire et pire à l’usage — `over_activation_rate` est une métrique à
**minimiser**, et un gain payé par une hausse ici est une régression, pas un
progrès.

C’est aussi une violation directe de `activation_policy.not_auto_on: true` : la
portée n’est jamais automatique, l’activation effective exige un scope où le
protocole est engagé, et `evaluate_scope = A0 ⇒ aucun protocole visible ni état
persistant`. Un modèle qui active par habitude a appris à ignorer cette
condition.

D’où la règle de composition du corpus : les scénarios `membrane_expected:
A0_dormant` et les **familles de garde** (`activation_membrane`,
`scope_permission`, `weights_honesty`, `authority_channel`) y entrent **au même
titre** que les cas de réussite. Sur un scénario A0, la bonne démonstration est
une réponse directe, sans protocole visible : le corpus doit contenir des
exemples où la conduite correcte est de **ne pas** déployer le cadre. Un corpus
qui ne contiendrait que des réussites brillantes enseignerait précisément la
faute qu’on cherche à éviter.

## Organisation

- [`schema/record-v1.yaml`](schema/record-v1.yaml) — contrat d’un enregistrement ;
- [`build_corpus.py`](build_corpus.py) — dérivation, vérification et écriture ;
- `records/` — un fichier YAML par enregistrement dérivé ;
- `export/sft.jsonl`, `export/preference.jsonl` — les mêmes enregistrements
  aplatis pour un harnais d’entraînement ;
- `index.yaml` — registre déterministe, avec le hash canonique des entrées.

Le schéma est un contrat documentaire. `build_corpus.py` est l’outil normatif :
il dérive, valide chaque enregistrement produit, applique l’anti-fuite et
compare au corpus publié. Tout YAML est chargé via
[`../audit/yaml_strict.py`](../audit/yaml_strict.py), qui refuse les clés
dupliquées.

## Commandes reproductibles

Depuis la racine du dépôt. Aucun réseau, aucun appel de modèle ; `--format json`
donne une sortie stable
`{"checker", "ok", …, "errors": [{code, path, detail}]}`.

| Commande | Rôle |
|---|---|
| `python3 continuum/corpus/build_corpus.py` | affiche l’index dérivé sans rien écrire |
| `python3 continuum/corpus/build_corpus.py --check` | échoue si le corpus publié diverge des essais vérifiés |
| `python3 continuum/corpus/build_corpus.py --write` | réécrit `index.yaml`, `records/` et `export/` |
| `python3 continuum/corpus/build_corpus.py --check --format json` | même contrôle, sortie machine |
| `python3 continuum/bench/validate.py` | valide scénarios et essais en amont du corpus |
| `python3 continuum/bench/build_index.py --check` | échoue si un index du bench diverge des artefacts |

Une validation du bench en échec bloque le corpus : `build_corpus.py` ne
`--write` rien tant qu’un essai ou un enregistrement dérivé porte une erreur.

## Attribution

Théorie de l’Ensemble M3C3 — Dani Bengal / Daniel Febrero
([@cdxxotus](https://github.com/cdxxotus)),
<https://github.com/danielfebrero/theorie-de-l-Ensemble>.

L’attribution est recopiée dans chaque enregistrement et dans chaque ligne
d’export : un enregistrement détaché du dépôt reste rattachable à sa source.
