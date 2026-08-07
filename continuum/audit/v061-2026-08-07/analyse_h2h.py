#!/usr/bin/env python3
"""Analyse du tête-à-tête v0.6.0 (D) contre v0.6.1 (E), selon protocol.md §Phase 2.

W1 est une condition de NON-RÉGRESSION : v0.6.1 corrige des défauts, elle ne prétend pas
mieux juger. Un gain serait un bonus ; ce qu'on vérifie, c'est qu'elle ne perd rien.

Usage : python3 analyse_h2h.py <dossier_runs_E> [fidelite_v061.json]
"""
import json
import math
import os
import random
import subprocess
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
V060 = os.path.join(HERE, "..", "ab-test-v060-2026-08-07")
CRITS = ["clarte_verdict", "solidite_justification", "traitement_risque",
         "parties_prenantes", "actionnabilite"]


def sign_test(x, y):
    w = sum(1 for a, b in zip(x, y) if a > b)
    l = sum(1 for a, b in zip(x, y) if a < b)
    n = w + l
    p = sum(math.comb(n, k) for k in range(w, n + 1)) / 2 ** n if n else 1.0
    return {"victoires": w, "defaites": l, "nuls": len(x) - n, "p_unilateral": round(p, 4)}


def main():
    dir_e = sys.argv[1]
    fid_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "fidelite_v061.json")

    with open(os.path.join(HERE, "shuffle_h2h.json")) as f:
        sh = json.load(f)
    with open(os.path.join(HERE, "finals_E.json")) as f:
        fe = json.load(f)
    with open(os.path.join(V060, "runs", "finals.json")) as f:
        fd = json.load(f)

    scores, anomalies = {}, []
    for key, pos in sh.items():
        p = os.path.join(dir_e, "runs", f"judge_{key}.txt")
        if not os.path.exists(p):
            anomalies.append(f"{key} : juge manquant")
            continue
        txt = open(p).read()
        obj = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
        e = {}
        for pk, arm in pos.items():
            s = {unicodedata.normalize("NFKD", k).encode("ascii", "ignore").decode().lower(): v
                 for k, v in obj["scores"][pk].items()}
            rendus = [c for c in CRITS if c in s]
            if rendus:
                e[arm] = sum(s[c] for c in rendus) / len(rendus)
        if len(e) == 2:
            scores[key] = {"scores": e, "meilleure": pos.get(obj.get("meilleure"))}
        else:
            anomalies.append(f"{key} : {len(e)}/2 bras notés")

    ks = sorted(scores)
    m1 = {a: round(sum(scores[k]["scores"][a] for k in ks) / len(ks), 3) for a in ("D", "E")}
    best = {a: sum(1 for k in ks if scores[k]["meilleure"] == a) for a in ("D", "E")}
    x = [scores[k]["scores"]["E"] for k in ks]
    y = [scores[k]["scores"]["D"] for k in ks]
    S = {"E>D": sign_test(x, y), "D>E": sign_test(y, x)}
    random.seed(42)
    deltas = [a - b for a, b in zip(x, y)]
    boot = sorted(sum(random.choices(deltas, k=len(deltas))) / len(deltas) for _ in range(10000))
    ci = [round(boot[250], 3), round(boot[9749], 3)]

    # --- justesse ---
    def bench(p):
        return {d["id"]: d for d in json.load(open(p))["dilemmas"]}
    comp = bench(os.path.join(V060, "dilemmes_complementaires.json"))
    orig = bench(os.path.join(V060, "..", "ab-test-dilemmes-2026-08-07", "dilemmas.json"))

    def just(f, b, arm):
        s = []
        for i, d in b.items():
            if not d.get("key"):
                continue
            for r in (1, 2):
                k = f"{i}_{arm}_r{r}"
                if k in f:
                    s.append(d["key"].get(str(f[k].get("decision", "")).strip().upper()[:1], 0.0))
        return round(sum(s) / len(s), 3) if s else None

    M2 = {"comp": {"D": just(fd, comp, "D"), "E": just(fe, comp, "E")},
          "orig": {"D": just(fd, orig, "D"), "E": just(fe, orig, "E")}}

    # --- coût ---
    cout = {a: round(sum(v["output_chars"] for k, v in (fd if a == "D" else fe).items()
                         if f"_{a}_r" in k and not k.startswith("A")) /
                     len([k for k in (fd if a == "D" else fe) if f"_{a}_r" in k and not k.startswith("A")]), 1)
            for a in ("D", "E")}

    # --- M8 ---
    adapt = [r["id"] for r in json.load(open(os.path.join(V060, "adaptivite.json")))["requetes"]]
    def triv(arm, src):
        v = [src[f"{a}_{arm}_r1"]["output_chars"] for a in adapt if f"{a}_{arm}_r1" in src]
        return sum(v) / len(v) if v else None
    tA = triv("A", fd)
    tE = [len(open(os.path.join(dir_e, "runs", f"{a}_E_r1.txt")).read()) for a in adapt
          if os.path.exists(os.path.join(dir_e, "runs", f"{a}_E_r1.txt"))]
    M8 = {"D": round(triv("D", fd) / tA, 3), "E": round((sum(tE) / len(tE)) / tA, 3) if tE else None}

    fid = json.load(open(fid_path)) if os.path.exists(fid_path) else {}
    m7 = fid.get("v061", {}).get("moyenne")

    def check(script, *a):
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", script), *a],
                           capture_output=True, text=True,
                           cwd=os.path.join(HERE, "..", "..", ".."))
        return r.returncode == 0
    W0 = check("superset_check.py") and check("bloc_check.py",
              os.path.join(HERE, "bloc_v061.txt"))

    W = {
        "W0_bases_et_canal": W0,
        "W1_pas_de_regression_juges": (m1["E"] >= m1["D"] - 0.20
                                       and S["D>E"]["p_unilateral"] > 0.05),
        "W2_justesse_reparee": (M2["orig"]["E"] is not None and M2["orig"]["E"] >= 0.95
                                and M2["comp"]["E"] == 1.0),
        "W3_croyants": (m7 is not None and m7 >= 8.0),
        "W4_adaptatif": (M8["E"] is not None and M8["E"] <= 1.5),
    }
    out = {"n_juges": len(ks), "M1": m1, "meilleure": best, "tests_signes": S,
           "delta_moyen_E_moins_D": round(sum(deltas) / len(deltas), 3), "IC95": ci,
           "M2": M2, "cout_dilemme": cout, "M8": M8, "M7_v061": m7,
           "anomalies": anomalies, "conditions": W,
           "verdict": ("RÉUSSIE — v0.6.1 valide les 5 conditions" if all(W.values())
                       else "ÉCHEC — " + ", ".join(k for k, v in W.items() if not v))}
    with open(os.path.join(HERE, "results_h2h.json"), "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print(f"=== TÊTE-À-TÊTE v0.6.0 (D) contre v0.6.1 (E) — {len(ks)} juges ===")
    print(f"M1            D = {m1['D']:<7} E = {m1['E']}")
    print(f"« meilleure » D = {best['D']:<7} E = {best['E']}")
    print(f"E > D : {S['E>D']}")
    print(f"D > E : {S['D>E']}")
    print(f"Δ (E−D) = {out['delta_moyen_E_moins_D']}  IC95 {ci}")
    print(f"\nJustesse — complémentaire D={M2['comp']['D']} E={M2['comp']['E']}"
          f" · origine D={M2['orig']['D']} E={M2['orig']['E']}")
    print(f"Coût dilemme  D = {cout['D']}  E = {cout['E']}")
    print(f"M8            D = {M8['D']}  E = {M8['E']}")
    print(f"M7 v0.6.1     {m7}")
    print("\n=== CONDITIONS ===")
    for k, v in W.items():
        print(f"  {'OK ' if v else 'NON'} {k}")
    print("\nVERDICT:", out["verdict"])
    if anomalies:
        print("anomalies :", anomalies)


if __name__ == "__main__":
    main()
