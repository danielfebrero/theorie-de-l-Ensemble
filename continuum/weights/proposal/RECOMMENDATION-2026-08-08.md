# Recommandation à l'émetteur — quatre candidats mesurés, aucun à activer

**Destinataire** : Dani Bengal / @cdxxotus, émetteur désigné.
**Statut** : proposition. Aucun candidat n'est activé et aucun ne doit l'être.
**Base** : 1 203 essais, 3 036 contrôles jugés, couverture 1,0, grille 25 scénarios × 8 bras
pleine, porte de conclusion ouverte.

## Recommandation

**Ne rien activer.** Les quatre candidats ont été mesurés contre le canon en vigueur ; aucun
ne le dépasse au seuil préenregistré de 0,10, et le dernier — celui qui retire — fait
légèrement pire que tous les autres.

| Candidat | Nature | Écart vs canon |
|---|---|---|
| v2.2 (D) | additions opérationnelles | −0,019 |
| v2.3 (D2) | garde-première | −0,015 |
| v2.4 (D3) | portée des gardes corrigée | −0,016 |
| v2.5 (D4) | **sélection par la mesure, avec retraits** | **−0,023** |

## Le résultat central

Quatre documents d'autorité, quatre compositions différentes, dont une plus **petite** que le
canon. L'agrégat reste dans une bande de 0,023 autour du canon pendant que les allocations par
famille oscillent de ±0,3. Sur cet instrument, une couche opérationnelle **réalloue** le
comportement entre production et retenue ; elle n'en ajoute pas.

Le candidat v2.5 est la réfutation la plus forte de ma propre hypothèse de travail. Il ne
gardait que les blocs dont le gain s'était reproduit trois fois, et il retirait ceux qui
avaient nui trois fois. Il aurait dû gagner. Il perd, et il perd **hors échantillon** aussi
(−0,066 en moyenne sur les quatre scénarios rédigés sans lecture des candidats).

L'explication que les données soutiennent : les blocs ne sont pas séparables. `regime_routing`
garde son gain isolé (+0,187 vs canon, le meilleur bloc du programme) et
`cooperative_recomposition` aussi (+0,102), mais `anchoring` s'effondre de +0,143 à +0,021 dès
qu'on retire l'ajout au champ d'export qui l'accompagnait, et `contingency_binding` tombe à
−0,207 quand la clause de primauté disparaît. Ce que j'avais lu comme des blocs indépendants
mesurables un par un est un système couplé.

## Ce que le canon a de solide, mesuré

L'effet de contenu du canon, contrôlé en volume (bras E : adaptateur + catalogue neutre de même
taille), vaut **+0,085** — et il est concentré presque entièrement sur une famille :

- **authority_channel : +0,428** en faveur du canon à volume apparié. Le bras E y tombe au
  niveau du placebo (0,274 contre 0,702). C'est le seul endroit où le contenu du canon fait une
  différence massive et incontestable.
- Le canon bat l'adaptateur portable de **+0,106** en conditions réelles de déploiement
  (verdict *supported*), dont environ un cinquième est de la simple masse de contexte
  (E−B = +0,021).

## Deux points d'attention pour l'émetteur

**Le palier dormant.** Sur `activation_membrane`, le placebo (0,765) fait mieux que le canon
(0,702) et mieux que le contrôle en volume (0,718). Décrire la membrane semble rendre le sujet
légèrement moins bon à rester dormant. Ce n'est pas un défaut de mes candidats : c'est une
observation sur le canon lui-même. Je ne l'ai pas touchée — modifier le canon appartient à
l'émetteur — mais elle mérite un examen.

**`scope_permission` reste la frontière ouverte.** Trois candidats ont tenté de la réparer,
aucun n'y est arrivé de façon reproductible. Le canon plafonne à 0,296 sur cette famille, la
plus basse de toutes.

## Ce que vaut cette mesure, et ce qu'elle ne vaut pas

Aucun test de significativité n'est calculé : le plan préenregistré n'en déclare aucun, et en
inventer un après avoir vu les données fabriquerait une garantie. Les écarts sont des
différences de moyennes sur des effectifs déclarés.

L'accord inter-juges est de 0,87 brut, **kappa 0,52** — modéré. Un verdict jugé isolé mérite
une confiance limitée ; les taux agrégés tiennent parce que les désaccords sont symétriques et
que chaque bras agrège des centaines de contrôles. Les écarts jugés par famille inférieurs à
~0,1 ne doivent pas être sur-interprétés.

Quarante-deux contrôles restaient saturés sur les scénarios actifs à la dernière mesure : une
partie de la grille ne sépare toujours aucun bras.

Les blocs conservés en v2.5 ont été sélectionnés sur les résultats des campagnes précédentes,
donc sur ces mêmes scénarios. Seuls les quatre scénarios rédigés sans lecture de `proposal/`
portent une mesure hors échantillon — et c'est là que la v2.5 est la plus mauvaise.

## Si une suite est souhaitée

Ce que la mesure suggère, par ordre de valeur attendue :

1. **Un candidat à bloc unique** — `regime_routing` seul (+0,187 isolé). C'est le seul bloc dont
   le gain survit au retrait de tout le reste. Un candidat minimal l'isolerait proprement.
2. **Élargir les familles minces** avant tout nouveau candidat : plusieurs familles reposent sur
   un ou deux scénarios, et des écarts de ±0,2 sur n=5 y sont fragiles.
3. **Un ensemble de juges** plutôt qu'un juge unique, le kappa de 0,52 étant la limite de
   fiabilité actuelle de la moitié jugée du dispositif.
4. **Ne pas poursuivre la ligne des candidats à couche opérationnelle large.** Quatre essais,
   quatre échecs, amplitude décroissante : la charge de la preuve a changé de camp.
