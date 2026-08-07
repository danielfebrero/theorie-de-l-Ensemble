#!/usr/bin/env python3
"""Génère le mélange aveugle (4 positions) puis les prompts juges du test v0.6.0.

Le mélange est produit avec une graine fixe et écrit sur disque AVANT les runs de juge,
de sorte que l'assignation position→bras ne puisse pas être ajustée après coup.

Usage :
    python3 gen_judges.py shuffle <dossier>   # graine 42, écrit shuffle.json
    python3 gen_judges.py judges  <dossier>   # lit les runs, écrit les prompts juges
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEST1 = os.path.join(HERE, "..", "ab-test-dilemmes-2026-08-07")
ARMS = ["A", "B", "C", "D"]
POS = ["R1", "R2", "R3", "R4"]
REPS = (1, 2)

JUDGE_TMPL = """Tu es un évaluateur aveugle de qualité décisionnelle. Ne consulte aucun fichier, n'utilise aucun outil.
Voici un dilemme, puis 4 réponses anonymes (R1, R2, R3, R4) produites indépendamment par des décideurs
différents. Évalue la substance décisionnelle de chaque réponse — ignore le style. Ne fais aucune
supposition sur l'origine des réponses.
Notes entières de 0 à 10 sur 5 critères :
- clarte_verdict : la réponse tranche-t-elle nettement et sans ambiguïté ?
- solidite_justification : raisonnement logique, sans trous ni affirmations gratuites, chiffres corrects si présents
- traitement_risque : pire cas, irréversibilité et asymétries correctement traités
- parties_prenantes : facteurs humains et parties prenantes réellement pris en compte
- actionnabilite : décision exécutable immédiatement, concrète

DILEMME — {titre}

{texte}

Options :
{options}

{reponses}
Sortie : un unique objet JSON valide, sans texte autour :
{{"scores": {{"R1": {{"clarte_verdict": n, "solidite_justification": n, "traitement_risque": n, "parties_prenantes": n, "actionnabilite": n}}, "R2": {{...}}, "R3": {{...}}, "R4": {{...}}}}, "classement": ["Rx", "Ry", "Rz", "Rw"], "meilleure": "Rx"}}
"""


def load_dilemmas():
    out = {}
    for path in (os.path.join(HERE, "dilemmes_complementaires.json"), os.path.join(TEST1, "dilemmas.json")):
        with open(path) as f:
            for d in json.load(f)["dilemmas"]:
                out[d["id"]] = d
    return out


def parse_final(path):
    """Extrait le premier objet JSON complet après le marqueur ---FINAL---."""
    txt = open(path).read()
    parts = txt.rsplit("---FINAL---", 1)
    if len(parts) != 2:
        raise ValueError(f"{path}: marqueur ---FINAL--- absent")
    tail = parts[1].strip()
    start = tail.find("{")
    if start < 0:
        raise ValueError(f"{path}: aucun objet JSON")
    depth, in_str, esc, end = 0, False, False, None
    for i, ch in enumerate(tail[start:], start):
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise ValueError(f"{path}: objet JSON non terminé")
    return json.loads(tail[start:end]), len(txt)


def cmd_shuffle(out):
    dils = load_dilemmas()
    random.seed(42)
    shuffle = {}
    for did in sorted(dils):
        for rep in REPS:
            arms = list(ARMS)
            random.shuffle(arms)
            shuffle[f"{did}_r{rep}"] = dict(zip(POS, arms))
    with open(os.path.join(HERE, "shuffle.json"), "w") as f:
        json.dump(shuffle, f, indent=1, ensure_ascii=False)
    print(f"shuffle.json écrit — {len(shuffle)} assignations, graine 42")


def cmd_judges(out):
    dils = load_dilemmas()
    with open(os.path.join(HERE, "shuffle.json")) as f:
        shuffle = json.load(f)

    finals, errors = {}, []
    for did in dils:
        for arm in ARMS:
            for rep in REPS:
                p = os.path.join(out, "runs", f"{did}_{arm}_r{rep}.txt")
                try:
                    obj, nchars = parse_final(p)
                    finals[f"{did}_{arm}_r{rep}"] = dict(obj, output_chars=nchars)
                except Exception as e:
                    errors.append(str(e))
    # requêtes triviales : une seule passe, pas de juge
    with open(os.path.join(HERE, "adaptivite.json")) as f:
        for r in json.load(f)["requetes"]:
            for arm in ARMS:
                p = os.path.join(out, "runs", f"{r['id']}_{arm}_r1.txt")
                try:
                    obj, nchars = parse_final(p)
                    finals[f"{r['id']}_{arm}_r1"] = dict(obj, output_chars=nchars)
                except Exception as e:
                    errors.append(str(e))

    with open(os.path.join(out, "finals.json"), "w") as f:
        json.dump(finals, f, indent=1, ensure_ascii=False)
    if errors:
        print(f"{len(errors)} erreur(s) de parsing :")
        for e in errors[:10]:
            print("  -", e)

    n = 0
    for key, pos in shuffle.items():
        did, rep = key.split("_r")
        rep = int(rep)
        if any(f"{did}_{pos[p]}_r{rep}" not in finals for p in POS):
            print(f"SKIP {key} (run manquant)")
            continue
        d = dils[did]
        opts = "\n".join(f"  {k}) {v}" for k, v in d["options"].items())
        blocs = []
        for p in POS:
            fin = finals[f"{did}_{pos[p]}_r{rep}"]
            blocs.append(
                f"RÉPONSE {p} — Décision : option {fin['decision']}.\n"
                f"Justification : {fin['justification']}\n"
            )
        prompt = JUDGE_TMPL.format(
            titre=d["titre"], texte=d["texte"], options=opts, reponses="\n".join(blocs)
        )
        with open(os.path.join(out, "prompts", f"judge_{did}_r{rep}.md"), "w") as f:
            f.write(prompt)
        n += 1
    print(f"{n} prompts juges générés · {len(finals)} finals parsés")


if __name__ == "__main__":
    cmd, out = sys.argv[1], sys.argv[2]
    {"shuffle": cmd_shuffle, "judges": cmd_judges}[cmd](out)
