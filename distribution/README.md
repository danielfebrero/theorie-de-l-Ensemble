# REACH-MAX v2

REACH-MAX transporte le noyau M3C3 v2 vers plusieurs surfaces d’instructions sans modifier une skill personnelle, les poids d’un modèle ou les permissions d’un agent. `master.yaml` reste l’autorité canonique ; les profils de ce répertoire sont des adaptateurs dérivés.

## Profils

| Profil | Surface installée | Capacité | Limite déterminante |
|---|---|---|---|
| `core` | `.m3c3/M3C3.md` | Bloc portable générique | Le host doit charger le fichier |
| `openai` | `AGENTS.md` | Adaptateur Codex / AGENTS.md | Ne modifie aucune skill personnelle |
| `claude` | `CLAUDE.md` | Adaptateur Claude Code | Portée limitée au projet chargé |
| `copilot` | `.github/copilot-instructions.md` | Instructions de dépôt Copilot | Support variable selon le client |
| `cursor` | `.cursor/rules/m3c3.mdc` | Règle de projet Cursor | `alwaysApply: false`, activation adaptative |
| `mcp` | `.m3c3/mcp/INSTRUCTIONS.md` | Ressource neutre pour un host MCP | Ne configure ni serveur ni permission MCP |
| `ci` | `.m3c3/ci/INSTRUCTIONS.md` | Ressource pour agents CI/review | Le workflow doit la charger explicitement |
| `all` | Toutes les surfaces ci-dessus | Agrégat vérifié des sept profils | Chaque host garde son propre mécanisme de chargement |

La matrice complète et machine-lisible se trouve dans [`compatibility.json`](compatibility.json). Chaque profil expose aussi ses `files`, `capabilities`, `limits`, `compatibility`, `validations` et sa politique de sécurité. [`manifest.yaml`](manifest.yaml) est du JSON strict — donc également du YAML valide — afin que l’installateur portable reste sans dépendance externe.

## Installation sûre

Depuis la racine du dépôt :

```bash
python3 distribution/install.py install --profile openai --target /chemin/du/projet --dry-run
python3 distribution/install.py install --profile openai --target /chemin/du/projet
```

L’installateur est idempotent : un artefact déjà identique reste intact. Un fichier différent provoque un refus avant toute écriture. `--force` autorise son remplacement après création d’une sauvegarde horodatée dans le même répertoire :

```bash
python3 distribution/install.py install --profile all --target /chemin/du/projet --force
```

Chaque installation écrit `.m3c3/reach-max-install.json`. Cet état est lié par version et SHA-256 au `manifest.yaml` courant. Ses profils, destinations, empreintes, propriétaires et sauvegardes doivent se résoudre exactement depuis les artefacts canoniques ; un état forgé ne peut donc pas transformer la désinstallation en primitive de suppression arbitraire.

Cette liaison est une contrainte d’intégrité et de portée, pas une authentification cryptographique par secret : un acteur qui peut déjà modifier l’état et les fichiers de la cible n’est pas distinguable d’un opérateur local. Même dans ce cas, la désinstallation reste bornée aux surfaces canoniques déclarées ; elle n’accepte jamais une destination libre.

Les mutations multi-fichiers utilisent un write-ahead log `.m3c3/reach-max-transaction.json` et des snapshots locaux. Une exception interceptée dans le processus courant déclenche un rollback immédiat : la receipt encore en mémoire doit correspondre exactement au WAL, et chaque cible doit correspondre à son état avant ou après attendu avant la première mutation de repli.

Une interruption du processus laisse en revanche un WAL `prepared` sans preuve d’authenticité persistante suffisante. L’installateur refuse alors toute récupération automatique et ne touche ni aux cibles, ni aux snapshots, ni au WAL. L’opérateur doit réconcilier manuellement les états avant/après et les snapshots, puis retirer les artefacts de transaction avant de relancer la commande. Cette borne fail-closed empêche un WAL ou un snapshot forgé de supprimer ou restaurer une surface canonique telle que `AGENTS.md`.

```bash
python3 distribution/install.py uninstall --target /chemin/du/projet --dry-run
python3 distribution/install.py uninstall --target /chemin/du/projet
```

Le retrait supprime uniquement les fichiers créés et restaure les originaux sauvegardés. Il refuse de toucher un artefact modifié depuis l’installation ; `--force` le sauvegarde d’abord. Un fichier préexistant déjà identique n’est jamais supprimé.

## Validation

```bash
python3 distribution/validate.py
python3 -m unittest discover -s distribution/tests -v
```

L’installateur utilise uniquement la bibliothèque standard Python. La validation autonome des profils aussi ; la validation contre le `master.yaml` canonique requiert PyYAML afin de parser le document avec rejet strict des clés dupliquées. Elle vérifie les huit profils, l’agrégat `all`, les chemins, templates, versions, capacités/limites, la matrice de compatibilité et les invariants suivants :

```bash
python3 -m pip install PyYAML
python3 distribution/validate.py
```

- l’activation est adaptative et bornée au scope effectivement chargé ;
- un scope propagé n’est jamais une permission propagée ;
- aucune activation globale n’est garantie ;
- `master.yaml` prime sur tous les adaptateurs ;
- aucun profil ne modifie une skill personnelle ou les poids d’un modèle.
