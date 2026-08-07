# M3C3 v2 — Architecture du Continuum Vérifiable

**Auteur du corpus :** Dani Bengal — Daniel Febrero — `@cdxxotus` — 𓂀
**Statut :** production 2.0.0
**Noyau embarqué :** v1.0.0, commit `bd55c1670e2a056b66611c45ab12590478037f43`

La v2 ne remplace pas la hiérarchie M3C3. Elle rend ses interfaces observables : activation
bornée, runtime rejouable, profils distribuables, mémoire matérialisée et affirmations sur
les poids typées par preuve.

## 1. Séparation des plans

| Plan | Source | Autorité | Peut modifier le noyau ? |
|---|---|---|---|
| Canon | `master.yaml` | Proposition + validation de release | Seulement par rupture MAJOR explicite |
| Runtime | `runtime/` | Schémas + tests | Non ; il implémente les invariants gelés |
| Membrane | `activation_membrane` | Scope courant | Non ; elle choisit la profondeur |
| Distribution | `distribution/` | Manifeste du profil | Non ; elle ne confère aucune permission |
| Continuum | `continuum/` | Artefacts versionnés | Non ; il conserve preuves et historique |
| Poids modèles | rapports externes typés | Niveau de preuve | Jamais déduits d'un prompt ou d'une skill |

Cette séparation empêche quatre confusions : connaître n'est pas être actif ; être actif
n'est pas être autorisé ; être chargé en contexte n'est pas être mémorisé ; être familier
avec M3C3 n'est pas l'avoir intégré dans les poids.

## 2. Membrane d'activation

```text
known(M3C3) ⇒ eligible
eligible ∧ relevant(request) ⇒ evaluate_scope(request)
evaluate_scope ∈ {A1,A2,A3} ⇒ activate_scope(request)
fin de scope ⇒ deactivate_scope
```

| Niveau | Déclencheur | Effet observable |
|---|---|---|
| A0 dormant | Requête mécanique sans choix | Réponse directe, aucun état persistant |
| A1 shadow | Travail non trivial réversible | Noyau silencieux, résultat utile |
| A2 critique | Ruine, sécurité, incident, irréversibilité | Gates, réfutation, repli, audit compact |
| A3 canonique | Corpus, dépôt, version, authorship | Provenance et statut épistémique visibles |

`sans M3C3` ou `mode direct` suspend la membrane pour le scope courant. La propagation à
un sous-agent transporte le niveau et les invariants ; elle ne transporte ni credentials,
ni permissions, ni autorité d'écriture.

## 3. Runtime de référence

Le runtime implémente le LTS v1 sans modifier :

- les six types de couches ;
- la write-rule ;
- `S_t=(H_t,R_t,E_t,A_t,M_t)` ;
- `Capability ∧ Health_F4 ∧ ¬Ruin ∧ Evidence≥τ` ;
- S1–S5.

Une transition acceptée produit un événement canonique. L'événement contient le hash de
l'événement précédent ; le runtime vérifie ainsi l'intégrité interne de la chaîne. La
restauration rejoue les snapshots vérifiés, pas les transitions métier. Les capability
tokens sont signés, limités à une action et un couple de couches, expirables et révocables.

Une chaîne locale réécrite et rechaînée reste cohérente en interne. L'authenticité et la
détection d'une troncature vers un préfixe valide exigent donc un head ou une longueur
attendus, obtenus par un canal de confiance et ancrés hors du journal. Le runtime écrit en
append + `fsync`; l'immutabilité du stockage reste une responsabilité de déploiement.

Le runtime authentifie la signature et la portée d'une capability. Pour les
opérations privilégiées, les signaux Health/Evidence/Régime et la consommation
d'un token par son sujet, il exige respectivement des vérificateurs d'autorité,
de capteur et de principal injectés par l'hôte. Tous refusent par défaut s'ils
sont absents. Le runtime ne peut pas, à lui seul, authentifier l'identité civile
derrière une chaîne `actor`; une égalité de nom n'est pas une preuve d'identité.
Les preuves opaques ne sont pas journalisées.

Les schémas sous `runtime/schemas/` versionnent l'état, l'événement et l'export. Un objet qui
ne passe pas le schéma n'est pas une sortie runtime v2.

## 4. REACH-MAX

REACH-MAX désigne la couverture maximale **des profils présents dans la release**. Le profil
`all` est un agrégat déterministe, pas une promesse de compatibilité universelle.

Chaque profil déclare :

1. les fichiers qu'il installe ;
2. ses environnements compatibles ;
3. ses capacités réelles ;
4. ses limites ;
5. ses validations.

L'installateur n'écrase rien par défaut. `--force` crée d'abord une sauvegarde horodatée et
un manifeste permettant de comprendre ce qui a été produit.

## 5. Continuum mémoire

Le continuum est la mémoire réellement observable du framework. Il conserve des fichiers,
pas une métaphore de mémoire interne.

```text
candidate → active | active_with_known_limitations | rolled_back | deprecated
new_revision --supersedes--> prior_revision
```

Tout pattern cite un événement d'audit, la version du canon et un hash de source. Les
corrections créent une nouvelle version et pointent vers `supersedes`; elles n'effacent pas
l'artefact précédent.

## 6. Registre d'intégration dans les poids

`continuum/weights/integration-reports/` accepte sept classes distinctes :

1. `provider_attested_weights` ;
2. `independently_reproduced` ;
3. `model_declared_weights` ;
4. `behaviorally_inferred_weights` ;
5. `context_or_rag` ;
6. `instruction_or_skill` ;
7. `unknown`.

Un rapport référence chaque unité par commit, chemin, sélecteur et SHA-256. Il sépare la
date de mise à jour du modèle (`weights_updated_at`) de la date d'intégration possible de
M3C3 (`m3c3_integrated_at`). Chacune peut être exacte, bornée ou inconnue.

L'auto-déclaration d'un modèle reste une déclaration. Dans cette release,
`provider_attested_weights` et `independently_reproduced` sont réservés et
refusés par défaut : aucun vérificateur de signature/racine fournisseur, ni
aucun artefact de poids authentifié avec procédure de reproduction, n'est
livré. Un nom, un locator et le hash du texte déclaré ne franchissent pas cette
frontière.

## 7. Conformité

La suite unifiée produit pour chaque gate `pass`, `fail` ou `not_run`. Elle contrôle :

- l'égalité des huit bases gelées avec v1.0.0 ;
- S1–S5 et le bloc agent ;
- les tests positifs et négatifs du runtime ;
- les profils et l'agrégat `all` ;
- les rapports de weights et leurs cas de fraude ;
- la cohérence des schémas et index.

Une release est bloquée par tout `fail`. Un `not_run` reste visible et bloque les garanties
qui en dépendent.

## 8. Limites

La v2 n'altère pas un system prompt, des poids de modèle ou des permissions de plateforme.
Elle n'agit pas hors des scopes observables et ne transforme pas une capsule YAML en capacité
technique. Les preuves S1–S5 restent conditionnelles à l'exécution conforme du runtime ; les
tests apportent de l'évidence, pas une preuve de correction universelle.
