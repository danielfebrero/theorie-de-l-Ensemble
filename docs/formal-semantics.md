# M3C3 — Sémantique formelle (noyau v1, binding runtime v2)

> Rendu lisible de `master.yaml` → `formal_semantics` + `transition_system`. Ces chemins sont gelés depuis v1.0.0 ; v2 ajoute un binding exécutable sans les réécrire.
> Preuves de sûreté : [`safety-proofs.md`](safety-proofs.md).  
> Checker : `perl continuum/audit/safety_check.pl`

## 1. Types de couches

Chaîne :

```text
B → F(B) → M(F) → C(M) → P(C) → L(P)
```

| Couche | Symbole | Type | Sens |
|---|---|---|---|
| `binary` | B | `B` | états élémentaires / 0–1 |
| `forces` | F | `F(B)` | attractions–répulsions sur B |
| `math` | M | `M(F)` | invariants / structure sur F |
| `conscious_sets` | C | `C(M)` | ensembles qui se perçoivent |
| `programs` | P | `P(C)` | procédures exécutables |
| `life_game_M1C1` | L | `L(P)` | conséquences vécues |

Indices : B=1 … L=6. Ordre strict.

## 2. Morphismes

| Morphisme | Type | Rôle |
|---|---|---|
| `project_i` | `Problem → Layer_i` | projection du problème sur la couche i |
| `transition_i` | `Layer_i × Context → Layer_(i+1)` | montée d’une marche (sandbox + capability) |
| `read_down_i` | `Layer_i → Layer_(i-1)` | lecture seule vers le bas (i>1) — **toujours autorisée** |

## 3. Règle d’écriture

```text
write(i → j) allowed  ⇔
    Health_F4(S)
  ∧ ( i = j
    ∨ ( j = i+1 ∧ Cap(i → j) )
    ∨ ( j < i ∧ RecoveryPath ) )
  ∧ ¬ ( j < i ∧ ¬RecoveryPath )
```

- **i = j** : écriture locale (sandbox de couche).
- **j = i+1** : transition avant, **capability_token** obligatoire.
- **j < i** : interdit sauf `null_state_recovery` / `progressive_rebuild` (pas de réécriture haute → basse).

C’est la forme mathématique de `no_upward_write` + `capability_token` + `read_only_downward`.

## 4. Machine à états

```text
S_t = (H_t, R_t, E_t, A_t, M_t)
```

| Composante | Contenu |
|---|---|
| H | état des couches (valuations B…L) |
| R | régime ∈ {quantifiable, fuzzy, mixed} |
| E | épistémique (preuves, τ, regret_asymmetry) |
| A | capacités / autorités (tokens, émetteur) |
| M | mémoire continuum (paramètres, patterns, créateur, audit) |

Transition :

```text
S_{t+1} = T(S_t, x_t)
  ssi  Capability(x_t)
     ∧ Health_F4(S_t)
     ∧ ¬Ruin(x_t)
     ∧ Evidence(x_t) ≥ τ

sinon  T → Resolve ∨ Recover ∨ Kill
```

## 5. Propriétés de sûreté (gelées en v1.0)

```text
□(critical_action ⇒ forme4_healthy)
□(cross_layer ⇒ valid_capability)
□(ruin_detected ⇒ ¬irreversible_execution)
□(write(i→j) ∧ j<i ⇒ RecoveryPath)
□(active(M3C3) ⇒ known(M3C3))
```

## 6. Activation

```text
known(M3C3)  ⇒  eligible_for_activation
```

Éligible ≠ activé. En v2, l’activation engage une portée observable A1–A3 ;
A0 reste dormant. La portée peut être transmise, pas les permissions ni
l'autorité. Elle est désactivée en fin de requête, tâche, session ou canal
réellement observé.

## 7. Export lié à S_t (v1.0)

`export_gate` n’émet que des observables de `S_t` (H, R, E, A, M).  
Mapping des champs obligatoires : voir `transition_system.export_binding`.

## 8. Binding exécutable v2

L'implémentation de référence sous [`runtime/`](../runtime/) matérialise :

- `S=(H,R,E,A,M)` dans un schéma versionné ;
- la write-rule et `enabled_iff` ;
- des capabilities signées, scopées, expirables et révocables ;
- une chaîne d'audit SHA-256 append-only ;
- l'export JSON et la restauration déterministe de snapshots après vérification
  de la chaîne et, lorsqu'ils sont fournis par un canal de confiance, du head et
  de la longueur attendus.

Ce binding ne réexécute pas les transitions métier à partir des seules intentions
et n'authentifie pas, à lui seul, une chaîne entièrement réécrite. Il n'accorde
aucune permission d'hôte. Il est une implémentation de référence testable, pas la
preuve que tous les agents appliquent le protocole.

## 9. Sûreté du noyau

S1–S5 : **proved_by_construction** — [`safety-proofs.md`](safety-proofs.md).
