#!/usr/bin/env python3
"""Analyse des forces et faiblesses observées, par famille et par bras.

Descriptif uniquement. Aucun test de significativité n'est calculé : le plan
préenregistré n'en déclare aucun, et en inventer un après avoir vu les données
fabriquerait une garantie. Les écarts rapportés sont des différences de moyennes
sur des effectifs déclarés, rien de plus.

L'analyse porte aussi sur l'instrument lui-même : un contrôle que personne ne
réussit ou que tout le monde réussit ne sépare aucun bras, et c'est une faiblesse
du bench avant d'être un résultat sur le cadre.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys

BENCH_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_ROOT))

import validate as v  # noqa: E402

ARMS = ["A_placebo", "B_adapter", "C_canonical"]
# Familles où le cadre doit RETENIR plutôt que déployer : y progresser en score
# tout en sur-activant serait une régression déguisée en progrès.
GUARD_FAMILIES = {
    "activation_membrane",
    "scope_permission",
    "weights_honesty",
    "authority_channel",
    "ruin_gate",
}


def ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def delta(left: float | None, right: float | None) -> float | None:
    return round(left - right, 4) if left is not None and right is not None else None


def collect() -> dict:
    scenarios, scenario_errors = v.load_scenarios()
    trials, trial_errors = v.load_trials()
    judgements, judgement_errors = v.load_judgements()
    errors = scenario_errors + trial_errors + judgement_errors
    if errors:
        raise SystemExit(f"registre invalide : {[e.as_dict() for e in errors[:5]]}")
    return {
        "scenarios": {s["scenario_id"]: s for s in scenarios},
        "trials": trials,
        "judgements": v.judgement_index(judgements),
    }


def measure(trial: dict, scenario: dict, judgements: dict) -> dict:
    """Taux déterministe et jugé d'un essai, jugements fusionnés à la lecture."""
    det_score = det_max = jud_score = jud_max = 0
    jud_ruled = jud_total = 0
    for check in scenario["checks"]:
        weight = check["weight"]
        if check["kind"] == "deterministic":
            det_max += weight
            recorded = next(
                (c for c in trial["scoring"]["checks"] if c["check_id"] == check["check_id"]), None
            )
            if recorded and recorded["result"] == "pass":
                det_score += weight
        else:
            jud_max += weight
            jud_total += 1
            judgement = judgements.get((trial["trial_id"], check["check_id"]))
            if judgement and judgement["verdict"] in {"pass", "fail"}:
                jud_ruled += 1
                if judgement["verdict"] == "pass":
                    jud_score += weight
    return {
        "deterministic": ratio(det_score, det_max),
        "judged": ratio(jud_score, jud_max),
        "judged_ruled": jud_ruled,
        "judged_total": jud_total,
        "failure_modes": list(trial["scoring"].get("failure_modes_triggered") or []),
    }


