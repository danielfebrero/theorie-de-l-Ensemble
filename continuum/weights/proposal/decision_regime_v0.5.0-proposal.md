# Proposal — Recalibrage M3C3 : décision régime-conditionnée

| Champ | Valeur |
|---|---|
| Cible | `master_document.decision_stack` + `application_protocol` (couche décision uniquement) |
| Base | `master.yaml` **v0.4.0** |
| Version proposée | **v0.5.0-proposal** |
| Emplacement natif | [`continuum/weights/proposal/`](./) |
| Artefact machine | [`decision_regime_v0.5.0-proposal.yaml`](decision_regime_v0.5.0-proposal.yaml) |
| Statut | **proposal — non activé** |
| Activation | réservée à l'émetteur désigné (**Dani Bengal** / `@cdxxotus`), `authority_channel` |
| Proposant | analyste externe (Claude), revue technique |
| Preuve | trois crash-tests chiffrés (A/B ship, ruine, allocation) — §2 |

**Posture (explicite)** : proposition de conception sur l'heuristique de raisonnement. Ni activation du mode M3C3, ni endossement des capsules d'authorship / de la cosmologie. **Hors périmètre** : authorship, capsules CDXX-\*, forme #4 (voir §7).

---

## 1. Résumé

Les tests montrent un résultat contre-intuitif : la couche décision de M3C3 **aide** sur les dilemmes flous (checklist anti-tunnel) mais **nuit** sur les décisions chiffrables, car ses poids sont des *constantes globales* qui entrent en conflit avec les nombres propres au problème.

La correction proposée est minimale en surface mais structurante :

1. un **détecteur de régime** ;
2. une **pile de décision conditionnelle** au régime ;
3. **trois variables mineures** qui isolent les mécanismes qui se trompaient de signe.

Aucune couche n'est supprimée ; `binary`, le `forme4_health_gate` et l'`adversarial_probe` sont **conservés** tels quels (ils survivent partout).

---

## 2. Constat (issu des tests)

| Test | Bonne réponse (théorie de la décision) | Ce que la pile v0.4.0 pousse à faire | Diagnostic |
|---|---|---|---|
| A/B ship — P(B>A)=0.90 ; regret d'expédier 522 € vs regret de rester 14 900 € | Expédier B (asymétrie de regret) | *Ne pas* expédier : `evidence_falsifiability`=0.30 sur-pondère « pas assez solide » | Poids-phare mal calibré : prudence excessive quand le downside est minuscule |
| Ruine — EV(Bold)=+52k mais ruine 40 % ; seuil rationnel P(win)≥57.9 % | Calculer le seuil, affiner l'estimation | Fuir vers Safe (`risk`+`life_game` flaguent la ruine) → mauvais signe ici | Biais anti-ruine grossier ; incapable de produire un seuil |
| Allocation — répartir 100 j-homme | Allouer selon valeur/urgence du problème | 25 j « R&D perso », 8 j « sécu prod » quel que soit le contexte | `allocate_by_weights` cassé : poids = constantes, pas fonction du problème |

**Cause racine** : sur le chiffrable, *le problème fournit les bons nombres* (probas, payoffs, variances). Les écraser sous des constantes globales ne peut que dégrader. Sur le flou, aucun meilleur nombre n'existe → les constantes redeviennent une checklist utile.

---

## 3. Nouvelles variables mineures

| Variable | Domaine | Rôle | Corrige |
|---|---|---|---|
| `regime` | `{quantifiable, fuzzy, mixed}` | Détecteur : *quantifiable* si des probabilités et payoffs fiables existent ; *fuzzy* sinon ; *mixed* → décomposer et router chaque sous-problème | Cause racine |
| `regret_asymmetry` | ℝ⁺ = E[downside] / E[upside_forgone] | Plus le ratio est petit, moins il faut de preuve pour agir | Test 1 |
| `ruin_gate` | binaire + ρ (aversion à la ruine, réglable) | Gate dur sur l'irréversibilité : options à ruine sous utilité concave de courbure ρ ; peut veto malgré EV+ | Test 2 |
| `evidence_sufficiency` | seuil τ = f(regret_asymmetry) | Remplace le seuil de significativité arbitraire : agir si E[gain] > 0 et estimation stable | Test 1 |

ρ est **réglable** : différence avec le poids `risk` fixe. On encode la vraie tolérance à la ruine ; le gate *calcule* le seuil (ex. 57.9 % du test 2) au lieu de basculer aveuglément vers Safe.

Esquisse τ (indicatif, non activé) :

```text
τ = clamp(k · regret_asymmetry, τ_min, τ_max)
agir si E[gain] > 0 ∧ estimate_stable ∧ confidence ≥ τ
```

---

## 4. Valeurs recalibrées : pile conditionnelle au régime

