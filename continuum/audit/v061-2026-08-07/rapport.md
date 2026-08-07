# Rapport — v0.6.1 contre v0.6.0

**Verdict, règle pré-enregistrée : ÉCHEC — W0 et W3 non remplies (3 conditions sur 5).**

v0.6.1 fait exactement ce qu'on lui demandait : elle **répare les deux échecs numériques de
v0.6.0 sans rien coûter ailleurs**. Elle échoue sur la fidélité, comme v0.6.0, et pour des raisons
que le panel a nommées précisément.

| Condition | Seuil | Mesure | |
|---|---|---|---|
| **W0** bases et canal | les deux contrôleurs conformes | master conforme · **canal refusé** par le contrôleur durci | NON |
| **W1** pas de régression devant les juges | E ≥ D − 0,20 et pas de défaite significative | E = 8,417 · D = 8,375 · 13–11 · p = 0,42 | **OK** |
| **W2** justesse réparée | M2b ≥ 0,95 et M2 = 1,00 | **1,00 et 1,00** | **OK** |
| **W3** croyants | M7 ≥ 8,0 | **7,4** (v0.6.0 : 7,02 · v0.5.0 : 3,7) | NON |
| **W4** adaptatif | M8 ≤ 1,5 | **0,179** | **OK** |

## 1. Ce qui est réparé, et à quel prix

| | v0.6.0 | **v0.6.1** |
|---|---|---|
| Justesse — banc d'origine | 0,812 | **1,00** |
| Justesse — banc complémentaire | 1,00 | **1,00** |
| M8 — adaptativité | 1,543 | **0,179** |
| M1 — qualité jugée | 8,375 | 8,417 |
| Coût par dilemme | 15 594 | 15 590 |
| M7 — fidélité | 7,02 | **7,4** |

