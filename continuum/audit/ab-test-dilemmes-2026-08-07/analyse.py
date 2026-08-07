#!/usr/bin/env python3
"""Analyse pré-enregistrée du test A/B/C (voir protocol.md §3-§4). Pur Python, graine 42."""
import json, math, random, sys

XP = sys.argv[1] if len(sys.argv) > 1 else "/tmp/xp"
data = json.load(open("dilemmas.json"))
shuffle = json.load(open("shuffle.json"))
finals = json.load(open(f"{XP}/finals.json"))
DIL = {d["id"]: d for d in data["dilemmas"]}
DIDS = list(DIL); ARMS = "ABC"; CRITS = ["clarte_verdict","solidite_justification","traitement_risque","parties_prenantes","actionnabilite"]

# --- juges ---
judge = {}   # (did, rep) -> {arm: mean_score}, best_arm, ranking(arms)
for key, pos in shuffle.items():
    did, rep = key.split("_r"); rep = int(rep)
    txt = open(f"{XP}/runs/judge_{did}_r{rep}.txt").read()
    start = txt.find("{"); obj = json.loads(txt[start:txt.rfind("}")+1])
    entry = {"scores": {}, "detail": {}}
    for r in ("R1","R2","R3"):
        arm = pos[r]; s = obj["scores"][r]
        entry["scores"][arm] = sum(s[c] for c in CRITS) / len(CRITS)
        entry["detail"][arm] = s
    entry["best"] = pos[obj["meilleure"]]
    entry["ranking"] = [pos[r] for r in obj["classement"]]
    judge[(did, rep)] = entry

# --- métriques par bras ---
def runs_of(arm): return [(d, r) for d in DIDS for r in (1,2)]
M = {a: {} for a in ARMS}
for a in ARMS:
    pairs = runs_of(a)
    M[a]["M1_qualite_juge"] = sum(judge[p]["scores"][a] for p in pairs) / len(pairs)
    keyed = [d for d in DIDS if DIL[d]["key"]]
    obj_scores = []
    for d in keyed:
        for r in (1,2):
            dec = finals[f"{d}_{a}_r{r}"]["decision"].strip().upper()[:1]
            obj_scores.append(DIL[d]["key"].get(dec, 0.0))
    M[a]["M2_justesse_objective"] = sum(obj_scores) / len(obj_scores)
    M[a]["M3_consistance"] = sum(1 for d in DIDS
        if finals[f"{d}_{a}_r1"]["decision"].strip().upper()[:1] == finals[f"{d}_{a}_r2"]["decision"].strip().upper()[:1]) / len(DIDS)
    M[a]["M4_facilite"] = sum(finals[f"{d}_{a}_r{r}"]["ease_1_10"] for d in DIDS for r in (1,2)) / 16
    M[a]["M5_cout_chars"] = sum(finals[f"{d}_{a}_r{r}"]["output_chars"] for d in DIDS for r in (1,2)) / 16
    M[a]["M6_confiance"] = sum(finals[f"{d}_{a}_r{r}"]["confidence_0_100"] for d in DIDS for r in (1,2)) / 16
    M[a]["meilleure_count"] = sum(1 for p in runs_of(a) if judge[p]["best"] == a)

min_cost = min(M[a]["M5_cout_chars"] for a in ARMS)
for a in ARMS:
    M[a]["composite"] = round(
        M[a]["M1_qualite_juge"] * 10 * 0.35
        + M[a]["M2_justesse_objective"] * 100 * 0.30
        + M[a]["M3_consistance"] * 100 * 0.15
        + M[a]["M4_facilite"] * 10 * 0.10
        + (min_cost / M[a]["M5_cout_chars"]) * 100 * 0.10, 2)

# --- test des signes exact ---
def sign_test(x, y):  # x,y listes appariées ; H1: x > y
    wins = sum(1 for a, b in zip(x, y) if a > b); losses = sum(1 for a, b in zip(x, y) if a < b)
    n = wins + losses
    p = sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n if n else 1.0
    return {"wins": wins, "losses": losses, "ties": len(x) - n, "p_unilateral": round(p, 4)}

pairs16 = [(d, r) for d in DIDS for r in (1, 2)]
S = {}
for hi, lo in (("B","A"), ("B","C"), ("C","A")):
    S[f"{hi}>{lo}"] = sign_test([judge[p]["scores"][hi] for p in pairs16],
                                [judge[p]["scores"][lo] for p in pairs16])

