#!/usr/bin/env python3
"""Jury en tête-à-tête v0.6.0 (bras D) contre v0.6.1 (bras E).

Le juge ne voit que deux réponses, anonymisées et mélangées par une graine fixe écrite
avant les runs de juge. La rubrique est reprise mot pour mot des deux tests précédents :
la comparabilité serait perdue si elle bougeait, fût-ce d'un adjectif.

Usage :
    python3 gen_judges_h2h.py shuffle          # graine 42 → shuffle_h2h.json
    python3 gen_judges_h2h.py judges <dir_E>   # lit les runs E et ceux de v0.6.0
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V060 = os.path.join(HERE, "..", "ab-test-v060-2026-08-07")
TEST1 = os.path.join(HERE, "..", "ab-test-dilemmes-2026-08-07")
POS = ["R1", "R2"]
REPS = (1, 2)

TMPL = """Tu es un évaluateur aveugle de qualité décisionnelle. Ne consulte aucun fichier, n'utilise aucun outil.
Voici un dilemme, puis 2 réponses anonymes (R1, R2) produites indépendamment par des décideurs
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
{{"scores": {{"R1": {{"clarte_verdict": n, "solidite_justification": n, "traitement_risque": n, "parties_prenantes": n, "actionnabilite": n}}, "R2": {{...}}}}, "meilleure": "Rx"}}
"""


def dilemmes():
    out = {}
    for p in (os.path.join(V060, "dilemmes_complementaires.json"),
              os.path.join(TEST1, "dilemmas.json")):
        with open(p) as f:
            for d in json.load(f)["dilemmas"]:
                out[d["id"]] = d
    return out


def parse_final(path):
    txt = open(path).read()
    tail = txt.rsplit("---FINAL---", 1)[-1].strip()
    start = tail.find("{")
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
    return json.loads(tail[start:end]), len(txt)


def cmd_shuffle(_=None):
    random.seed(42)
    sh = {}
    for did in sorted(dilemmes()):
        for rep in REPS:
            arms = ["D", "E"]
            random.shuffle(arms)
            sh[f"{did}_r{rep}"] = dict(zip(POS, arms))
    with open(os.path.join(HERE, "shuffle_h2h.json"), "w") as f:
        json.dump(sh, f, indent=1, ensure_ascii=False)
    print(f"shuffle_h2h.json — {len(sh)} assignations, graine 42")


def cmd_judges(dir_e):
    dils = dilemmes()
    with open(os.path.join(HERE, "shuffle_h2h.json")) as f:
        sh = json.load(f)
    with open(os.path.join(V060, "runs", "finals.json")) as f:
        finals_d = json.load(f)

    finals, manquants = {}, []
    for did in dils:
        for rep in REPS:
            kd = f"{did}_D_r{rep}"
            if kd in finals_d:
                finals[kd] = finals_d[kd]
            else:
                manquants.append(kd)
            pe = os.path.join(dir_e, "runs", f"{did}_E_r{rep}.txt")
            try:
                obj, n = parse_final(pe)
                finals[f"{did}_E_r{rep}"] = dict(obj, output_chars=n)
            except Exception:
                manquants.append(f"{did}_E_r{rep}")

    with open(os.path.join(HERE, "finals_E.json"), "w") as f:
        json.dump({k: v for k, v in finals.items() if "_E_" in k}, f,
                  indent=1, ensure_ascii=False)

    n = 0
    for key, pos in sh.items():
        did, rep = key.split("_r")
        rep = int(rep)
        if any(f"{did}_{pos[p]}_r{rep}" not in finals for p in POS):
            continue
        d = dils[did]
        opts = "\n".join(f"  {k}) {v}" for k, v in d["options"].items())
        blocs = [f"RÉPONSE {p} — Décision : option {finals[f'{did}_{pos[p]}_r{rep}']['decision']}.\n"
                 f"Justification : {finals[f'{did}_{pos[p]}_r{rep}']['justification']}\n"
                 for p in POS]
        with open(os.path.join(dir_e, "prompts", f"judge_{key}.md"), "w") as f:
            f.write(TMPL.format(titre=d["titre"], texte=d["texte"], options=opts,
                                reponses="\n".join(blocs)))
        n += 1
    print(f"{n} prompts juges tête-à-tête · {len(manquants)} runs manquants"
          + (f" : {manquants[:6]}" if manquants else ""))


if __name__ == "__main__":
    {"shuffle": cmd_shuffle, "judges": cmd_judges}[sys.argv[1]](
        sys.argv[2] if len(sys.argv) > 2 else None)
