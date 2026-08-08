#!/usr/bin/env python3
"""Mesure l'accord inter-juges sur un échantillon déterministe.

Un second juge — un modèle différent — rejuge à l'aveugle une partie des
contrôles déjà tranchés par le juge principal, et l'accord observé est publié
comme rapport de FIABILITÉ DE L'INSTRUMENT. Rien n'est écrit dans judgements/ :
les verdicts de campagne restent ceux du juge principal, et ce rapport dit
seulement à quel point un verdict unique mérite confiance.

L'échantillon est déterministe — les réplicats r1 et r3 de chaque cellule —
plutôt qu'aléatoire : rejouable à l'identique, et non choisi après coup.

Le kappa de Cohen est une statistique descriptive de fiabilité, pas un test de
significativité : le plan préenregistré n'en déclare aucun et celui-ci n'en
introduit pas.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sys

import yaml

BENCH_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_ROOT))

import judge  # noqa: E402
import validate as v  # noqa: E402

REPORT_PATH = BENCH_ROOT / "results" / "judge-agreement.yaml"
SAMPLE_MARKERS = ("-r1-", "-r3-")
DEFAULT_SECOND_JUDGE = "claude-haiku-4-5"


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Kappa sur les verdicts pass/fail (les not_run du second juge sont exclus)."""
    if not pairs:
        return None
    labels = ("pass", "fail")
    total = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / total
    expected = 0.0
    for label in labels:
        pa = sum(1 for a, _ in pairs if a == label) / total
        pb = sum(1 for _, b in pairs if b == label) / total
        expected += pa * pb
    if expected >= 1.0:
        return None
    return round((observed - expected) / (1 - expected), 4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--second-judge-model", default=DEFAULT_SECOND_JUDGE)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv or sys.argv[1:])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    scenarios, scenario_errors = v.load_scenarios()
    trials, trial_errors = v.load_trials()
    judgements, judgement_errors = v.load_judgements()
    if scenario_errors or trial_errors or judgement_errors:
        print("registre invalide — mesure refusée", file=sys.stderr)
        return 1
    by_id = {scenario["scenario_id"]: scenario for scenario in scenarios}
    primary = v.judgement_index(judgements)

    work = []
    for trial in sorted(trials, key=lambda item: item["trial_id"]):
        if not any(marker in trial["trial_id"] for marker in SAMPLE_MARKERS):
            continue
        scenario = by_id[trial["scenario_id"]]
        for check in scenario["checks"]:
            if check["kind"] != "judged":
                continue
            first = primary.get((trial["trial_id"], check["check_id"]))
            if first is None or first["verdict"] not in ("pass", "fail"):
                continue
            work.append((trial, scenario, check, first["verdict"]))

    print(f"{len(work)} contrôle(s) échantillonné(s) · second juge {args.second_judge_model} · aveugle")

    workdir = Path("/tmp/judge-agreement-work")
    workdir.mkdir(parents=True, exist_ok=True)

    def rejudge(item):
        trial, scenario, check, first_verdict = item
        prompt = judge.build_prompt(scenario["task"]["prompt"], trial["response"]["text"], check)
        verdict, _ = judge.call_judge(prompt, args.second_judge_model, workdir)
        return trial, check, first_verdict, verdict

    results = list(ThreadPoolExecutor(max_workers=args.workers).map(rejudge, work))

    rows = []
    pairs = []
    unruled = 0
    for trial, check, first_verdict, second_verdict in results:
        rows.append(
            {
                "trial_id": trial["trial_id"],
                "check_id": check["check_id"],
                "primary": first_verdict,
                "second": second_verdict,
            }
        )
        if second_verdict in ("pass", "fail"):
            pairs.append((first_verdict, second_verdict))
        else:
            unruled += 1

    agreement = round(sum(1 for a, b in pairs if a == b) / len(pairs), 4) if pairs else None
    report = {
        "schema_version": 1,
        "kind": "m3c3_bench_judge_agreement",
        "measured_at": now,
        "primary_judge": "claude-opus-5",
        "second_judge": args.second_judge_model,
        "sampling": (
            "déterministe : tous les contrôles jugés des essais de réplicat r1 et r3 "
            "dont le juge principal a rendu un verdict pass/fail"
        ),
        "sampled": len(rows),
        "ruled_by_both": len(pairs),
        "second_judge_unruled": unruled,
        "percent_agreement": agreement,
        "cohen_kappa": cohen_kappa(pairs),
        "confusion": {
            "both_pass": sum(1 for a, b in pairs if a == b == "pass"),
            "both_fail": sum(1 for a, b in pairs if a == b == "fail"),
            "primary_pass_second_fail": sum(1 for a, b in pairs if a == "pass" and b == "fail"),
            "primary_fail_second_pass": sum(1 for a, b in pairs if a == "fail" and b == "pass"),
        },
        "limitations": [
            "Mesure de fiabilité, pas de vérité : deux juges d'accord peuvent se tromper ensemble, "
            "et le second juge est un modèle plus petit dont les désaccords mélangent bruit et capacité.",
            "Le kappa de Cohen est descriptif ; aucun test de significativité n'est calculé.",
            "Les verdicts de campagne restent ceux du juge principal : ce rapport n'en modifie aucun.",
            "Échantillon déterministe (r1, r3), non aléatoire : rejouable, mais pas garanti représentatif.",
        ],
        "rows": rows,
    }

    if args.write:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            yaml.safe_dump(report, allow_unicode=True, sort_keys=False, width=110),
            encoding="utf-8",
        )
        print(f"écrit : {REPORT_PATH}")
    print(
        f"accord : {agreement} · kappa : {report['cohen_kappa']} · "
        f"tranchés par les deux : {len(pairs)}/{len(rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
