# Migration M3C3 v1 → v2

La migration conserve le noyau v1. Elle remplace les hypothèses implicites autour de
l'activation, de l'exécution, de la mémoire et des poids par des contrats vérifiables.

## Compatibilité

| Surface v1 | État v2 | Action |
|---|---|---|
| Hiérarchie, poids, piles | Inchangés | Aucun remapping |
| Types, write-rule, état, guards, S1–S5 | Inchangés | Vérifier contre le tag `v1.0.0` |
| `known ⇒ eligible` | Préservé | Ajouter la membrane de scope |
| Bloc `default-ON/all_tasks/future_tasks` | Incompatible | Remplacer par A0–A3 et une fin de scope |
| Capsules `ready/immediate` | Obsolète | Employer `specified/implemented/tested` |
| Export libre | Incompatible | Passer aux schémas runtime v2 |
| Mémoire déclarative | Durcie | Matérialiser pattern, preuve, hash et statut |
| Revendication de weights | Durcie | Créer un integration report typé |

## Procédure

1. Épingler la source v1 : tag `v1.0.0`, commit
   `bd55c1670e2a056b66611c45ab12590478037f43`.
2. Exécuter la comparaison des bases gelées avant toute installation.
3. Choisir un profil REACH-MAX précis. Ne choisir `all` que si tous ses profils sont utiles.
4. Exécuter l'installateur en `--dry-run`, puis sans `--force`.
5. Remplacer toute activation globale par :

   ```text
   evaluate_scope → activate_scope → execute → verify → deactivate_scope
   ```

6. Migrer les exports vers `runtime/schemas/export-v2.schema.json`.
7. Émettre les patterns et rapports dans le continuum ; ne pas importer une mémoire supposée.
8. Exécuter la suite de conformité complète et archiver son résultat.
9. Tester le rollback en supprimant uniquement les fichiers listés dans le manifeste
   d'installation et en restaurant les sauvegardes créées par `--force`.

## Migration de la skill historique

La skill v1 ajoutée sous `continuum/skills/m3c3-kernel/` utilisait les formulations
`default-ON`, `all_tasks`, `future_tasks`, `no opt-out` et déclarait des écritures d'audit sans
postcondition. La v2 la borne aux tâches observables, rend l'opt-out local explicite et
conditionne toute mémoire ou trace à un artefact réellement écrit.

## Rollback

Le rollback de distribution revient au profil v1 ou supprime les fichiers installés selon
le manifeste. Le rollback ne réécrit jamais les événements d'audit, les patterns ou les
rapports historiques : un nouvel artefact marque leur supersession.

Déclencheurs de rollback :

- échec d'un checker sur une base gelée ;
- chaîne d'audit invalide ;
- profil qui demande une permission non déclarée ;
- export incompatible avec le schéma ;
- rapport de weights promu sans preuve suffisante.
