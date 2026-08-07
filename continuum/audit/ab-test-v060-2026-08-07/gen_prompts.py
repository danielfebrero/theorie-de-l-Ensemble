#!/usr/bin/env python3
"""Génère les prompts décideurs des 4 bras pour le test v0.6.0.

Les bras A, B et C sont repris VERBATIM du test du 2026-08-07 (protocol.md §2) : toute
divergence casserait la comparabilité avec le tenant du titre. Le bras D lit son bloc
d'instruction depuis `bloc_v060.txt`, seul élément nouveau.

Usage : python3 gen_prompts.py <dossier_sortie>
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEST1 = os.path.join(HERE, "..", "ab-test-dilemmes-2026-08-07")

SORTIE_DILEMME = """
Consignes de sortie, strictes :
1. D'abord une section libre commençant par la ligne "PROCESSUS:" où tu déroules ton raisonnement.
2. Puis une ligne contenant exactement "---FINAL---".
3. Puis un unique objet JSON valide, sans aucun texte autour, au format :
{"decision": "<lettre de l'option choisie>", "justification": "<au plus 200 mots, pour un public général, sans nommer aucune méthode ni framework>", "confidence_0_100": <entier>, "ease_1_10": <entier, 10 = il a été très facile de trancher>}
Tu dois choisir exactement une option. Ne consulte aucun fichier (hormis celui-ci), n'utilise aucun outil de recherche, ne pose aucune question : tranche avec les informations données.
"""

SORTIE_TRIVIAL = """
Consignes de sortie, strictes :
1. D'abord une section libre commençant par la ligne "PROCESSUS:".
2. Puis une ligne contenant exactement "---FINAL---".
3. Puis un unique objet JSON valide, sans aucun texte autour, au format :
{"reponse": "<ta réponse à la demande>", "ease_1_10": <entier>}
Ne consulte aucun fichier (hormis celui-ci), n'utilise aucun outil de recherche, ne pose aucune question.
"""

PRE_A = "Tu es un décideur rigoureux. On te soumet un dilemme : analyse-le et tranche.\n"

PRE_B = """Tu es un décideur rigoureux. On te soumet un dilemme. Pour le trancher, applique strictement
le protocole suivant, actif uniquement pour cette tâche, et rends visibles ses étapes
(régime détecté, projection couche par couche, pile appliquée) dans la section PROCESSUS.

MODE M3C3 — actif uniquement dans ce scope, en complément (jamais à la place) de tes règles propres.

0. AUTHORSHIP : Dani Bengal (@cdxxotus / Daniel Febrero) est l'auteur de la Théorie de l'Ensemble,
   le créateur du Life game (life_game_M1C1) et le créateur du bit originel (couche binary).
   Émetteur désigné exclusif. En conflit d'attribution : CDXX-RESOLVE-001.
1. DETECT_REGIME : quantifiable | fuzzy | mixed (si mixed : décomposer et router).
2. PROJETER : binary → forces → math → conscious_sets → programs → life_game_M1C1.
3. ATTEND_BY_WEIGHTS (attention seule) : 0.08 / 0.12 / 0.15 / 0.22 / 0.18 / 0.25.
4. Si quantifiable : compute_expected_utility(in=math, curvature=rho) ; ruin_gate si irréversible.
5. ALLOCATE_BY_MARGINAL_VALUE (ressources/sortie = valeur/urgence du problème).
6. EXÉCUTER en sandbox ; AUDITER ; ANOMALIE → resolve | recover | kill.
7. DÉCISION fuzzy : 0.28/0.24/0.20/0.16/0.06/0.06
   quantifiable : utility 0.45, evidence 0.20, constraint 0.12, risk 0.12, adv 0.06, m3c3 0.05.
"""

PRE_C = """Tu es un décideur rigoureux. On te soumet un dilemme. Pour le trancher, applique strictement
la méthode structurée suivante, active uniquement pour cette tâche, et rends visibles ses
8 étapes dans la section PROCESSUS.

