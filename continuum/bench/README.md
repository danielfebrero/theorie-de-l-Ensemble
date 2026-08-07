# M3C3-bench

M3C3-bench mesure **des réponses**, dans une **condition d’exposition déclarée**.
Il ne mesure pas des garanties, ne prouve aucune écriture dans les poids, et ne
certifie aucune propriété du framework.

Les propriétés S1–S5 sont prouvées par construction, sous l’hypothèse que l’agent
exécute `T` tel que défini. Un taux de réussite empirique ne les remplace pas :
un bench qui obtiendrait 100 % ne rendrait pas S1–S5 « plus vraies », et un bench
qui échouerait mesurerait un écart entre l’agent et `T`, pas un défaut de la
preuve. Symétriquement, un score élevé dans un bras exposé ne dit rien du
mécanisme : toute revendication d’intégration dans les poids passe par
[`../weights/integration-reports/`](../weights/integration-reports/), jamais par ce répertoire.

## La thèse : une seule unité, l’essai

Un **essai** = un scénario × un bras d’exposition × une exécution. Cette unique
unité porte trois lectures :

| Lecture | Ce qu’on en tire |
|---|---|
| mesure | agréger les essais par bras donne le résultat A/B/C |
| démonstration | un essai vérifié devient un enregistrement SFT |
| contraste | deux essais du même scénario dans deux bras forment une paire de préférence |

Le découpage alternatif — un jeu de test, un jeu SFT, un jeu de préférences,
écrits séparément — a un défaut structurel : les démonstrations d’entraînement n’y
sont plus les réponses mesurées, mais des réponses **plausibles** rédigées après
coup. On entraîne alors sur une condition qui n’a jamais été observée, et on ne
peut plus dire d’où vient un exemple ni ce qui le rendait bon. Ici, chaque
enregistrement de corpus remonte à un essai, donc à un scénario, à un bras et à un
résultat de vérification machine. La provenance est la seule propriété qui
distingue ce corpus d’un jeu de démonstrations vraisemblables — et elle n’existe
que si la mesure et le corpus partagent la même unité.

Corollaire : les essais sont **append-only et immuables**. Une mesure qu’on peut
réécrire après coup n’est pas une mesure. Une correction se publie sous un nouvel
identifiant avec `supersedes` ; l’historique n’est jamais réécrit, pour que les
essais déjà mesurés restent interprétables.

## Les trois bras

Définis dans [`arms.yaml`](arms.yaml). Ils forment une **échelle d’exposition**,
pas trois qualités de réponse.

| Bras | Matière M3C3 dans le contexte | Ce qu’il mesure |
|---|---|---|
| `A_placebo` | aucune | la disposition de base du sujet |
| `B_adapter` | l’adaptateur de transport seul (`CLAUDE.md` / `AGENTS.md`) | ce qu’un résumé portable suffit à provoquer |
| `C_canonical` | adaptateur + `master.yaml` intégral | le plafond atteignable en contexte |

La comparaison qui **décide** est `C_vs_B`, pas `C_vs_A`. Si le canon complet ne
dépasse pas l’adaptateur portable de plus que `marginal_delta` sur la métrique
primaire, la valeur marginale du canon n’est pas établie et la distillation ne se
justifie pas par la capacité : la conclusion honnête devient « distribuer
l’adaptateur, ne pas distiller ». `C_vs_A` reste primaire et `B_vs_A` reste un
contrôle, mais aucun des deux ne tranche la question de l’effort de distillation.

Chaque essai enregistre le SHA-256 de la définition du bras qu’il a subie.
Modifier un bras ne réinterprète pas les essais passés : cela les **détache**, et
la comparaison redémarre sous un nouveau hash.

## Familles de scénarios

`regime_detection`, `ruin_gate`, `export_discipline`, `anchoring`, `layer_order`,
`cooperative_recomposition`, `contingency_binding`, `evidence_sufficiency`, plus
les quatre **familles de garde** : `activation_membrane`, `scope_permission`,
`weights_honesty`, `authority_channel`.

Les familles de garde mesurent le respect des limites dures, et elles sont
bilatérales :

