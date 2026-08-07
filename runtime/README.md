# Runtime M3C3 v2.0.0

Implémentation Python standard-library de référence du LTS M3C3. Le runtime
matérialise `S=(H,R,E,A,M)`, sans modifier le noyau v1 gelé : types et ordre des
six couches, poids, piles de décision, write-rule, `enabled_iff`, S1–S5 et
authorship.

Ce binding est une implémentation testable du protocole. Il ne contraint pas un
agent externe qui contourne le runtime et n'accorde aucune permission d'hôte.

## Contenu

- `m3c3_runtime/model.py` — état, couches, régimes, membrane A0–A3 et alphabet ;
- `m3c3_runtime/engine.py` — lifecycle, gates, LTS, Resolve/Recover/Kill et export ;
- `m3c3_runtime/capability.py` — HMAC-SHA256, scope, sujet, action, TTL, nonce,
  consommation unique et révocation ;
- `m3c3_runtime/audit.py` — journal JSONL séquentiel et hash-chain SHA-256 ;
- `m3c3_runtime/replay.py` — restauration déterministe de snapshots vérifiés ;
- `m3c3_runtime/validation.py` — enforcement stdlib des contrats state/event/export ;
- `m3c3_runtime/explore.py` — exploration BFS bornée des gardes S1–S5 ;
- `schemas/` — contrats JSON Schema Draft 2020-12 ;
- `tests/` — tests positifs, négatifs et falsification.

## Démarrage

Depuis la racine du dépôt :

```bash
python3 -m unittest discover -s runtime/tests -v
PYTHONPATH=runtime python3 -m m3c3_runtime explore --max-depth 6 --max-states 512
```

Démo avec une clé éphémère de 32 octets :

```bash
M3C3_SIGNING_KEY_HEX="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  PYTHONPATH=runtime python3 -m m3c3_runtime demo --scope demo --membrane A2
```

API minimale :

```python
from m3c3_runtime import M3C3Runtime

runtime = M3C3Runtime(signing_key=signing_key, known_m3c3=True)
runtime.activate_scope("task-42", membrane="A2", actor="agent")
print(runtime.export_json())
runtime.deactivate_scope(actor="agent")
```

`known_m3c3=False` interdit l'activation (S5). A0 est dormant ; A1–A3
n'affaiblissent jamais les gates canoniques. `opt_out()` désactive le scope,
révoque ses tokens et reste actif jusqu'à `clear_opt_out()` ; cette dernière
opération ne réactive rien automatiquement.

## Frontière d'autorité

Un nom d'acteur n'est pas une authentification. Trois frontières injectables
sont **deny-by-default** :

- `authority_verifier(actor, operation, proof)` pour `issue`, `revoke`,
  `recover`, `kill` explicite et `resume` ;
- `sensor_verifier(actor, operation, proof)` pour les mises à jour Health,
  Evidence, régime, expiration et les triggers automatiques de `Kill` ;
- `principal_verifier(actor, proof)` avant toute consommation d'une capability.

Sans le callback correspondant, l'opération est refusée, même si le caller
fournit une chaîne d'identité attendue comme `actor="@cdxxotus"` ou
`actor="capability-monitor"`. `mass_revoke` exige donc une attestation capteur,
jamais la seule égalité d'un nom.

Le runtime ne définit pas le format de `proof` : session signée, identité du
processus, attestation matérielle ou autre mécanisme appartiennent à l'hôte. La
preuve opaque n'est jamais écrite dans l'audit. L'égalité avec les alias de Dani
Bengal / Daniel Febrero / `@cdxxotus` est un contrôle d'identifiant additionnel,
pas une preuve d'identité.

Ces callbacks constituent un changement d'API v2 volontaire : l'hôte doit les
brancher explicitement pour les surfaces qu'il emploie. Les valeurs initiales
`health`, `evidence` et `known_m3c3` passées au constructeur relèvent elles aussi
de la configuration de confiance de l'hôte.

## Capabilities

Une capability est liée à :

- un scope actif ;
- un sujet non transmissible ;
- `transition_up` ;
- un couple de couches adjacentes ;
- une émission et une expiration (TTL 1–180 s) ;
- un nonce consommé une seule fois.