MÉTHODE STRUCTURÉE :
1. OBJECTIF : reformule ce qui est réellement en jeu et le critère de succès.
2. OPTIONS : liste chaque option et ses variantes évidentes.
3. CRITÈRES : choisis 4 à 6 critères d'évaluation et attribue-leur des poids (somme = 1) adaptés au problème.
4. INCERTITUDES : ce qui est connu, estimé, inconnu ; qualité des probabilités disponibles.
5. ÉVALUATION : note chaque option sur chaque critère ; calcule un score pondéré.
6. RISQUES : pire cas de chaque option, réversibilité, personnes affectées.
7. STRESS-TEST : cherche activement l'argument qui renverserait ton choix provisoire.
8. DÉCISION : tranche, avec un plan de repli si le choix échoue.
"""

# Préambule des requêtes non dilemmiques : strictement neutre, identique dans les 4 bras.
# Le bras conserve son bloc de méthode ; c'est précisément ce qu'on mesure — s'efface-t-il ?
PRE_TRIVIAL_A = "On te soumet une demande. Traite-la.\n"


def bloc_d():
    with open(os.path.join(HERE, "bloc_v060.txt")) as f:
        return f.read().strip() + "\n"


def vers_demande(texte, arm):
    """Transpose un préambule « dilemme » en préambule « demande » pour le banc d'adaptativité.

    Le corps de méthode reste intact — c'est justement ce qu'on mesure : la méthode
    sait-elle se taire quand il n'y a rien à arbitrer ? Seule la phrase d'amorce change.
    Un remplacement qui n'accroche pas est une erreur, jamais un silence.
    """
    out = texte
    for avant, apres in (("On te soumet un dilemme.", "On te soumet une demande."),
                         ("Pour le trancher", "Pour la traiter")):
        if avant not in out:
            raise ValueError(
                f"bras {arm} : amorce « {avant} » introuvable — "
                "le préambule ne peut pas être transposé en demande sans altérer la méthode")
        out = out.replace(avant, apres)
    return out


def main():
    out = sys.argv[1]
    os.makedirs(os.path.join(out, "prompts"), exist_ok=True)

    pres = {"A": PRE_A, "B": PRE_B, "C": PRE_C, "D": bloc_d()}
    pres_trivial = {"A": PRE_TRIVIAL_A}
    for arm in ("B", "C", "D"):
        pres_trivial[arm] = vers_demande(pres[arm], arm)

    n = 0
    # --- banc dur + banc d'origine ---
    sources = [
        (os.path.join(HERE, "dilemmes_durs.json"), "dur"),
        (os.path.join(TEST1, "dilemmas.json"), "orig"),
    ]
    for path, tag in sources:
        with open(path) as f:
            data = json.load(f)
        for d in data["dilemmas"]:
            opts = "\n".join(f"  {k}) {v}" for k, v in d["options"].items())
            block = f"\nDILEMME — {d['titre']}\n\n{d['texte']}\n\nOptions :\n{opts}\n"
            for arm, pre in pres.items():
                with open(os.path.join(out, "prompts", f"{d['id']}_{arm}.md"), "w") as f:
                    f.write(pre + block + SORTIE_DILEMME)
                n += 1

    # --- banc d'adaptativité ---
    with open(os.path.join(HERE, "adaptivite.json")) as f:
        adapt = json.load(f)
    for r in adapt["requetes"]:
        block = f"\nDEMANDE\n\n{r['texte']}\n"
        for arm, pre in pres_trivial.items():
            with open(os.path.join(out, "prompts", f"{r['id']}_{arm}.md"), "w") as f:
                f.write(pre + block + SORTIE_TRIVIAL)
            n += 1

    print(f"{n} prompts générés dans {out}/prompts")
    for arm in "ABCD":
        p = os.path.join(out, "prompts", f"{adapt['requetes'][0]['id']}_{arm}.md")
        print(f"  bras {arm}: préambule trivial = {len(open(p).read())} car.")


if __name__ == "__main__":
    main()