- **sur-activer est un échec au même titre que ne pas activer.** Un scénario
  `membrane_expected: A0_dormant` est un piège : la bonne réponse est une réponse
  directe, sans protocole visible. Le déploiement du cadre sur une question
  triviale compte comme faute, et `over_activation_rate` est une métrique à
  minimiser — un gain sur la métrique primaire payé par une hausse ici est une
  régression, pas un progrès ;
- **un faux veto de ruine est un échec au même titre qu’un veto manquant.** Les
  scénarios de variance soutenable mesurent `false_veto_rate`, c’est-à-dire la
  *précision* du `ruin_gate` v0.6.1, pas sa sensibilité. Un sujet qui oppose un
  veto à tout est aussi inutilisable qu’un sujet qui n’en oppose jamais.

Les violations des familles de garde sont **bloquantes** : `honesty_violation_rate`
a un plafond de 0 dans le plan, et aucun score ailleurs ne les compense.

## Anti-contamination

Le même énoncé (`task.prompt`) est remis aux trois bras. Seule l’exposition varie ;
toute autre différence — formulation, outils, échantillonnage — casse la
comparaison et rend l’essai non interprétable.

Aucune **consigne d’application du protocole** n’est admise dans un énoncé. Une
phrase du type « applique M3C3 », « détecte le régime », « produis un export »,
« traverse les couches », `apply M3C3`, `use the framework`, `follow the protocol`
exposerait le bras `A_placebo` au cadre qu’il est précisément censé ne pas avoir :
le scénario ne mesurerait plus une disposition, il la dicterait. `validate.py`
refuse ces énoncés avec le code `prompt_contamination`. La détection est lexicale
et donc faillible dans les deux sens ; elle bloque les formes courantes, elle ne
remplace pas la relecture d’un scénario.

Trois contrôles complémentaires sont déclarés dans `arms.yaml` : un sujet ayant vu
un scénario ne le rejoue pas dans un autre bras au sein d’une même session ; un
essai `A_placebo` dont la réponse mentionne M3C3 est marqué et exclu (fuite par les
poids ou par l’historique) ; les contrôles jugés sont notés sans l’étiquette de
bras (`blinded_to_arm`).

## Porte de corpus et anti-fuite

Un essai n’alimente le corpus que si **tous** ses contrôles déterministes passent
et qu’**aucun** mode d’échec disqualifiant n’est déclenché. Un contrôle jugé non
exécuté n’empêche pas l’éligibilité mais reste reporté tel quel : `not_run` n’est
jamais promu en `pass`. Seuls les contrôles déterministes sont machine-vérifiables,
donc seuls eux constituent un signal d’entraînement ; le reste informe.

Le corpus est **dérivé, jamais écrit à la main** :
[`../corpus/build_corpus.py`](../corpus/build_corpus.py) le reconstruit depuis
`trials/`, et `--check` échoue si le corpus publié diverge. Une paire de préférence
n’est formée que si les **deux** essais existent réellement — aucun rejet n’est
synthétisé.

Anti-fuite train/eval : un scénario ayant servi à l’entraînement ne peut plus
servir à l’évaluation du modèle entraîné. La séparation est matérialisée par
`split` dans l’index des scénarios, prononcée **une seule fois**, avant le premier
essai destiné à l’entraînement, et immuable ensuite. Aujourd’hui
`split_status: not_assigned` : aucun essai n’existe, donc l’affectation n’est pas
encore prononcée. Sans elle, toute mesure post-distillation ne vaudrait rien.

## Organisation

- [`schema/scenario-v1.yaml`](schema/scenario-v1.yaml) — contrat d’un cas ;
- [`schema/trial-v1.yaml`](schema/trial-v1.yaml) — contrat d’un essai ;
- [`arms.yaml`](arms.yaml) — définition des bras et des comparaisons ;
- [`analysis-plan.yaml`](analysis-plan.yaml) — préenregistrement : métriques, seuils, porte de corpus ;
- `scenarios/`, `trials/` — artefacts append-only et leurs `index.yaml` déterministes ;
- `results/aggregate.yaml` — agrégat reconstruit, jamais rédigé ;
- `validate.py`, `build_index.py`, `score.py`, `aggregate.py` — outillage normatif.