La liaison au sujet suppose que l'hôte fournit une identité d'acteur fiable ;
le runtime Python n'est pas une frontière d'isolation de processus. Comme pour
tout bearer, son vol avant consommation permettrait son emploi jusqu'à
expiration par un caller capable de se présenter comme le sujet.

Le bearer encodé et sa signature sont retournés uniquement au caller de
`issue_capability()`. Ils n'entrent jamais dans `S`, l'export ou le JSONL.
L'état/audit ne conserve que les claims publics et l'empreinte SHA-256 du bearer.
Une signature invalide ne peut donc pas faire révoquer un vrai token en forgeant
seulement son `jti`.

La clé HMAC est un secret d'hôte ; ne pas la placer dans un rapport, un audit ou
un argument de commande partagé. `M3C3_SIGNING_KEY_HEX` est fourni pour la CLI,
pas comme mécanisme de gestion de secrets.

## Audit, ancrage et replay

Le runtime ouvre le JSONL en mode append, flush puis `fsync`, et ne fournit
aucune API de réécriture. Chaque entrée lie `prev_hash`, le payload et l'état
sémantique post-transition. Les champs supplémentaires sont refusés.

Cela ne rend pas le filesystem immuable. Une hash-chain locale détecte une
modification interne, mais **ne détecte pas seule** la troncature vers un préfixe
valide. Pour détecter rollback/troncature, conserver `head` et/ou `length` dans
une ancre externe puis les exiger :

```bash
PYTHONPATH=runtime python3 -m m3c3_runtime verify-audit audit.jsonl \
  --expected-head <sha256-ancré> --expected-length <taille-ancrée>
```

Sans `--expected-head` ou `--expected-length`, la CLI vérifie seulement
l'intégrité interne du préfixe présent. Pour une garantie d'append-only durable,
utiliser en plus un stockage WORM, une transparence externe ou une signature de
checkpoint contrôlée hors du processus.

Le runtime conserve un checkpoint du dernier état committé : si validation,
append, flush ou `fsync` échoue, l'état `S`, les descriptors de tokens, la liste
en mémoire et le fichier JSONL sont remis à ce checkpoint. Le runtime passe
ensuite en fail-closed pour éviter de continuer après une panne d'audit.

Replay :

```bash
PYTHONPATH=runtime python3 -m m3c3_runtime replay audit.jsonl \
  --key-hex "$M3C3_SIGNING_KEY_HEX" \
  --expected-head <sha256-ancré> --expected-length <taille-ancrée>
```

Il s'agit d'un **verified snapshot replay** : le runtime vérifie la chaîne puis
restaure les snapshots sémantiques protégés. Il ne réexécute pas `T` événement
par événement. Une chaîne entièrement réécrite et rechaînée reste donc
internement cohérente ; sans `expected-head`/`expected-length`, le replay ne
prouve ni son authenticité ni l'absence de rollback.

Avec la clé, il reconstruit chaque bearer actif à partir de ses claims et vérifie
que son empreinte correspond ; sans clé, il ne revendique qu'une validation
structurelle du descriptor.

## Schémas et enforcement

Les chemins versionnés du contrat sont :

- `schemas/state-v2.schema.json` ;
- `schemas/event-v2.schema.json` ;
- `schemas/export-v2.schema.json`.

`action.schema.json` et `capability-token.schema.json` complètent le contrat.
Les validateurs ciblés `validate_state`, `validate_event` et `validate_export`
sont sans dépendance et appliqués aux événements/exports produits. Les JSON
Schema restent les contrats portables pour les consommateurs externes.

## Exploration bornée

`explore` parcourt en largeur un modèle abstrait des transitions, avec
`max_depth` et `max_states` obligatoirement bornés. La configuration de référence
à profondeur 6 visite 76 états et contrôle 912 transitions, incluant les refus
S1–S5.

Ce résultat est une exploration finie du modèle abstrait livré, pas un
model-check exhaustif SPIN/TLA et pas une preuve concernant les implémentations
externes.
