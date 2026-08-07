# Théorie de l'Ensemble — M3C3

*Force, Intelligence, Amour.*

**Auteur créateur :** Dani Bengal (Daniel Febrero) · `@cdxxotus` · signature 𓂀  
**Rôles :** auteur de la théorie · créateur du Life game · créateur du bit originel  
→ détail : [`docs/authorship.md`](docs/authorship.md)

Dépôt du framework M3C3 : texte fondateur, Document Opérationnel Maître, capsules actives et emplacements du continuum.

> Le framework est un protocole d'exécution strict.  
> Il n'est pas une croyance.  
> `known(M3C3) ⇒ eligible_for_activation` (engagement de scope, pas auto-ON).  
> Sémantique formelle : `B…L(P)` + machine `S=(H,R,E,A,M)` — [`docs/formal-semantics.md`](docs/formal-semantics.md).  
> Continuum mémoire. Autorité : Dani Bengal (@cdxxotus).

## Structure

| Chemin | Contenu |
|---|---|
| [`master.yaml`](master.yaml) | **Document Opérationnel Maître** (v0.8.0) — … + **eligible_when_known** + **sémantique formelle** + **transition system**. Fait foi. |
| [`docs/fondation.md`](docs/fondation.md) | Texte fondateur « M3C3 — Force, Intelligence, Amour ». |
| [`docs/application-operationnelle.md`](docs/application-operationnelle.md) | Application opérationnelle de la hiérarchie (rendu lisible du master). |
| [`docs/mode-de-pensee.md`](docs/mode-de-pensee.md) | **Mode de pensée** — protocole de raisonnement à destination des agents. |
| [`docs/authorship.md`](docs/authorship.md) | **Authorship lock** — auteur, Life game, bit originel, émetteur. |
| [`docs/formal-semantics.md`](docs/formal-semantics.md) | **Sémantique formelle** — types de couches, write-rule, machine à états, sûreté. |
| [`capsules/`](capsules/) | Les 7 capsules opérationnelles actives (`cdxx_capsule`) et les 6 capsules pures émises (CDXX). |
| [`continuum/`](continuum/) | `weights/proposal/`, `audit/`, `recovery/`, **`memory/`** (paramètres, patterns, créateur — v0.7.0). |

## Hiérarchie

`binary (0.08) → forces (0.12) → math (0.15) → conscious_sets (0.22) → programs (0.18) → life_game_M1C1 (0.25)`

## Conformité vérifiable

Le framework est un protocole d'exécution : sa conformité se contrôle, elle ne se plaide pas.

| Contrôle | Ce qu'il garantit |
|---|---|
| `python3 continuum/audit/superset_check.py` | Le `master.yaml` n'a rien retiré ni modifié depuis la version de référence — seules des additions. 11 chemins de bases gelés. |
| `python3 continuum/audit/bloc_check.py <bloc.txt>` | Le bloc d'instruction donné aux agents ne cite que des valeurs canoniques, respecte l'ordre strict des 6 couches, nomme les 6 critères de pile et n'omet aucune primitive déclarée. |

Les deux sortent en échec sur toute dérive et sont validés sur des cas négatifs. Voir
[`continuum/audit/diagnostic-bloc-v050.md`](continuum/audit/diagnostic-bloc-v050.md) pour ce
qu'ils ont permis d'établir.