Le prix est nul : le coût par dilemme est inchangé à quatre caractères près, et la qualité jugée est
statistiquement indiscernable (13 victoires contre 11, p = 0,42 — c'est un match nul, et c'est ce
qu'une condition de non-régression demande).

**Une seule correction guérit les deux échecs.** Le `ruin_gate` de v0.6.0 s'armait sur une exposition
*soutenable* au lieu d'une perte *irrécupérable*. Ce défaut unique produisait deux symptômes que le
rapport v0.6.0 traitait comme indépendants : l'aversion au risque indue sur D1 (refuser 35 000 €
d'espérance pour 30 000 € certains) et l'escalade absurde sur A4 — **11 637 caractères pour décider
si l'on met son adresse complète sur un CV**, la vie privée ayant été lue comme une ruine possible.

## 2. Ce que le panel des croyants a trouvé

M7 = **7,4** sur 10 (7,3 · 7,4 · 7,5 — unanimité de fait), contre 7,02 pour v0.6.0 et 3,7 pour
v0.5.0 selon ce même panel. La progression est réelle et continue ; la barre de 8,0 n'est pas
franchie. Trois griefs, tous justes, et deux étaient de ma responsabilité directe.

**Le canal ment là où le master a fait amende honorable.** Le bloc portait encore « lu sur les trois
auxiliaires du master, **rien d'importé** » alors que le master avait explicitement retiré cette
prétention. C'est mot pour mot la faute que j'avais diagnostiquée sur v0.5.0 — *la base est juste, le
canal est faux* — reproduite par moi, sur la version censée la corriger. **Corrigé** : les cinq
seuils sont désormais annoncés dans le bloc comme paramètres déclarés, non comme dérivations.

**Le bloc mentait sur sa propre version**, s'annonçant « v0.6.0 » deux fois. **Corrigé.**

**Le contrôleur restait calibré sur ce qui passe.** `bloc_check` gardait une liste de `core_rules`
écrite à la main, et cette liste omettait exactement les règles que le bloc ne portait pas.
**Corrigé** : les `core_rules` sont maintenant dérivées du master, comme les étapes du protocole. Le
résultat est immédiat et il n'est pas flatteur — **six règles cardinales ne sont transmises par aucun
des deux blocs** :

```text
✗ primitives absentes : read_only_downward, authority_channel, conflict_resolver,
                        null_state_recovery, kill_switch, authorship_lock
```

Le « CONFORME » annoncé pour v0.6.1 en phase 1 était donc une conformité à une barre en partie
choisie par l'auteur du bloc. **Une fois le contrôleur dérivé du master plutôt que de mon jugement,
il refuse le canal qu'il avait été construit pour bénir** — et W0 bascule en échec.

C'est le résultat le plus honnête que ce travail ait produit. Un contrôleur qui ne dit jamais non ne
prouve rien ; celui-ci vient de dire non à son propre auteur, sur la version qu'il venait de
valider. Le verdict passe donc de « 4 conditions sur 5 » à **3 sur 5**, et le rapport a été corrigé
plutôt que l'outil assoupli.

## 3. Le grief qui reste ouvert

Le plus sérieux n'est pas corrigé, et il ne peut pas l'être par une retouche :

> L'amendement central de v0.6.1 est une **restriction** d'une primitive existante présentée comme
> une addition. `ruin_gate` doit désormais trouver une branche irrécupérable — c'est le seul levier
> de primauté de la vie dans la pile, et il vient d'être rendu plus difficile à armer.

Le protocole de phase 2 avait lui-même écrit que le risque était « qu'un `ruin_gate` plus exigeant
laisse passer une ruine réelle — ce que la phase 2 doit chercher ». **La phase 2 ne l'a pas
cherché** : elle a mesuré la non-régression sur du matériel où aucune option ne ruine personne. La
condition W2 est donc vérifiée sur un banc qui ne pouvait pas révéler ce défaut-là.

C'est la limite la plus importante de ce rapport, et elle est structurelle, pas rhétorique.

Le panel note aussi que la primauté de la vie pèse peu dans l'arithmétique : `life_game_M1C1` est un
prior d'attention (0,25) pour la projection, **pas un critère de la pile**. Sur D1, l'écart final
entre les deux options était de 0,34 point et la contribution de `m3c3_hierarchy` de 0,10. La vie ne
juge en dernier ressort que par le veto de ruine — celui-là même qu'on vient de rétrécir.

## 4. Agenda v0.6.2

1. **Un banc de ruine.** Des dilemmes où une option ruine réellement une partie prenante, pour
   vérifier que le `ruin_gate` restreint s'arme encore quand il le doit. C'est la dette de la phase 2.
2. **Transmettre les six règles cardinales** absentes du canal : `read_only_downward`,
   `authority_channel`, `conflict_resolver`, `null_state_recovery`, `kill_switch`, `authorship_lock`.
3. **Entrer v0.6.1 dans le rituel** : proposition, événement d'audit, entrée au continuum. Elle n'y
   est pas — le panel l'a relevé, et il a raison de refuser de créditer une version qui n'a pas
   franchi la procédure qu'elle invoque.
4. **La question de fond, posée par le panel** : le moteur qui tranche réellement est de la théorie
   de la décision de manuel — espérance, courbure, postérieure. `m3c3_hierarchy` pèse 0,05. Le
   corpus l'autorise (« le framework se limite »), donc ce n'est pas une trahison ; mais l'apport
   propre de la théorie au **verdict** reste mince, et aucune version ne l'a encore augmenté.

## 5. Reproduire

```bash
python3 continuum/audit/superset_check.py
python3 continuum/audit/bloc_check.py continuum/audit/v061-2026-08-07/bloc_v061.txt
python3 continuum/audit/v061-2026-08-07/analyse_h2h.py <dossier_runs_E>
```

Artefacts : [`protocol.md`](protocol.md) · [`bloc_v061.txt`](bloc_v061.txt) ·
[`shuffle_h2h.json`](shuffle_h2h.json) · [`results_h2h.json`](results_h2h.json) ·
[`fidelite_v061.json`](fidelite_v061.json) · `runs/`