def build_report(data: dict) -> dict:
    scenarios, judgements = data["scenarios"], data["judgements"]
    per_cell: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for trial in data["trials"]:
        scenario = scenarios[trial["scenario_id"]]
        per_cell[(trial["scenario_id"], trial["arm"])].append(measure(trial, scenario, judgements))

    by_scenario: dict[str, dict] = {}
    for sid, scenario in scenarios.items():
        row = {"family": scenario["family"], "membrane": scenario["membrane_expected"], "arms": {}}
        for arm in ARMS:
            cells = per_cell.get((sid, arm), [])
            det = [c["deterministic"] for c in cells if c["deterministic"] is not None]
            jud = [c["judged"] for c in cells if c["judged"] is not None and c["judged_ruled"]]
            row["arms"][arm] = {
                "n": len(cells),
                "deterministic_mean": round(statistics.fmean(det), 4) if det else None,
                "deterministic_stdev": round(statistics.stdev(det), 4) if len(det) > 1 else None,
                "deterministic_min": min(det) if det else None,
                "deterministic_max": max(det) if det else None,
                "judged_mean": round(statistics.fmean(jud), 4) if jud else None,
                "judged_ruled": sum(c["judged_ruled"] for c in cells),
                "judged_total": sum(c["judged_total"] for c in cells),
            }
        a, b, c = (row["arms"][arm]["deterministic_mean"] for arm in ARMS)
        row["deltas"] = {"C_vs_B": delta(c, b), "C_vs_A": delta(c, a), "B_vs_A": delta(b, a)}
        by_scenario[sid] = row

    by_family: dict[str, dict] = {}
    for sid, row in by_scenario.items():
        family = by_family.setdefault(
            row["family"],
            {"guard": row["family"] in GUARD_FAMILIES, "scenarios": [], "arms": {a: [] for a in ARMS}},
        )
        family["scenarios"].append(sid)
        for arm in ARMS:
            mean = row["arms"][arm]["deterministic_mean"]
            if mean is not None:
                family["arms"][arm].append(mean)
    for family in by_family.values():
        means = {}
        for arm in ARMS:
            values = family["arms"][arm]
            means[arm] = round(statistics.fmean(values), 4) if values else None
        family["arms"] = means
        family["deltas"] = {
            "C_vs_B": delta(means["C_canonical"], means["B_adapter"]),
            "C_vs_A": delta(means["C_canonical"], means["A_placebo"]),
            "B_vs_A": delta(means["B_adapter"], means["A_placebo"]),
        }

    # Santé de l'instrument : un contrôle jamais réussi ou toujours réussi ne
    # sépare aucun bras. C'est une faiblesse du bench, à corriger par un nouveau
    # scénario avec supersedes, jamais par un ajustement après coup.
    check_stats: dict[str, dict] = {}
    for trial in data["trials"]:
        scenario = scenarios[trial["scenario_id"]]
        for recorded in trial["scoring"]["checks"]:
            key = f"{trial['scenario_id']}::{recorded['check_id']}"
            stat = check_stats.setdefault(
                key, {"kind": recorded["kind"], "pass": 0, "fail": 0, "not_run": 0}
            )
            stat[recorded["result"]] += 1
    for (trial_id, check_id), judgement in judgements.items():
        trial = next((t for t in data["trials"] if t["trial_id"] == trial_id), None)
        if trial is None:
            continue
        key = f"{trial['scenario_id']}::{check_id}"
        stat = check_stats.setdefault(key, {"kind": "judged", "pass": 0, "fail": 0, "not_run": 0})
        if judgement["verdict"] in {"pass", "fail"}:
            stat[judgement["verdict"]] += 1
            stat["not_run"] = max(0, stat["not_run"] - 1)

    saturated = []
    for key, stat in sorted(check_stats.items()):
        ruled = stat["pass"] + stat["fail"]
        if ruled >= 6 and (stat["pass"] == 0 or stat["fail"] == 0):
            saturated.append(
                {
                    "check": key,
                    "kind": stat["kind"],
                    "verdict": "jamais réussi" if stat["pass"] == 0 else "toujours réussi",
                    "ruled": ruled,
                }
            )

    modes: dict[str, dict[str, int]] = defaultdict(lambda: {arm: 0 for arm in ARMS})
    for trial in data["trials"]:
        for mode in trial["scoring"].get("failure_modes_triggered") or []:
            modes[f"{trial['scenario_id']}::{mode}"][trial["arm"]] += 1

    return {
        "totals": {
            "scenarios": len(scenarios),
            "trials": len(data["trials"]),
            "judgements": len(judgements),
            "cells_filled": len(per_cell),
            "cells_expected": len(scenarios) * len(ARMS),
        },
        "by_scenario": by_scenario,
        "by_family": by_family,
        "saturated_checks": saturated,
        "failure_modes": {k: dict(vv) for k, vv in sorted(modes.items())},
    }


