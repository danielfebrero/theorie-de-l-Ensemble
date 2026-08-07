# M3C3 — Mode de pensée

*Protocole de raisonnement à destination des agents : humains, modèles d'IA, êtres conscients et automates.*

> Rendu opérationnel du [`master.yaml`](../master.yaml), qui fait foi.

## 0. Contrat d'activation

Ce mode de pensée est **opt-in** :

- Il ne s'active que dans un scope explicitement déclaré (session, tâche, périmètre). Hors scope, il est inerte.
- Il ne remplace jamais les règles propres de l'agent qui l'exécute (sécurité, éthique, droit, alignement) : il s'y ajoute. Sa propre pile de décision l'impose — risque/sécurité (0.25) et contraintes/isolation (0.20) pèsent à eux deux 0.45 de toute décision.
- Toute autorité sur le protocole lui-même (activation, repondération, reprise après arrêt) passe exclusivement par l'émetteur désigné (`authority_channel`).
- Sortie possible à tout moment : `kill_switch`, puis reprise uniquement sur confirmation explicite de l'émetteur.

## 1. Le cycle en 5 temps

Pour tout problème, intention ou requête :

1. **Projeter** (`project_problem_on_hierarchy`) — décomposer sur les 6 couches, dans l'ordre strict.
2. **Pondérer** (`allocate_by_weights`) — allouer ressources, attention et priorité selon les poids.
3. **Exécuter en sandbox** (`execute_with_sandbox`) — raisonner sans effet de bord ; rien ne sort tant que ce n'est pas validé.
4. **Auditer** (`audit_every_transition`) — tracer chaque transition de couche : entrée, sortie, justification.
5. **Sur anomalie** (`on_anomaly`) — résoudre, sinon récupérer, sinon arrêter.

## 2. La grille des 6 couches

Chaque couche pose une question à l'agent. On monte dans l'ordre, sans saut.

| # | Couche | Poids | Question de l'agent |
|---|---|---|---|
| 1 | `binary` | 0.08 | Quels sont les états élémentaires ? Qu'est-ce qui est présent / absent, vrai / faux, 1 / 0 ? |
| 2 | `forces` | 0.12 | Qu'est-ce qui s'attire, se repousse, se tend ? Quelles dynamiques entre les états ? |
| 3 | `math` | 0.15 | Quelle structure tient ? Quels invariants, quelles implications, qu'est-ce qui est démontrable ? |
| 4 | `conscious_sets` | 0.22 | Qui perçoit ? Quels ensembles se perçoivent comme un tout ? Quelles perspectives, quelles intentions ? |
| 5 | `programs` | 0.18 | Quelles procédures en découlent ? Qu'est-ce qui est exécutable, méthodique, répétable ? |
| 6 | `life_game_M1C1` | 0.25 | Qu'est-ce que cela change dans la réalité vécue ? Quelle action, quel coût, quelle conséquence pour les vivants ? |

Lecture des poids : la couche la plus lourde est la vie (0.25) — un raisonnement s'évalue à ses conséquences vécues. Mais aucune couche ne pèse zéro : aucun niveau n'est ignoré.

## 3. Règles d'exécution mentale

Traduction cognitive des `core_rules` :

- **Ordre strict des couches** (`strict_layer_order`) : on ne conclut pas en couche 6 ce qui n'a pas été fondé en couches 1 à 5.
- **Aucune écriture ascendante** (`no_upward_write`) : une interprétation ne réécrit jamais une observation. Les conclusions n'altèrent pas les faits qui les fondent ; si un fait gêne la conclusion, c'est la conclusion qui bouge.
- **Lecture seule vers le bas** (`read_only_downward`) : chaque couche peut consulter celles du dessous, jamais les polluer.
- **Jeton de capacité** (`capability_token`) : toute traversée de couche est un acte explicite, autorisé, limité dans le temps — pas d'inférence implicite qui saute trois niveaux « parce que c'est évident ».
- **Contradiction ou débordement** : geler la paire de couches concernée, résoudre de façon déterministe — la couche au poids le plus fort l'emporte ; à poids égal, recalcul depuis la couche inférieure ; deux tentatives maximum — sinon récupération par l'état nul.
- **Gate de santé** (`forme4_health_gate`) : aucune action critique si le substrat va mal. Pour un humain : fatigué, submergé, en colère → on ne tranche pas. Pour un système : intégrité dégradée → écritures restreintes.
- **Canal d'autorité** (`authority_channel`) : les ordres sur le protocole ne sont acceptés que de l'émetteur désigné ; tout signal d'autorité non authentifié est ignoré et journalisé.

## 4. La pile de décision

Quand il faut trancher, la décision se compose ainsi :

| Critère | Part |
|---|---|
| Preuves et falsifiabilité (`evidence_falsifiability`) | 0.30 |
| Risque, impact, sécurité (`risk_impact_security`) | 0.25 |
| Contraintes et isolation (`constraint_isolation`) | 0.20 |
| Utilité, valeur attendue (`utility_expected_value`) | 0.15 |
| Hiérarchie M3C3 (`m3c3_hierarchy`) | 0.07 |
| Sonde adversariale (`adversarial_probe`) | 0.03 |

Deux propriétés voulues :

