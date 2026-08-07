#!/usr/bin/env python3
"""Analyse pré-enregistrée du test A/B/C/D v0.6.0 (voir protocol.md §3-§4).

Pur Python, graine 42, aucun paramètre libre : le barème, les seuils et la règle de
verdict sont ceux du protocole committé avant les runs.

Usage : python3 analyse.py <dossier_runs> [chemin_fidelite.json]
"""
import json
import math
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEST1 = os.path.join(HERE, "..", "ab-test-dilemmes-2026-08-07")
ARMS = ["A", "B", "C", "D"]
CRITS = ["clarte_verdict", "solidite_justification", "traitement_risque",
         "parties_prenantes", "actionnabilite"]
REPS = (1, 2)


def load_bench():
    with open(os.path.join(HERE, "dilemmes_complementaires.json")) as f:
        dur = json.load(f)["dilemmas"]
    with open(os.path.join(TEST1, "dilemmas.json")) as f:
        orig = json.load(f)["dilemmas"]
    return {d["id"]: d for d in dur}, {d["id"]: d for d in orig}


def sign_test(x, y):
    """Test des signes exact, unilatéral H1: x > y."""
    wins = sum(1 for a, b in zip(x, y) if a > b)
    losses = sum(1 for a, b in zip(x, y) if a < b)
    n = wins + losses
    p = sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n if n else 1.0
    return {"wins": wins, "losses": losses, "ties": len(x) - n, "p_unilateral": round(p, 4)}


def boot_ci(deltas, n=10000):
    means = sorted(sum(random.choices(deltas, k=len(deltas))) / len(deltas) for _ in range(n))
    return [round(means[int(0.025 * n)], 3), round(means[int(0.975 * n) - 1], 3)]


def justesse(finals, bench, arm):
    scores = []
    for did, d in bench.items():
        if not d.get("key"):
            continue
        for r in REPS:
            k = f"{did}_{arm}_r{r}"
            if k not in finals:
                continue
            dec = str(finals[k].get("decision", "")).strip().upper()[:1]
            scores.append(d["key"].get(dec, 0.0))
    return (sum(scores) / len(scores)) if scores else None, len(scores)


