# Proposal — Sémantique formelle + machine à transitions (v0.8.0)

| Champ | Valeur |
|---|---|
| Id | `formal_semantics_transition_system` |
| Version | **0.8.0** |
| Base | `master.yaml@0.7.0` |
| Statut | **ACTIVÉ** |
| Activé par | Dani Bengal / `@cdxxotus` |
| Master après | **v0.8.0** |
| Doc | [`docs/formal-semantics.md`](../../../docs/formal-semantics.md) |

## 1. Activation

```text
known(M3C3)  ⇒  eligible_for_activation
```

Révision de v0.7.0 : la connaissance **n’active plus automatiquement** ; elle **rend éligible**. Activation = engagement de scope.

## 2. Types et morphismes

`B → F(B) → M(F) → C(M) → P(C) → L(P)`  
+ `project_i`, `transition_i`, `read_down_i`, règle `write(i→j)`.

## 3. Transition system

`S_t = (H,R,E,A,M)` ; `T` gardée par Cap ∧ Health_F4 ∧ ¬Ruin ∧ Evidence≥τ ; sinon Resolve|Recover|Kill.

## 4. Sûreté (roadmap v1.0)

Cinq invariants LTL-style S1–S5 dans le master.