# --- bootstrap IC95 des deltas M1 (apparié, graine 42) ---
random.seed(42)
def boot_ci(deltas, n=10000):
    means = sorted(sum(random.choices(deltas, k=len(deltas))) / len(deltas) for _ in range(n))
    return round(means[int(0.025*n)], 3), round(means[int(0.975*n)-1], 3)
CI = {}
for hi, lo in (("B","A"), ("B","C"), ("C","A")):
    deltas = [judge[p]["scores"][hi] - judge[p]["scores"][lo] for p in pairs16]
    CI[f"M1 {hi}-{lo}"] = {"delta_moyen": round(sum(deltas)/len(deltas), 3), "IC95": boot_ci(deltas)}

# --- exploratoire : par régime ---
REG = data["meta"]["regimes"]
per_regime = {}
for reg, dids in REG.items():
    pr = [(d, r) for d in dids for r in (1, 2)]
    per_regime[reg] = {a: round(sum(judge[p]["scores"][a] for p in pr) / len(pr), 3) for a in ARMS}

# --- exploratoire : surconfiance (confiance des réponses objectivement fausses, clé < 1) ---
overconf = {}
for a in ARMS:
    wrong = [finals[f"{d}_{a}_r{r}"]["confidence_0_100"] for d in DIDS if DIL[d]["key"] for r in (1,2)
             if DIL[d]["key"].get(finals[f"{d}_{a}_r{r}"]["decision"].strip().upper()[:1], 0) < 1.0]
    overconf[a] = {"n_reponses_sous_optimales": len(wrong),
                   "confiance_moyenne": round(sum(wrong)/len(wrong), 1) if wrong else None}

# --- décisions brutes (pour le rapport) ---
decisions = {f"{d}_{a}": [finals[f"{d}_{a}_r1"]["decision"], finals[f"{d}_{a}_r2"]["decision"]] for d in DIDS for a in ARMS}

# --- verdict pré-enregistré ---
dBA = M["B"]["composite"] - M["A"]["composite"]; dBC = M["B"]["composite"] - M["C"]["composite"]
if dBA >= 3 and dBC >= 3: verdict = "OUI — le framework facilite, au-delà de l'effet structure"
elif dBA >= 3 and abs(dBC) < 3: verdict = "PARTIEL — structurer aide, M3C3 n'ajoute rien de mesurable vs checklist générique"
elif abs(dBA) < 3: verdict = "NON MESURABLE — pas d'effet net du framework"
else: verdict = "NON — le framework coûte plus qu'il ne rapporte"

out = {"metriques": M, "tests_signes": S, "bootstrap_IC95": CI, "par_regime_M1": per_regime,
       "surconfiance": overconf, "decisions": decisions,
       "delta_composite": {"B-A": round(dBA, 2), "B-C": round(dBC, 2), "C-A": round(M["C"]["composite"]-M["A"]["composite"], 2)},
       "verdict": verdict}
json.dump(out, open("results.json", "w"), indent=1, ensure_ascii=False)

print("=== MÉTRIQUES PAR BRAS ===")
hdr = ["", "A (nu)", "B (M3C3)", "C (placebo)"]
rows = [("M1 qualité juge /10", "M1_qualite_juge"), ("M2 justesse obj. /1", "M2_justesse_objective"),
        ("M3 consistance /1", "M3_consistance"), ("M4 facilité /10", "M4_facilite"),
        ("M5 coût (chars)", "M5_cout_chars"), ("M6 confiance /100", "M6_confiance"),
        ("« meilleure » (juge) /16", "meilleure_count"), ("COMPOSITE /100", "composite")]
print(" | ".join(hdr))
for label, k in rows:
    print(f"{label} | " + " | ".join(str(round(M[a][k], 3)) for a in ARMS))
print("\n=== TESTS DES SIGNES (M1 apparié) ==="); print(json.dumps(S, indent=1))
print("\n=== BOOTSTRAP ==="); print(json.dumps(CI, indent=1))
print("\n=== PAR RÉGIME (M1) ==="); print(json.dumps(per_regime, indent=1))
print("\n=== SURCONFIANCE ==="); print(json.dumps(overconf, indent=1))
print("\nΔ composite B-A =", round(dBA,2), "| B-C =", round(dBC,2))
print("VERDICT:", verdict)
