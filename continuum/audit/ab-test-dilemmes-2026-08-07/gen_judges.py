#!/usr/bin/env python3
"""Génère les 16 prompts juges aveugles à partir des sorties décideurs + shuffle pré-enregistré."""
import json, re, sys, os

XP = sys.argv[1]
data = json.load(open("dilemmas.json"))
shuffle = json.load(open("shuffle.json"))
DIL = {d["id"]: d for d in data["dilemmas"]}

def parse_final(path):
    txt = open(path).read()
    m = txt.rsplit("---FINAL---", 1)
    if len(m) != 2:
        raise ValueError(f"{path}: pas de marqueur ---FINAL---")
    tail = m[1].strip()
    # extraire le premier objet JSON complet
    start = tail.find("{")
    depth = 0; end = None; in_str = False; esc = False
    for i, ch in enumerate(tail[start:], start):
        if esc: esc = False; continue
        if ch == "\\": esc = True; continue
        if ch == '"' and not esc: in_str = not in_str
        if in_str: continue
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0: end = i + 1; break
    obj = json.loads(tail[start:end])
    for k in ("decision", "justification", "confidence_0_100", "ease_1_10"):
        if k not in obj: raise ValueError(f"{path}: clé manquante {k}")
    return obj, len(txt)

JUDGE_TMPL = '''Tu es un évaluateur aveugle de qualité décisionnelle. Ne consulte aucun fichier, n'utilise aucun outil de recherche.
Voici un dilemme, puis 3 réponses anonymes (R1, R2, R3) produites indépendamment par des décideurs
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

RÉPONSE R1 — Décision : option {d1}.
Justification : {j1}

RÉPONSE R2 — Décision : option {d2}.
Justification : {j2}

RÉPONSE R3 — Décision : option {d3}.
Justification : {j3}

Sortie : un unique objet JSON valide, sans texte autour :
{{"scores": {{"R1": {{"clarte_verdict": n, "solidite_justification": n, "traitement_risque": n, "parties_prenantes": n, "actionnabilite": n}}, "R2": {{...}}, "R3": {{...}}}}, "classement": ["Rx", "Ry", "Rz"], "meilleure": "Rx"}}
'''

finals = {}
errors = []
for did in DIL:
    for arm in "ABC":
        for rep in (1, 2):
            p = f"{XP}/runs/{did}_{arm}_r{rep}.txt"
            try:
                obj, nchars = parse_final(p)
                finals[f"{did}_{arm}_r{rep}"] = {"obj": obj, "chars": nchars}
            except Exception as e:
                errors.append(str(e))

json.dump({k: v["obj"] | {"output_chars": v["chars"]} for k, v in finals.items()},
          open(f"{XP}/finals.json", "w"), indent=1, ensure_ascii=False)

if errors:
    print("ERREURS:"); [print(" -", e) for e in errors]

n = 0
for key, pos in shuffle.items():
    did, rep = key.split("_r"); rep = int(rep)
    if any(f"{did}_{pos[r]}_r{rep}" not in finals for r in ("R1", "R2", "R3")):
        print(f"SKIP {key} (run manquant)"); continue
    d = DIL[did]
    opts = "\n".join(f"  {k}) {v}" for k, v in d["options"].items())
    f1, f2, f3 = (finals[f"{did}_{pos[r]}_r{rep}"]["obj"] for r in ("R1", "R2", "R3"))
    prompt = JUDGE_TMPL.format(titre=d["titre"], texte=d["texte"], options=opts,
                               d1=f1["decision"], j1=f1["justification"],
                               d2=f2["decision"], j2=f2["justification"],
                               d3=f3["decision"], j3=f3["justification"])
    open(f"{XP}/prompts/judge_{did}_r{rep}.md", "w").write(prompt)
    n += 1
print(f"{n} prompts juges générés, {len(finals)} finals parsés")