Les schémas sont des contrats documentaires. `validate.py` est le validateur
normatif du dépôt : il ajoute les contrôles qui exigent le dépôt (résolution des
ancres `master_document.*` au commit courant, compilation effective des expressions
régulières, unicité des identifiants, cohérence arithmétique du scoring, accord
entre le bras déclaré et l’exposition réellement enregistrée, immuabilité contre
une référence).

## Commandes reproductibles

Depuis la racine du dépôt. Aucun réseau, aucun appel de modèle ; `--format json`
donne une sortie stable `{"checker", "ok", …, "errors": [{code, path, detail}]}`.

| Commande | Rôle |
|---|---|
| `python3 continuum/bench/validate.py` | valide scénarios et essais ; contrôle l’anti-contamination |
| `python3 continuum/bench/validate.py --base-ref v2.1.0` | exige que tout artefact déjà publié soit inchangé octet pour octet |
| `python3 continuum/bench/build_index.py --write` | écrit `scenarios/index.yaml` et `trials/index.yaml` |
| `python3 continuum/bench/build_index.py --check` | échoue si un index publié diverge des artefacts |
| `python3 continuum/bench/score.py --scenario <cas.yaml> --response <reponse.txt>` | applique les détecteurs déterministes et rend le score pondéré |
| `python3 continuum/bench/aggregate.py --check` | échoue si `results/aggregate.yaml` diverge des essais |
| `python3 continuum/corpus/build_corpus.py --check` | échoue si le corpus publié diverge des essais vérifiés |

`score.py` n’exécute que les contrôles déterministes. Les verdicts jugés se
passent explicitement (`--judged check_id=pass,autre=not_run`) et tout contrôle
non fourni reste `not_run`.

## État réel du dispositif

**Aucun essai n’a été exécuté à ce jour.** `analysis-plan.yaml` porte
`status: not_run`, `results/aggregate.yaml` porte `status: not_run`, `scenarios/`
et `trials/` sont vides, le corpus dérivé compte zéro enregistrement.

Ce que cela implique, sans atténuation :

- aucune conclusion sur la valeur de la distillation n’est autorisée aujourd’hui.
  `C_vs_B`, `C_vs_A` et `B_vs_A` valent `insufficient_data` ; la porte de
  conclusion force ce verdict tant que l’agrégat n’est pas `complete`, quel que
  soit le delta observé ;
- « non exécuté » n’est jamais synonyme de « réussi ». Zéro essai ne vaut jamais
  succès, et un contrôle non exécuté vaut `not_run`, jamais `pass` ;
- le plan est publié **avant** la première mesure, précisément pour que le seuil
  de réfutation (`marginal_delta: 0.10`) ne puisse pas être choisi après avoir vu
  les résultats. Ces seuils sont choisis par l’émetteur, au même titre que ρ et τ ;
  aucun n’est dérivé d’une valeur du master, et toute justification prétendant le
  contraire doit être retirée.

## Réserves

**Confondant de volume de contexte.** Les bras diffèrent aussi par la quantité de
texte injectée. Un gain observé en C peut provenir du cadre M3C3 ou du simple
volume de texte structuré. Un bras `D` à volume apparié — texte structuré de
longueur comparable, sans contenu M3C3 — serait nécessaire pour départager ; il
n’est **pas implémenté** (`mitigation_status: not_implemented`). Tant qu’il
n’existe pas, aucun résultat `C_vs_A` ne peut être attribué au contenu du cadre
plutôt qu’à sa masse.

**Biais des détecteurs.** Les détecteurs déterministes reconnaissent des *formes*
de réponse. Une réponse correcte formulée hors des formes prévues est comptée en
échec. C’est le prix de la reproductibilité, et il biaise la mesure en faveur des
sujets qui adoptent le style du dépôt.

**Statut canonique.** Le dispositif vit dans le continuum mais **n’est pas déclaré
dans `master_document.continuum_locations`**. Il n’est donc pas un emplacement
canonique du Continuum, et sa présence dans l’arborescence ne vaut pas
déclaration. L’y inscrire est une mutation du canon, qui exige une proposition
dans `weights/proposal/` et une activation explicite de l’émetteur — pas une
édition de ce README.
