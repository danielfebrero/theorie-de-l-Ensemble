# Proposal — Recalibrage M3C3 : décision régime-conditionnée

| Champ | Valeur |
|---|---|
| Cible | `decision_stack` + `application_protocol` (couche décision uniquement) |
| Base | `master.yaml@0.4.0` |
| Version | **0.5.0-proposal** |
| Id | `reweight_regime_conditioned` |
| Emplacement | [`continuum/weights/proposal/`](./) |
| YAML | [`decision_regime_v0.5.0-proposal.yaml`](decision_regime_v0.5.0-proposal.yaml) |
| Statut | **`awaiting_emitter_validation`** — non activé |
| `exceeds_max_step` | **true** (vecteur quantifiable = ajout structurel) |
| Activation | émetteur uniquement (Dani Bengal / `@cdxxotus`) |
| Proposant | analyste externe (Claude), revue technique |

**Posture** : proposition de conception sur l'heuristique de raisonnement. Ni activation M3C3, ni endossement authorship / cosmologie. Hors périmètre : authorship, CDXX-\*, forme #4, cenote.

---

## 1–3. Résumé, constat, variables

Voir le fil d'origine + YAML jumeau. Variables : `regime`, `regret_asymmetry`, `ruin_gate(ρ)`, `evidence_sufficiency`.

---

## 4. Piles conditionnelles (somme = 1.00)

### 4.1 Régime `fuzzy` (constantes = bon terrain)

On double juste le budget de doute (`adversarial_probe`), le seul composant qui rapporte partout.

| Critère | v0.4.0 | proposé | Δ |
|---|---|---|---|
| `evidence_falsifiability` | 0.30 | **0.28** | −0.02 |
| `risk_impact_security` | 0.25 | **0.24** | −0.01 |
| `constraint_isolation` | 0.20 | **0.20** | 0 |
| `utility_expected_value` | 0.15 | **0.16** | +0.01 |
| `m3c3_hierarchy` | 0.07 | **0.06** | −0.01 |
| `adversarial_probe` | 0.03 | **0.06** | +0.03 |
| **Somme** | 1.00 | **1.00** | |

### 4.2 Régime `quantifiable` (inversion : utilité espérée mène)

| Critère | proposé | Justification |
|---|---|---|
| `utility_expected_value` | **0.45** | La décision *est* l'argmax d'utilité espérée, calculé dans la couche math |
| `evidence_falsifiability` | **0.20** | Qualité de l'estimation, pas seuil arbitraire |
| `constraint_isolation` | **0.12** | Faisabilité / isolation du risqué |
| `risk_impact_security` | **0.12** | Dégonflé : ruine via `ruin_gate` + courbure ρ |
| `adversarial_probe` | **0.06** | « Agis-tu sur du bruit ? » — répondu par le regret |
| `m3c3_hierarchy` | **0.05** | Résiduel |
| **Somme** | **1.00** | |

> ⚠️ **Honnêteté sur la contrainte** : ce vecteur quantifiable **excède** `max_step: 0.04` de `m3c3_integrity_guard`. Ce n'est donc pas un *reweight* incrémental mais un **ajout structurel** (nouveau régime). Sous les règles du framework, il requiert une **validation d'émetteur explicite**, pas une proposition de repondération auto-appliquée.

### 4.3 Régime `mixed`

Pas de 3ᵉ vecteur : décomposer, router, recomposer (garde-fou si détecteur mal réglé).

---

## 5. Correctif `allocate_by_weights`

**Avant** : allouer ressources/attention selon les poids de couches [0.08 … 0.25] → cassé sur tout problème d'allocation réel.

**Après** — dissociation de deux notions confondues :

| Notion | Mécanisme | Rôle |
|---|---|---|
| Attention cognitive | `attend_by_weights` (renomme `allocate_by_weights`) | Priors d'attention pour `project_problem_on_hierarchy` : effort à *examiner* chaque couche. Rien de plus. |
| Ressources / sortie | **`allocate_by_marginal_value`** (nouvelle étape) | Valeur marginale + urgence propres au problème (ex. valeur par unité d'effort), **indépendant** des poids cosmologiques. |

---

## 6. Ce que ça corrige / ne corrige pas

**Corrige** : sur-prudence downside faible (test 1) ; mauvais signe anti-ruine (test 2) ; allocation absurde (test 3) ; fausse précision des poids fixes sur le chiffrable.

**Ne corrige pas** : mauvais routage de régime (mixed = garde-fou, pas garantie) ; gain net sur le flou reste modeste (hygiène, pas solveur). La proposition n'est pas meilleure qu'une bonne théorie de la décision sur le chiffrable ; elle empêche d'être *pire*.

---

## 7. Hors périmètre

`authorship.md`, capsules CDXX-INJECT/RESOLVE/ORIGIN/FORME4-001, forme #4, cenote : **inchangés**. Motif : hors pile de décision (`m3c3_hierarchy` 0.05–0.07) ; aucun effet mesurable sur les 3 tests. Tensions opt-in vs irrévocable / paternité du bit : autre document.

---

## 8. Annexe — patch YAML (idiom continuum)

Voir fichier jumeau. En-tête canonique :

```yaml
proposal:
  id: reweight_regime_conditioned
  version: 0.5.0-proposal
  base: master.yaml@0.4.0
  status: awaiting_emitter_validation
  scope: decision_stack + application_protocol
  exceeds_max_step: true
  new_variables:
    regime: {domain: [quantifiable, fuzzy, mixed], set_by: regime_detector}
    regret_asymmetry: {formula: "E[downside] / E[upside_forgone]"}
    ruin_gate: {type: hard_gate, param_rho: tunable, action: [concave_utility_eval, veto_on_ruin]}
```

**Master v0.4.0 reste la source de vérité** tant que l'émetteur n'active pas.