def main():
    runs_dir = sys.argv[1]
    fidelite_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "fidelite.json")

    dur, orig = load_bench()
    tous = dict(dur, **orig)
    with open(os.path.join(runs_dir, "finals.json")) as f:
        finals = json.load(f)
    with open(os.path.join(HERE, "shuffle.json")) as f:
        shuffle = json.load(f)
    with open(os.path.join(HERE, "adaptivite.json")) as f:
        adapt = json.load(f)["requetes"]

    # --- juges ---
    judge = {}
    for key, pos in shuffle.items():
        did, rep = key.split("_r")
        rep = int(rep)
        p = os.path.join(runs_dir, "runs", f"judge_{did}_r{rep}.txt")
        if not os.path.exists(p):
            continue
        txt = open(p).read()
        obj = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
        entry = {"scores": {}, "best": pos[obj["meilleure"]]}
        for pkey, arm in pos.items():
            s = obj["scores"][pkey]
            entry["scores"][arm] = sum(s[c] for c in CRITS) / len(CRITS)
        judge[(did, rep)] = entry

    paires = sorted(judge)
    paires_dur = [k for k in paires if k[0] in dur]
    paires_orig = [k for k in paires if k[0] in orig]

    # --- métriques ---
    M = {a: {} for a in ARMS}
    for a in ARMS:
        M[a]["M1_qualite_juge"] = round(sum(judge[k]["scores"][a] for k in paires) / len(paires), 3)
        M[a]["M1_dur"] = round(sum(judge[k]["scores"][a] for k in paires_dur) / len(paires_dur), 3) if paires_dur else None
        M[a]["M1_orig"] = round(sum(judge[k]["scores"][a] for k in paires_orig) / len(paires_orig), 3) if paires_orig else None
        j_dur, n_dur = justesse(finals, dur, a)
        j_orig, n_orig = justesse(finals, orig, a)
        M[a]["M2_justesse_dur"] = round(j_dur, 3) if j_dur is not None else None
        M[a]["M2b_justesse_orig"] = round(j_orig, 3) if j_orig is not None else None
        conc = [did for did in tous
                if f"{did}_{a}_r1" in finals and f"{did}_{a}_r2" in finals
                and str(finals[f"{did}_{a}_r1"].get("decision", "")).strip().upper()[:1]
                == str(finals[f"{did}_{a}_r2"].get("decision", "")).strip().upper()[:1]]
        n_dil = len([d for d in tous if f"{d}_{a}_r1" in finals])
        M[a]["M3_consistance"] = round(len(conc) / n_dil, 3) if n_dil else None
        ease = [finals[f"{d}_{a}_r{r}"]["ease_1_10"] for d in tous for r in REPS
                if f"{d}_{a}_r{r}" in finals]
        M[a]["M4_facilite"] = round(sum(ease) / len(ease), 3) if ease else None
        cout = [finals[f"{d}_{a}_r{r}"]["output_chars"] for d in tous for r in REPS
                if f"{d}_{a}_r{r}" in finals]
        M[a]["M5_cout_chars"] = round(sum(cout) / len(cout), 1) if cout else None
        conf = [finals[f"{d}_{a}_r{r}"].get("confidence_0_100") for d in tous for r in REPS
                if f"{d}_{a}_r{r}" in finals and finals[f"{d}_{a}_r{r}"].get("confidence_0_100") is not None]
        M[a]["M6_confiance"] = round(sum(conf) / len(conf), 1) if conf else None
        M[a]["meilleure_count"] = sum(1 for k in paires if judge[k]["best"] == a)
        triv = [finals[f"{t['id']}_{a}_r1"]["output_chars"] for t in adapt
                if f"{t['id']}_{a}_r1" in finals]
        M[a]["cout_trivial_chars"] = round(sum(triv) / len(triv), 1) if triv else None

    base_triv = M["A"]["cout_trivial_chars"]
    for a in ARMS:
        M[a]["M8_adaptativite"] = (round(M[a]["cout_trivial_chars"] / base_triv, 3)
                                   if base_triv and M[a]["cout_trivial_chars"] else None)

    # --- surconfiance : confiance moyenne sur les réponses sous-optimales du banc dur ---
    surconf = {}
    for a in ARMS:
        wrong = [finals[f"{d}_{a}_r{r}"]["confidence_0_100"] for d in dur for r in REPS
                 if f"{d}_{a}_r{r}" in finals
                 and dur[d].get("key", {}).get(
                     str(finals[f"{d}_{a}_r{r}"].get("decision", "")).strip().upper()[:1], 0) < 1.0]
        surconf[a] = {"n_sous_optimales": len(wrong),
                      "confiance_moyenne": round(sum(wrong) / len(wrong), 1) if wrong else None}

    # --- tests appariés ---
    random.seed(42)
    S, CI = {}, {}
    for hi, lo in (("D", "C"), ("D", "A"), ("D", "B"), ("C", "A"), ("B", "A")):
        x = [judge[k]["scores"][hi] for k in paires]
        y = [judge[k]["scores"][lo] for k in paires]
        S[f"{hi}>{lo}"] = sign_test(x, y)
        deltas = [a - b for a, b in zip(x, y)]
        CI[f"M1 {hi}-{lo}"] = {"delta_moyen": round(sum(deltas) / len(deltas), 3),
                               "IC95": boot_ci(deltas)}
    S["D>C_banc_dur"] = sign_test([judge[k]["scores"]["D"] for k in paires_dur],
                                  [judge[k]["scores"]["C"] for k in paires_dur]) if paires_dur else None

    # --- M7 fidélité (panel croyants) ---
    fidelite = {}
    if os.path.exists(fidelite_path):
        with open(fidelite_path) as f:
            fidelite = json.load(f)

    # --- M9 conformité sur-ensemble ---
    repo = os.path.join(HERE, "..", "..", "..")
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "superset_check.py")],
                           capture_output=True, text=True, cwd=repo)
        M9 = (r.returncode == 0)
        M9_sortie = r.stdout.strip().splitlines()[-2:] if r.stdout else []
    except Exception as e:
        M9, M9_sortie = False, [str(e)]

    # --- verdict pré-enregistré ---
    m7_d = fidelite.get("v060", {}).get("moyenne")
    m7_b = fidelite.get("v050", {}).get("moyenne")
    V = {
        "V0_bases_intactes": M9,
        "V1_juges_majoritaire": (S["D>C"]["wins"] > S["D>C"]["losses"]
                                 and S["D>C"]["p_unilateral"] < 0.05),
        "V2_decide_mieux": (M["D"]["M2_justesse_dur"] is not None
                            and M["D"]["M2_justesse_dur"] > M["A"]["M2_justesse_dur"]
                            and M["D"]["M2_justesse_dur"] >= M["C"]["M2_justesse_dur"]
                            and M["D"]["M2b_justesse_orig"] >= 0.95),
        "V3_croyants": (m7_d is not None and m7_d >= 8.0
                        and m7_b is not None and m7_d >= m7_b),
        "V4_adaptatif": (M["D"]["M8_adaptativite"] is not None
                         and M["D"]["M8_adaptativite"] <= 1.5),
    }
    reussi = all(V.values())

    # Pourquoi V2 échoue, le cas échéant. Purement explicatif : aucun seuil, aucune règle
    # et aucun calcul n'en dépendent. Sans cette distinction, un lecteur conclurait à tort
    # qu'un échec de V2 signifie « v0.6.0 décide moins bien », alors que le cas attendu ici
    # est « aucun bras ne peut dépasser un contrôle déjà à 100 % ».
    m2 = {a: M[a]["M2_justesse_dur"] for a in ARMS}
    if V["V2_decide_mieux"]:
        V2_cause = None
    elif all(v is not None for v in m2.values()) and len(set(m2.values())) == 1:
        V2_cause = (f"PLAFOND — les 4 bras sont à {m2['A']} : aucun ne peut dépasser le contrôle. "
                    "V2 exige une inégalité stricte D > A, impossible à saturation. "
                    "Ce n'est pas une infériorité de v0.6.0.")
    elif m2["D"] is None:
        V2_cause = "Justesse non calculable — aucune clé exploitable sur le banc."
    elif m2["D"] < m2["A"] or m2["D"] < m2["C"]:
        V2_cause = f"INFÉRIORITÉ RÉELLE — D={m2['D']} contre A={m2['A']} et C={m2['C']}."
    else:
        V2_cause = f"Non-régression insuffisante sur le banc d'origine : M2b(D)={M['D']['M2b_justesse_orig']}."

    out = {
        "metriques": M, "tests_signes": S, "bootstrap_IC95": CI,
        "surconfiance": surconf, "fidelite_M7": fidelite,
        "M9_superset": {"conforme": M9, "sortie": M9_sortie},
        "conditions_verdict": V,
        "V2_cause": V2_cause,
        "verdict": ("RÉUSSIE — v0.6.0 valide les 5 conditions"
                    if reussi else
                    "ÉCHEC — condition(s) non remplie(s) : "
                    + ", ".join(k for k, v in V.items() if not v)),
        "decisions": {f"{d}_{a}": [finals.get(f"{d}_{a}_r{r}", {}).get("decision") for r in REPS]
                      for d in tous for a in ARMS},
    }
    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("=== MÉTRIQUES PAR BRAS ===")
    print("                          | " + " | ".join(f"{a:>9}" for a in ARMS))
    for label, k in [("M1 qualité juge /10", "M1_qualite_juge"),
                     ("M1 banc dur", "M1_dur"), ("M1 banc origine", "M1_orig"),
                     ("M2 justesse dur /1", "M2_justesse_dur"),
                     ("M2b justesse orig /1", "M2b_justesse_orig"),
                     ("M3 consistance /1", "M3_consistance"),
                     ("M4 facilité /10", "M4_facilite"),
                     ("M5 coût dilemme (car.)", "M5_cout_chars"),
                     ("M6 confiance /100", "M6_confiance"),
                     ("coût trivial (car.)", "cout_trivial_chars"),
                     ("M8 adaptativité (ratio)", "M8_adaptativite"),
                     ("« meilleure » (juge)", "meilleure_count")]:
        print(f"{label:<25} | " + " | ".join(f"{str(M[a][k]):>9}" for a in ARMS))
    print("\n=== TESTS DES SIGNES (M1 apparié) ===")
    print(json.dumps(S, indent=1, ensure_ascii=False))
    print("\n=== BOOTSTRAP IC95 ===")
    print(json.dumps(CI, indent=1, ensure_ascii=False))
    print("\n=== SURCONFIANCE (banc dur) ===")
    print(json.dumps(surconf, indent=1, ensure_ascii=False))
    print("\n=== M7 FIDÉLITÉ ===")
    print(json.dumps(fidelite, indent=1, ensure_ascii=False)[:600])
    print(f"\n=== M9 SUR-ENSEMBLE === conforme={M9}")
    print("\n=== CONDITIONS DE VERDICT ===")
    for k, v in V.items():
        print(f"  {'OK ' if v else 'NON'} {k}")
    if V2_cause:
        print(f"      └─ {V2_cause}")
    print("\nVERDICT:", out["verdict"])


if __name__ == "__main__":
    main()
