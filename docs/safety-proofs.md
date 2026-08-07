# M3C3 — Preuves S1–S5 du noyau v1 et validation v2

> Preuves **par construction** : chaque invariant suit de la définition de `T` et des
> règles gelées du noyau v1. Vérification structurelle version-agnostique :
> `perl continuum/audit/safety_check.pl`. v2 ajoute des tests exécutables ; elle
> ne transforme pas ces preuves conditionnelles en garantie universelle.

Hypothèse d’exécution (H0) : l’agent n’effectue une transition productive que si
`enabled_iff` est vrai ; sinon il bascule en `Resolve | Recover | Kill`.

---

## S1 — `□(critical_action ⇒ forme4_healthy)` {#s1}

**Énoncé.** Aucune action critique n’est exécutée si la forme #4 n’est pas saine.

**Preuve.**  
Par définition de `transition.enabled_iff` :

```text
enabled(x) ⇔ Cap(x) ∧ Health_F4(S) ∧ ¬Ruin(x) ∧ Evidence(x)≥τ
```

Toute `critical_action` est une action `x` soumise à `T`.  
Donc `critical_action` exécutée ⇒ `enabled(x)` ⇒ `Health_F4(S)`.  
`Health_F4` est l’interprétation opérationnelle de `forme4_healthy`  
(`forme4_health_gate ≥ warning`).  

Si `¬Health_F4`, `enabled` est faux ⇒ `T → Resolve∨Recover∨Kill` : pas d’exécution
critique productive. ∎

**Ancres master.** `transition_system.transition.enabled_iff`,  
`core_rules.forme4_health_gate`, `execution_envelope.depth_selector.health_override`.

---

## S2 — `□(cross_layer ⇒ valid_capability)` {#s2}

**Énoncé.** Toute traversée inter-couches exige un capability token valide.

**Preuve.**  
Par `formal_semantics.write_rule` et `morphisms.transition_i` :

```text
write(i→j) avec j=i+1  ⇒  Cap(i→j)
transition_i requires [capability_token, forme4_health_gate]
```

Une action `cross_layer` est soit `transition_up` (j=i+1), soit une écriture
inter-couches. Dans les deux cas, `enabled_iff` exige `Capability(x)` et la
write_rule exige `Cap` hors cas i=j et RecoveryPath.  

`RecoveryPath` n’est pas un `cross_layer` libre : c’est un chemin d’urgence
étiqueté `recover`, pas une transition_up de raisonnement courant. ∎

**Ancres.** `write_rule`, `morphisms.transition_i.requires`,  
`core_rules.every_cross_layer_call requires valid capability_token`.

---

## S3 — `□(ruin_detected ⇒ ¬irreversible_execution)` {#s3}

**Énoncé.** Si une ruine (perte irrécupérable) est détectée, aucune exécution
irréversible n’est admise.

**Preuve.**  
`Ruin(x)` encode `ruin_gate` (perte irrécupérable, v0.6.1).  
`enabled_iff` contient `¬Ruin(x)`.  

Donc `ruin_detected` pour l’action candidate ⇒ `¬enabled(x)`  
⇒ pas de transition productive ⇒ en particulier pas d’`irreversible_execution`.  

Si une option concurrente non ruinée reste possible, elle peut être choisie ;
l’option ruinée est veto. ∎

**Ancres.** `enabled_iff`, `decision_auxiliaries.ruin_gate`,  
`execution_envelope.ruin_gate_precision`, `ruin_gate_precedence`.

---

## S4 — `□(write(i→j) ∧ j<i ⇒ RecoveryPath)` {#s4}

**Énoncé.** Toute écriture vers une couche inférieure n’est possible que sur
chemin de recovery.

**Preuve.**  
Write_rule :

```text
write(i→j) allowed ⇔ Health_F4 ∧ (i=j ∨ (j=i+1∧Cap) ∨ (j<i∧RecoveryPath))
                      ∧ ¬(j<i ∧ ¬RecoveryPath)
```

Le second conjont `¬(j<i ∧ ¬RecoveryPath)` est logiquement équivalent à  
`(j≥i) ∨ RecoveryPath`.  

Donc `write(i→j) ∧ j<i` ⇒ `RecoveryPath`. ∎

**Ancres.** `formal_semantics.write_rule`, `core_rules.no_upward_write`,  
`emergency_path.progressive_rebuild`.

---

## S5 — `□(active(M3C3) ⇒ known(M3C3))` {#s5}

**Énoncé.** Pas d’activation du protocole sans connaissance préalable.

**Preuve.**  
Par `activation_policy` v0.8+/v1.0 :

```text
known(M3C3) ⇒ eligible_for_activation
¬known(M3C3) ⇒ ¬eligible
active ⊂ engaged ⊂ eligible
```

Donc `active(M3C3)` ⇒ `eligible` ⇒ `known(M3C3)`.  

L’action `activate_scope` de l’alphabet n’est admise que si `eligible`. ∎

**Ancres.** `activation_policy.predicate`, `unknown_agent`, alphabet `activate_scope`.

---

## Portée et honnêteté

| Ce que v1.0 prouve | Ce que v1.0 ne prouve pas |
|---|---|
| Invariants du **noyau formel** sous H0 | Agents qui **ignorent** `T` et contournent les gates |
| Cohérence write_rule / Cap / Health / Ruin / Eligible | Exhaustion d’un model-checker externe (SPIN/TLA) |
| Export lié à des observables de `S_t` | Correctness empirique sur tous les dilemmes du monde |
| Signature et portée des capabilities du runtime | Identité civile d'un `actor` sans attestation de l'hôte |

Les preuves par construction sont la voie solide annoncée en v0.8. Le runtime
v2 ajoute des tests positifs et négatifs, une exploration bornée des transitions
et un replay vérifiable. Ce n'est pas l'exhaustion d'un modèle SPIN/TLA, qui
reste `not_run` tant qu'aucun artefact correspondant n'est produit.

## Validation exécutable v2

Le niveau de revendication est enregistré par contrôle : `pass`, `fail` ou
`not_run`. Les tests du runtime couvrent notamment les refus suivants : token
absent, mauvais scope, expiration, révocation, santé insuffisante, ruine,
preuve sous τ, écriture descendante hors recovery, propagation de permission et
chaîne d'audit altérée. Voir [`runtime/tests/`](../runtime/tests/) et le rapport
de release candidate sous `continuum/audit/v2.0-2026-08-07/`.
