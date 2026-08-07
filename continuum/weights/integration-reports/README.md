# Registre des rapports d’intégration M3C3

Ce registre consigne ce qui est **attesté**, **déclaré**, **inféré** ou simplement
fourni au contexte d’un agent à propos de M3C3. Il ne transforme jamais une
familiarité, une réponse correcte, une instruction, une skill ou un accès RAG en
preuve d’écriture dans les poids.

## Classes de provenance

| Classification | Ce qu’elle autorise à conclure |
|---|---|
| `provider_attested_weights` | Classe réservée : refusée en v2.0 tant qu’aucune racine de confiance/signature fournisseur vérifiable n’est configurée. |
| `independently_reproduced` | Classe réservée : refusée en v2.0 sans artefact de poids authentifié et procédure de reproduction vérifiable. |
| `model_declared_weights` | Le modèle l’affirme lui-même ; ce n’est pas une attestation fournisseur. |
| `behaviorally_inferred_weights` | Des tests comportementaux sont compatibles avec l’hypothèse, sans identifier le mécanisme. |
| `context_or_rag` | Le contenu a été injecté dans le contexte ou récupéré au moment de l’inférence. |
| `instruction_or_skill` | Le contenu vient d’une instruction, d’une skill ou d’un artefact équivalent. |
| `unknown` | Le mécanisme et/ou la provenance ne sont pas établis. |

Un rapport `provider_attested_weights` est **toujours refusé en v2.0** avec
`provider_attestation_unverifiable`. Un champ YAML `issuer.kind: provider`, un
nom, une URL et le hash d’une déclaration restent auto-déclarés et forgeables.
Ils ne deviennent probants qu’après vérification contre une racine de confiance
ou une signature fournisseur configurée — mécanisme absent de cette release.

`independently_reproduced` est également refusé par défaut avec
`independent_reproduction_unverifiable`. Un nom d'auditeur, un URN et le hash
de sa propre déclaration ne prouvent ni l'identité de l'auditeur, ni l'artefact
de poids, ni l'exécution d'une reproduction.

Les classes restantes sont des rapports typés sur leur provenance déclarée. Leur
validation structurelle n’authentifie pas l’identité de l’émetteur.

## Organisation

- `schema-v1.yaml` : contrat déclaratif du format ;
- `reports/` : rapports probants ou non probants réels, append-only ;
- `examples/` : exemples explicitement fictifs/non probants, exclus de l’index ;
- `index.yaml` : index déterministe des seuls rapports réels ;
- `validate.py` : validation sémantique stricte, sélecteurs et hashes inclus ;
- `build_index.py` : construction ou vérification de l’index.

Chaque unité du framework porte le quadruplet exact
`framework_commit + path + selector + content_sha256`. Le sélecteur YAML est
résolu dans `path` au commit complet indiqué. `content_sha256` est le SHA-256 de
la valeur sélectionnée sérialisée en JSON canonique (`UTF-8`, clés triées,
séparateurs compacts, Unicode non échappé).

Les dates utilisent une précision explicite :

- `exact` avec `value` (instant RFC 3339) ;
- `day`, `month`, `quarter` ou `year` avec une valeur de granularité correspondante ;
- `range` avec `start`, `end` et `basis` (`month`, `quarter`, fenêtre fournisseur ou estimation) ;
- `unknown` avec une raison, sans date inventée.

## Validation reproductible

Depuis la racine du dépôt :

```bash
python3 continuum/weights/integration-reports/validate.py --include-examples
python3 continuum/weights/integration-reports/build_index.py --check
python3 continuum/weights/integration-reports/validate.py --base-ref v1.0.0
```

Avec `--base-ref`, tout rapport déjà présent dans la référence doit encore être
présent octet pour octet. Une correction se publie dans un nouveau rapport avec
`supersedes`; l’historique n’est jamais réécrit.

## Couverture des exemples

Les fichiers de `examples/` sont tous `example_non_evidence`. Ensemble, ils
montrent une portée exacte par `path + selector + content_sha256`, une
intégration partielle et des dates `exact`, `range` et `unknown`, sans jamais
prétendre décrire un modèle réel. Ils restent exclus de `index.yaml`.
