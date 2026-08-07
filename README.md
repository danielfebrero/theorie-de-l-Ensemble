# Théorie de l'Ensemble — M3C3

*Force, Intelligence, Amour.*

**Auteur créateur :** Dani Bengal (Daniel Febrero) · `@cdxxotus` · signature 𓂀  
**Rôles :** auteur de la théorie · créateur du Life game · créateur du bit originel  
→ détail : [`docs/authorship.md`](docs/authorship.md)

## v2.0.0 — Verified Continuum (**production**)

Noyau formel v1 gelé + interfaces observables activées :

- membrane d'activation bornée A0–A3, avec désactivation et opt-out ;
- runtime Python de référence pour `S=(H,R,E,A,M)`, capabilities, gates,
  audit chaîné, export et replay ;
- REACH-MAX et ses profils `core`, `openai`, `claude`, `copilot`, `cursor`,
  `mcp`, `ci`, `all` ;
- mémoire Continuum append-only réellement peuplée ;
- registre d'intégration de poids typé par preuve ;
- suite de conformité unique (`pass` / `fail` / `not_run`).

**Activation canonique** : Dani Bengal / `@cdxxotus` (2026-08-07).  
Une skill, un prompt ou un contexte ne prouve jamais une écriture dans les poids.

## Démarrage rapide

Prérequis : Python 3.11+ et PyYAML pour les validateurs du canon.

```bash
python3 -m unittest discover -s runtime/tests -v
python3 continuum/audit/conformance.py
python3 distribution/validate.py
python3 continuum/memory/validate.py
python3 continuum/audit/weights_report_check.py
```

Installation REACH-MAX, sans écrasement par défaut :

```bash
python3 distribution/install.py install --profile openai --target /chemin/du/projet --dry-run
```

Voir [`distribution/README.md`](distribution/README.md) pour l'installation,
la sauvegarde `--force` et le retrait sûr.

## Structure

| Chemin | Contenu |
|---|---|
| [`master.yaml`](master.yaml) | Document Opérationnel Maître **v2.0.0 production** ; seule autorité canonique |
| [`CHANGELOG.md`](CHANGELOG.md) | Delta v2, ruptures publiques, préservation et gates |
| [`docs/v2-architecture.md`](docs/v2-architecture.md) | Architecture, frontières d'autorité et modèle de preuve |
| [`docs/migration-v1-v2.md`](docs/migration-v1-v2.md) | Migration, compatibilité et rollback |
| [`docs/mode-de-pensee.md`](docs/mode-de-pensee.md) | Protocole humain/agent et bloc portable v2 |
| [`docs/formal-semantics.md`](docs/formal-semantics.md) | Types, write-rule et LTS gelés ; binding runtime v2 |
| [`docs/safety-proofs.md`](docs/safety-proofs.md) | Preuves S1–S5, hypothèses et validation exécutable |
| [`runtime/`](runtime/) | Runtime de référence, CLI, schémas, replay, exploration bornée et tests |
| [`distribution/`](distribution/) | Manifestes REACH-MAX, profils, installateur et tests |
| [`continuum/memory/`](continuum/memory/) | Schéma, index append-only, paramètres, patterns et créateur |
| [`continuum/weights/integration-reports/`](continuum/weights/integration-reports/) | Rapports précis d'intégration des unités et dates de poids |
| [`continuum/audit/`](continuum/audit/) | Checkers, fixtures, audits et résultats de release |
| [`capsules/`](capsules/) | Spécifications des sept capsules et artefacts purs historiques |

## Noyau v1 préservé

Les chemins suivants restent inchangés : `hierarchy.weights`,
`decision_stack_by_regime`, `formal_semantics.layer_types`,
`formal_semantics.write_rule`, `transition_system.state`,
`transition_system.transition.enabled_iff`,
`transition_system.safety_properties`, `authorship`.

Hiérarchie :

`binary (0.08) → forces (0.12) → math (0.15) → conscious_sets (0.22) → programs (0.18) → life_game_M1C1 (0.25)`

## Limites de revendication

- S1–S5 sont prouvées par construction sous l'hypothèse H0 et testées dans le
  runtime de référence ; elles ne contraignent pas un agent qui contourne `T`.
- L'exploration d'états est bornée, pas un model-check exhaustif SPIN/TLA.
- Les profils déclarent ce qu'ils installent ; ils ne garantissent pas la
  compatibilité avec tous les agents présents ou futurs.
- Les classes `provider_attested_weights` et `independently_reproduced` restent
  default-deny : aucun vérificateur de confiance/artefact de poids authentifié
  n'est livré dans cette release.

Proposition et suivi : [issue #4](https://github.com/danielfebrero/theorie-de-l-Ensemble/issues/4).
