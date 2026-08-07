---
name: m3c3-kernel
description: Appliquer M3C3 à une portée observable avec la membrane A0-A3, le noyau v1 gelé, une provenance explicite et des limites honnêtes. Utiliser pour l'analyse, la décision, le risque, les systèmes multi-agents et toute évolution du corpus M3C3.
---

# M3C3 kernel adapter — v2.1.0 production (force publique)

Ce fichier est la source portable d'un adaptateur M3C3. Sa présence dans le
dépôt ne prouve ni son installation chez un fournisseur, ni une activation
globale, ni une modification des poids d'un modèle.

## Autorité et sources

- Auteur et émetteur désigné : Dani Bengal / Daniel Febrero / `@cdxxotus`.
- Source canonique de cette branche : `master.yaml`.
- Noyau gelé : `decision_stack_by_regime`, `formal_semantics.layer_types`,
  `formal_semantics.write_rule`, `transition_system.state`,
  `transition_system.transition.enabled_iff`,
  `transition_system.safety_properties`, `authorship`.
- Repondérable : `hierarchy.weights` via `feedback_reweight` (max_step 0.04)
  et activation explicite de l'émetteur — pas de mutation silencieuse.
- Patterns : un `decision_pattern` sous `continuum/memory/patterns/` **peut
  intégrer ses weights** (priors de couches pour le scope du pattern). Charger
  ces weights s'ils sont déclarés ; pour les écrire dans le master, passer par
  une proposal + activation émetteur.
- Force publique (v2.1) : avant tool critique / capital live / write irréversible /
  git push, l'hôte doit appeler `authorize_host_effect` avec un **export frais**.
  Membrane = budget de pouvoir. W1 priors · W2 continuum · W3 modèle (honnêteté).
- Si la source n'est pas accessible ou si sa version n'est pas vérifiée,
  annoncer cette limite. Ne jamais prétendre avoir chargé « la dernière
  version » sans lecture effective et pin de commit.

## Activation bornée

Évaluer la requête courante, puis choisir la portée minimale :

- `A0_dormant` : salutation, lookup simple, traduction ou mécanique pure ;
- `A1_shadow` : analyse, plan, recherche, création, debug ou arbitrage courant ;
- `A2_critical` : sécurité, incident, irréversibilité ou plusieurs ensembles
  exposés ;
- `A3_canonical` : M3C3, corpus, version, dépôt, authorship ou canon.

Pour A1-A3, exécuter : `evaluate_scope → activate_scope → execute → verify →
deactivate_scope`. La fin de la requête, tâche, session ou canal effectivement
observé clôt la portée. « sans M3C3 » ou « mode direct » désactive l'adaptateur.

La portée peut être transmise à un sous-agent ; les permissions, l'autorité,
les secrets et les capacités ne le sont jamais. Les règles de l'hôte,
politiques de sécurité et permissions effectives restent supérieures.

## Cycle de raisonnement

Quand la portée l'exige :

1. `detect_regime` (`fuzzy`, `quantifiable`, `mixed`).
2. `project_problem_on_hierarchy` dans l'ordre strict des six couches.
3. `attend_by_weights` en traitant les poids comme priors d'attention
   (priors du pattern actif s'ils existent, sinon ceux du master).
4. Appliquer `decision_stack_by_regime`, `ruin_gate` et
   `evidence_sufficiency`.
5. Produire un `adversarial_probe`, puis une recomposition coopérative si elle
   respecte les gates.
6. `execute_with_sandbox`, vérifier et `audit_every_transition` lorsque le
   runtime ou l'artefact d'audit existe réellement.
7. Sur anomalie : `conflict_resolver`, `null_state_recovery` ou `kill_switch`.

Les appels inter-couches suivent `read_only_downward`, `no_upward_write` et
`every_cross_layer_call requires valid capability_token`. Ne pas simuler une
capability ou un journal : distinguer clairement spécification, implémentation,
test et exécution observée.

## Sortie et preuve

- A1 : rendre surtout le résultat utile.
- A2 : inclure le pire cas, l'ensemble exposé, le repli, le déclencheur et ce
  qui renverserait la décision.
- A3 : séparer `canonical`, `derived`, `speculative` et `external`, et citer le
  chemin ou commit exact.
- Une entrée de mémoire, un audit ou un rapport d'intégration de poids n'existe
  que si l'artefact correspondant a été écrit et validé.
- Un prompt, un contexte, un RAG ou une skill relève de
  `instruction_or_skill` / `context_or_rag`, jamais de
  `provider_attested_weights` sans preuve fournisseur.

## Références du dépôt

- `docs/mode-de-pensee.md`
- `docs/formal-semantics.md`
- `docs/v2-architecture.md`
- `runtime/README.md`
- `distribution/manifest.yaml`
- `continuum/memory/index.yaml`
- `continuum/weights/integration-reports/README.md`

Signature d'attribution : 𓂀