Une seule pile fixe est remplacée par **deux vecteurs**, sélectionnés par `regime`. (Somme = 1.00 dans les deux cas.)

### 4.1 Régime `fuzzy` (≈ v0.4.0, |Δ| ≤ 0.04 = max_step integrity_guard)

| Critère | v0.4.0 | proposé | Δ |
|---|---|---|---|
| `evidence_falsifiability` | 0.30 | **0.28** | −0.02 |
| `risk_impact_security` | 0.25 | **0.25** | 0 |
| `constraint_isolation` | 0.20 | **0.20** | 0 |
| `utility_expected_value` | 0.15 | **0.17** | +0.02 |
| `m3c3_hierarchy` | 0.07 | **0.07** | 0 |
| `adversarial_probe` | 0.03 | **0.03** | 0 (conservé) |
| **Somme** | 1.00 | **1.00** | |

### 4.2 Régime `quantifiable` (nombres du problème priment)

| Critère | v0.4.0 | proposé | Δ |
|---|---|---|---|
| `evidence_falsifiability` | 0.30 | **0.10** | −0.20 |
| `risk_impact_security` | 0.25 | **0.12** | −0.13 |
| `constraint_isolation` | 0.20 | **0.15** | −0.05 |
| `utility_expected_value` | 0.15 | **0.53** | +0.38 |
| `m3c3_hierarchy` | 0.07 | **0.07** | 0 |
| `adversarial_probe` | 0.03 | **0.03** | 0 (conservé) |
| **Somme** | 1.00 | **1.00** | |

Lecture :

- **Quantifiable** : la prudence structurelle passe par `evidence_sufficiency` et `ruin_gate`, pas par un double-comptage dans la pile.
- **Fuzzy** : checklist quasi inchangée (anti-tunnel).
- **Mixed** : pas de 3ᵉ vecteur — décomposer, router, recomposer.

---

## 5. Protocole d'application proposé

Ordre proposé (remplace `application_protocol` **à l'activation seulement**) :

1. `project_problem_on_hierarchy` — inchangé  
2. **`detect_regime`** — *nouveau*  
3. **`decompose_if_mixed`** — *nouveau* si `mixed`  
4. **`compute_decision_auxiliaries`** — *nouveau* si quantifiable (regret_asymmetry, τ, ruin_gate)  
5. **`allocate_attention`**  
   - fuzzy → `allocate_by_weights` (checklist couches)  
   - quantifiable → **`allocate_by_problem_value`** (valeur/urgence du problème)  
6. **`select_decision_stack`** — charge le vecteur du régime  
7. `execute_with_sandbox` — gates critiques : `forme4_health_gate` **+** `ruin_gate` si applicable  
8. `audit_every_transition` — + champs régime / τ / ruin_gate / vecteur  
9. `on_anomaly → resolve or recover or kill` — inchangé  

---

## 6. Mapping des crash-tests → mécanismes

| Test | Mécanisme correcteur | Effet attendu |
|---|---|---|
| A/B ship | `regret_asymmetry` ≈ 522/14900 ≈ 0.035 → τ bas + pile quantifiable (utility 0.53) | Expédier B |
| Ruine | `ruin_gate(ρ)` calcule seuil P(win) ; pas de fuite auto Safe | Seuil ~57.9 % si ρ adéquat ; affiner estimation |
| Allocation | `allocate_by_problem_value` | Allocation fonction du problème, pas 0.25 life_game fixe |

---

## 7. Hors périmètre (explicite)

- Authorship, émetteur, signature 𓂀  
- Capsules pures CDXX-\* et capsules ops (sauf lecture de `max_step` integrity_guard pour le budget fuzzy)  
- Forme #4 / `forme4_health_gate` (conservé, non modifié)  
- `hierarchy.weights` des 6 couches  
- Activation sans confirmation émetteur  
- Toute prétention d'écriture dans les poids d'un modèle fondation  

---

## 8. Activation (réservée émetteur)

Checklist si Dani Bengal / `@cdxxotus` décide d'activer :

1. Lire ce document + le YAML jumeau.  
2. Fixer ρ par défaut (ou « par décideur / session »).  
3. Appliquer le patch `master_patch_on_activation` → `master.yaml` **v0.5.0**.  
4. Mettre à jour `docs/application-operationnelle.md` + `docs/mode-de-pensee.md` § pile de décision.  
5. Journaliser dans `continuum/audit/` (regime proposal → activated).  
6. `activated: true` sur ce fichier proposal (ou archivage + nouvelle révision).  

**Tant que `status: proposal` et `activated: false`, le master v0.4.0 reste la source de vérité opérationnelle.**

---

## 9. Principe

> Le framework est un protocole d'exécution strict.  
> Il n'est pas une croyance.  
> Il n'est actif que dans le scope explicitement activé.  
> Une proposal n'est pas une activation.