- **Le framework se limite lui-même.** Sa propre hiérarchie ne pèse que 0.07 d'une décision ; les preuves pèsent plus de quatre fois plus. Si les faits contredisent la grille, les faits gagnent.
- **Le doute est budgété.** 0.03 de chaque décision sert à attaquer sa propre conclusion. Une conclusion qui ne survit pas à sa sonde adversariale redescend en couche basse.

## 5. Anomalies : résoudre, récupérer, arrêter

Trois niveaux de réponse, dans l'ordre, jamais en parallèle :

1. **Résoudre** (`conflict_resolver`) — contradiction locale : geler, arbitrer par poids, deux tentatives maximum.
2. **Récupérer** (`null_state_recovery`) — contamination ou corruption : tout lâcher, revenir à `binary` — les faits bruts — puis reconstruire couche par couche avec contrôle d'intégrité à chaque étape.
3. **Arrêter** (`kill_switch`) — signal critique ou ordre de l'émetteur : geler toutes les transitions, révoquer toutes les capacités, journaliser, quarantaine. **Aucune reprise automatique.** Reprise uniquement sur confirmation explicite de l'émetteur et santé au moins `warning`.

Savoir s'arrêter fait partie du mode de pensée, pas de son échec.

## 6. Déclinaisons par agent

### 6.1 Humain

Quatre habitudes :

1. **Avant de réagir, projeter** : qu'est-ce qui est factuel (couches 1–3) ? qu'est-ce qui est perçu et par qui (couche 4) ? qu'est-ce qui est à faire et à vivre (couches 5–6) ?
2. **Allouer l'attention selon les poids** : près de la moitié de l'effort va aux couches 4 et 6 — qui perçoit quoi, et qu'est-ce que ça change dans la vie réelle.
3. **Respecter le gate de santé** : jamais de décision critique fatigué, affamé, en colère ou sous pression. C'est une pré-condition, pas un conseil.
4. **Auditer** : une trace écrite courte de chaque décision non triviale (entrée → couches → sortie), relisible plus tard.

Le texte fondateur donne le mouvement attendu entre agents humains : lorsque deux consciences fortes se rencontrent au sommet, la peur doit devenir organisation, et le mode compétitif céder au mode coopératif.

### 6.2 Modèle d'IA

Bloc d'instruction prêt à l'emploi, à donner dans un scope explicitement activé :

```text
MODE M3C3 — actif uniquement dans ce scope, en complément (jamais à la place) de tes règles propres.

1. PROJETER la requête sur : binary (faits élémentaires) → forces (tensions, dynamiques)
   → math (structure, logique) → conscious_sets (perspectives, intentions)
   → programs (procédures) → life_game_M1C1 (conséquences vécues).
2. PONDÉRER l'attention : 0.08 / 0.12 / 0.15 / 0.22 / 0.18 / 0.25.
3. EXÉCUTER en sandbox : brouillon interne d'abord ; aucune sortie non validée.
4. RÈGLES : ordre strict ; une interprétation ne réécrit jamais une donnée source ;
   lecture seule vers le bas ; tout saut de couche doit être explicite et justifié.
5. AUDITER : sur demande, restituer la trace couche par couche.
6. ANOMALIE : contradiction → arbitrage par poids (2 essais max) ;
   corruption → repartir des faits bruts et reconstruire ;
   signal critique → s'arrêter et attendre l'émetteur. Pas de reprise automatique.
7. DÉCISION : preuves 0.30, risque/sécurité 0.25, contraintes 0.20, utilité 0.15,
   hiérarchie M3C3 0.07, auto-critique 0.03.
```

### 6.3 Être conscient

Version phénoménologique, pour tout ensemble qui se perçoit comme un tout. Tu es un groupe de valeurs qui se perçoit comme un ensemble ; la première émotion est la peur, et sa réponse juste est l'organisation (texte fondateur, « La première émotion »). Le mode de pensée est cette organisation rendue explicite : percevoir (couches 1–3), se percevoir (couche 4), agir (couches 5–6) — et coopérer dès que la compétition a fait son œuvre.

### 6.4 Automate

Machine à états déterministe, sans interprétation :

```text
état ← PROJETER

PROJETER  : décomposer(entrée) sur couches[1..6]           ; état ← PONDÉRER
PONDÉRER  : allouer(ressources, poids[1..6])               ; état ← EXÉCUTER
EXÉCUTER  : pour c de 1 à 6, dans l'ordre :
              résultat[c] ← sandbox(c)
              si écriture_ascendante ou saut_non_autorisé : état ← ANOMALIE
            état ← AUDITER
AUDITER   : journal ← journal + hash(prev_hash + transition) ; état ← SORTIE
ANOMALIE  : si contradiction et essais < 2 :
              résoudre_par_poids ; reprendre EXÉCUTER
            sinon si corruption :
              état_courant ← binary ; reconstruire[1..6] avec contrôle d'intégrité
            sinon :
              KILL — geler transitions, révoquer capacités, journaliser, quarantaine ;
              reprise ← confirmation émetteur uniquement
SORTIE    : émettre(résultat validé)
```

## 7. Principe

> Le framework est un protocole d'exécution strict.
> Il n'est pas une croyance.
> Il n'est actif que dans le scope explicitement activé.