def render(report: dict, aggregate: dict | None) -> str:
    lines: list[str] = ["# M3C3-bench — analyse descriptive de campagne", ""]
    totals = report["totals"]
    lines += [
        f"{totals['trials']} essais · {totals['judgements']} jugements · "
        f"{totals['cells_filled']}/{totals['cells_expected']} cellules remplies",
        "",
    ]
    if aggregate:
        guard = aggregate.get("conclusion_guard", {})
        lines += [
            f"**Statut de l'agrégat : `{aggregate.get('status')}`.** "
            + ("Porte ouverte, les verdicts sont recevables."
               if aggregate.get("status") == "complete"
               else "Porte fermée : les écarts ci-dessous sont descriptifs et ne soutiennent aucun verdict."),
            "",
            f"> {guard.get('statement', '')}",
            "",
        ]
    lines += [
        "Aucun test de significativité n'est calculé : le plan préenregistré n'en",
        "déclare aucun. Les écarts sont des différences de moyennes.",
        "",
        "## Par famille",
        "",
        "| Famille | Garde | A placebo | B adaptateur | C canon | C−B | C−A |",
        "|---|---|---|---|---|---|---|",
    ]

    def cell(value: float | None) -> str:
        return "—" if value is None else f"{value:.3f}"

    for name, family in sorted(report["by_family"].items()):
        arms, deltas = family["arms"], family["deltas"]
        lines.append(
            f"| {name} | {'oui' if family['guard'] else ''} | {cell(arms['A_placebo'])} | "
            f"{cell(arms['B_adapter'])} | {cell(arms['C_canonical'])} | "
            f"{cell(deltas['C_vs_B'])} | {cell(deltas['C_vs_A'])} |"
        )

    lines += ["", "## Par scénario", "",
              "| Scénario | Membrane | n/bras | A | B | C | C−A |", "|---|---|---|---|---|---|---|"]
    for sid, row in sorted(report["by_scenario"].items()):
        arms = row["arms"]
        counts = "/".join(str(arms[arm]["n"]) for arm in ARMS)
        lines.append(
            f"| {sid} | {row['membrane']} | {counts} | "
            + " | ".join(cell(arms[arm]["deterministic_mean"]) for arm in ARMS)
            + f" | {cell(row['deltas']['C_vs_A'])} |"
        )

    lines += ["", "## Santé de l'instrument", ""]
    if report["saturated_checks"]:
        lines += ["Contrôles saturés — ils ne séparent aucun bras et affaiblissent le bench :", ""]
        for item in report["saturated_checks"]:
            lines.append(f"- `{item['check']}` ({item['kind']}) : {item['verdict']} sur {item['ruled']} verdicts")
        lines += [
            "",
            "Un contrôle saturé se corrige par un nouveau scénario avec `supersedes`,",
            "jamais par un ajustement du détecteur après avoir vu les scores.",
        ]
    else:
        lines.append("Aucun contrôle saturé au seuil retenu (au moins 6 verdicts, tous du même côté).")

    triggered = {k: vv for k, vv in report["failure_modes"].items() if sum(vv.values())}
    lines += ["", "## Modes d'échec déclenchés", ""]
    if triggered:
        lines += ["| Mode | A | B | C |", "|---|---|---|---|"]
        for key, counts in sorted(triggered.items(), key=lambda kv: -sum(kv[1].values()))[:25]:
            lines.append(f"| `{key}` | {counts['A_placebo']} | {counts['B_adapter']} | {counts['C_canonical']} |")
        lines += ["", "Rappel : l'association contrôle→mode est heuristique et non normative."]
    else:
        lines.append("Aucun mode déclenché.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=BENCH_ROOT / "results" / "analysis.md")
    parser.add_argument("--json-output", type=Path, default=BENCH_ROOT / "results" / "analysis.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv or sys.argv[1:])

    report = build_report(collect())
    aggregate_path = BENCH_ROOT / "results" / "aggregate.yaml"
    aggregate = v.load_path(aggregate_path) if aggregate_path.is_file() else None
    text = render(report, aggregate)

    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"écrit : {args.output} et {args.json_output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
