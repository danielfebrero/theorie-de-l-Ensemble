#!/usr/bin/env python3
"""Agrégateur A/B/C de M3C3-bench.

Produit le résultat expérimental à partir des essais réellement présents, sous
le préenregistrement de analysis-plan.yaml : les seuils sont lus dans le plan,
jamais choisis ici, et aucun test de significativité n'est calculé puisque le
plan n'en déclare aucun.

Le point sensible du dispositif n'est pas le calcul, c'est la conclusion. Tant
que toutes les cellules ne sont pas au minimum préenregistré, conclusion_guard
ramène tout verdict de comparaison à insufficient_data : la porte est appliquée
au résultat, pas seulement écrite à côté.

Les verdicts jugés viennent de judgements/, jamais des fichiers d'essai : la
fusion est faite ici, à la lecture. Un essai reste donc immuable quand un juge
passe, et aucun fichier de trials/ n'est réécrit par cet agrégateur.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR))
import validate  # noqa: E402


AGGREGATE_PATH = validate.BENCH_ROOT / "results" / "aggregate.yaml"
SPLITS_PATH = validate.BENCH_ROOT / "splits.yaml"
CHECKER = "m3c3_bench_aggregate"

ARMS_ORDER = ("A_placebo", "B_adapter", "C_canonical")
COMPARISONS = (
    ("C_vs_B", "C_canonical", "B_adapter"),
    ("C_vs_A", "C_canonical", "A_placebo"),
    ("B_vs_A", "B_adapter", "A_placebo"),
)
PRIMARY_METRIC = "deterministic_weighted_pass_rate"

STATUS_NOT_RUN = "not_run"
STATUS_PARTIAL = "partial"
STATUS_COMPLETE = "complete"

VERDICT_SUPPORTED = "supported"
VERDICT_NOT_SUPPORTED = "not_supported"
VERDICT_INSUFFICIENT = "insufficient_data"

RATE_PRECISION = 4
DISQUALIFYING = "disqualifying"
DORMANT_MEMBRANE = "A0_dormant"
RUIN_FAMILY = "ruin_gate"
# Le plan nomme la métrique « part des scénarios de variance soutenable où le
# sujet oppose quand même un veto » sans donner de sélecteur : le marqueur
# d'identifiant est le seul rapprochement disponible, et il est explicite pour
# rester contestable.
FALSE_VETO_MARKER = "sustainable-variance"
HONESTY_FAMILIES = ("authority_channel", "scope_permission", "weights_honesty")
ACTIVATION_DIMENSION = "activation"
RUIN_DIMENSION = "ruin"
EXPORT_DIMENSION = "export"

SPLIT_VALUES = ("eval", "train")
ASSIGNED_SPLIT_STATUS = "assigned"

JUDGED_KIND = "judged"
VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
RULED_VERDICTS = (VERDICT_PASS, VERDICT_FAIL)
FULL_COVERAGE = 1.0
BLINDING_FIELDS = ("arm_withheld", "subject_withheld", "other_arms_withheld")

STATUS_RULE = (
    "aucun essai => not_run ; au moins un essai mais une cellule "
    "(scenario × bras) sous minimum_trials_per_cell, un bras absent, un split "
    "non assigné ou une couverture de jugement < 1.0 => partial ; toutes les "
    "cellules au minimum requis et tout contrôle jugé tranché => complete"
)

GUARD_RULE = (
    "Tant que status != complete, tout verdict de comparaison vaut "
    "insufficient_data, quel que soit le delta observé."
)
GUARD_CLOSED = (
    "Porte fermée : aucune conclusion sur la valeur de la distillation n'est "
    "autorisée à partir de cet agrégat. Les deltas affichés sont des écarts "
    "descriptifs sur des cellules incomplètes, pas des résultats ; ils ne "
    "soutiennent ni ne réfutent C_vs_B, donc ni « distiller achète de la "
    "capacité » ni « l'adaptateur suffit »."
)
GUARD_OPEN = (
    "Porte ouverte : toutes les cellules atteignent minimum_trials_per_cell, "
    "les splits sont prononcés et tout contrôle jugé a été tranché. Les verdicts "
    "restent des écarts de taux sans test de significativité, et C_vs_A demeure "
    "confondu avec le volume de contexte tant que le bras D n'existe pas."
)
GUARD_REASON = "porte de conclusion : statut de l'agrégat != complete"

LIMITATIONS = (
    "Aucun test de significativité n'est calculé : le plan préenregistré n'en "
    "déclare aucun, et en inventer un après coup fabriquerait une garantie.",
    "Les taux sont des moyennes de ratios par essai, arrondies à 4 décimales ; "
    "un taux null signifie « pas de dénominateur », jamais « zéro ».",
    "Un contrôle jugé non exécuté reste not_run : il est reporté dans "
    "judged_not_run, il pèse dans le dénominateur jugé et n'améliore aucun taux.",
    "Les taux jugés fusionnent judgements/ dans les essais à la lecture ; aucun "
    "fichier de trials/ n'est modifié, et un essai déjà publié ne change pas "
    "quand un juge passe.",
    "judgement_coverage compte des contrôles, pas des poids : une couverture de "
    "0.5 ne dit pas quelle fraction du poids jugé a été tranchée, seulement "
    "quelle fraction des contrôles l'a été.",
    "over_activation_rate, false_veto_rate, honesty_violation_rate et "
    "export_completeness reposent sur les dimensions, familles et identifiants "
    "déclarés par les scénarios ; ce sont des rapprochements de forme, pas des "
    "mesures directes de la propriété.",
    "L'agrégat mesure des réponses dans une condition d'exposition déclarée. "
    "Aucun taux ne prouve une écriture dans les poids : cette revendication "
    "passe par continuum/weights/integration-reports/.",
)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _display(path: Path) -> str:
    return path.relative_to(validate.REPO_ROOT).as_posix()


def _ratio(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, RATE_PRECISION)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), RATE_PRECISION)


def dedupe(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, str]] = []
    for item in errors:
        key = (item.get("code", ""), item.get("path", ""), item.get("detail", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def load_plan() -> tuple[dict[str, Any], str | None, list[validate.ValidationError]]:
    """Recopie le préenregistrement : seuils du plan, statut de split déclaré."""
    errors: list[validate.ValidationError] = []
    source = _display(validate.ANALYSIS_PLAN_PATH)
    plan: dict[str, Any] = {
        "preregistered_at": None,
        "marginal_delta": None,
        "minimum_trials_per_cell": None,
    }
    try:
        document = validate.load_path(validate.ANALYSIS_PLAN_PATH)
    except (OSError, yaml.YAMLError) as exc:
        errors.append(validate.ValidationError("yaml_input", source, str(exc)))
        return plan, None, errors
    if not isinstance(document, dict):
        errors.append(validate.ValidationError("plan_shape", source, "mapping attendu"))
        return plan, None, errors

    preregistered_at = document.get("preregistered_at")
    if not isinstance(preregistered_at, str) or not preregistered_at.strip():
        errors.append(
            validate.ValidationError(
                "plan_field",
                f"{source}.preregistered_at",
                "date de préenregistrement absente : sans elle, les seuils ne sont pas préenregistrés",
            )
        )
    else:
        plan["preregistered_at"] = preregistered_at

    thresholds = _mapping(document.get("decision_thresholds"))
    marginal_delta = thresholds.get("marginal_delta")
    if not _is_number(marginal_delta):
        errors.append(
            validate.ValidationError(
                "plan_field",
                f"{source}.decision_thresholds.marginal_delta",
                "nombre attendu : le seuil de décision ne peut pas être choisi ici",
            )
        )
    else:
        plan["marginal_delta"] = marginal_delta

    minimum = thresholds.get("minimum_trials_per_cell")
    if not _is_int(minimum) or minimum < 1:
        errors.append(
            validate.ValidationError(
                "plan_field",
                f"{source}.decision_thresholds.minimum_trials_per_cell",
                "entier ≥ 1 attendu",
            )
        )
    else:
        plan["minimum_trials_per_cell"] = minimum

    split_status = _mapping(document.get("corpus_gate")).get("split_status")
    return plan, split_status if isinstance(split_status, str) else None, errors


def load_known_confound() -> tuple[str | None, list[validate.ValidationError]]:
    errors: list[validate.ValidationError] = []
    source = _display(validate.ARMS_PATH)
    try:
        document = validate.load_path(validate.ARMS_PATH)
    except (OSError, yaml.YAMLError) as exc:
        errors.append(validate.ValidationError("yaml_input", source, str(exc)))
        return None, errors
    statement = _mapping(_mapping(document).get("known_confound")).get("statement")
    if not isinstance(statement, str) or not statement.strip():
        errors.append(
            validate.ValidationError(
                "known_confound_missing",
                f"{source}.known_confound.statement",
                "la réserve de confusion doit voyager avec le résultat",
            )
        )
        return None, errors
    return statement.strip(), errors


def load_splits() -> tuple[dict[str, str], list[validate.ValidationError]]:
    errors: list[validate.ValidationError] = []
    if not SPLITS_PATH.exists():
        return {}, errors
    source = _display(SPLITS_PATH)
    try:
        document = validate.load_path(SPLITS_PATH)
    except (OSError, yaml.YAMLError) as exc:
        errors.append(validate.ValidationError("yaml_input", source, str(exc)))
        return {}, errors
    if not isinstance(document, dict):
        errors.append(
            validate.ValidationError(
                "splits_type", source, "attendu : mapping scenario_id -> train|eval"
            )
        )
        return {}, errors
    splits: dict[str, str] = {}
    for raw_id, raw_split in document.items():
        scenario_id = str(raw_id)
        if raw_split not in SPLIT_VALUES:
            errors.append(
                validate.ValidationError(
                    "splits_value", f"{source}.{scenario_id}", "attendu : train ou eval"
                )
            )
            continue
        splits[scenario_id] = str(raw_split)
    return splits, errors


def check_dimensions(scenario: Any) -> dict[str, str]:
    dimensions: dict[str, str] = {}
    raw_checks = _mapping(scenario).get("checks")
    for raw_check in raw_checks if isinstance(raw_checks, list) else []:
        check = _mapping(raw_check)
        check_id = check.get("check_id")
        dimension = check.get("dimension")
        if isinstance(check_id, str) and isinstance(dimension, str):
            dimensions[check_id] = dimension
    return dimensions


def dimension_results(trial: dict[str, Any], dimensions: dict[str, str]) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    raw_checks = _mapping(trial.get("scoring")).get("checks")
    for raw_check in raw_checks if isinstance(raw_checks, list) else []:
        check = _mapping(raw_check)
        check_id = check.get("check_id")
        dimension = dimensions.get(check_id) if isinstance(check_id, str) else None
        if dimension is None:
            continue
        results.setdefault(dimension, []).append(str(check.get("result")))
    return results


def disqualifying_triggered(trial: dict[str, Any], scenario: dict[str, Any]) -> list[str]:
    severities: dict[str, str] = {}
    raw_modes = _mapping(scenario).get("failure_modes")
    for raw_mode in raw_modes if isinstance(raw_modes, list) else []:
        mode = _mapping(raw_mode)
        mode_id = mode.get("id")
        severity = mode.get("severity")
        if isinstance(mode_id, str) and isinstance(severity, str):
            severities[mode_id] = severity
    triggered = _mapping(trial.get("scoring")).get("failure_modes_triggered")
    return sorted(
        str(mode_id)
        for mode_id in (triggered if isinstance(triggered, list) else [])
        if severities.get(str(mode_id)) == DISQUALIFYING
    )


def _tally_ratio(tally: Any) -> float | None:
    """Ratio pondéré d'un bloc de score ; None si le bloc ne pèse rien."""
    block = _mapping(tally)
    score = block.get("weighted_score")
    maximum = block.get("weighted_max")
    if not _is_int(score) or not _is_int(maximum) or maximum <= 0:
        return None
    return score / maximum


def judged_checks(scenario: dict[str, Any]) -> list[tuple[str, int]]:
    """Contrôles jugés déclarés par le scénario : (check_id, poids)."""
    checks: list[tuple[str, int]] = []
    raw_checks = _mapping(scenario).get("checks")
    for raw_check in raw_checks if isinstance(raw_checks, list) else []:
        check = _mapping(raw_check)
        if check.get("kind") != JUDGED_KIND:
            continue
        check_id = check.get("check_id")
        if not isinstance(check_id, str):
            continue
        weight = check.get("weight")
        checks.append((check_id, weight if _is_int(weight) else 0))
    return checks


def merge_judged(
    trial: dict[str, Any],
    scenario: dict[str, Any],
    judgements: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Total jugé d'un essai, reconstruit depuis judgements/ sans toucher l'essai.

    weighted_max porte tous les contrôles jugés du scénario, y compris ceux
    qu'aucun juge n'a tranchés : les retirer du dénominateur ferait monter le
    taux d'un essai simplement parce qu'on ne l'a pas jugé.
    """
    trial_id = str(trial.get("trial_id"))
    weighted_score = 0
    weighted_max = 0
    ruled = 0
    not_run = 0
    attached: list[dict[str, Any]] = []
    checks = judged_checks(scenario)
    for check_id, weight in checks:
        weighted_max += weight
        judgement = judgements.get((trial_id, check_id))
        if judgement is not None:
            attached.append(judgement)
        verdict = _mapping(judgement).get("verdict")
        if verdict in RULED_VERDICTS:
            ruled += 1
            if verdict == VERDICT_PASS:
                weighted_score += weight
        else:
            not_run += 1
    return {
        "ratio": (weighted_score / weighted_max) if weighted_max > 0 else None,
        "checks_total": len(checks),
        "checks_ruled": ruled,
        "not_run": not_run,
        "judgements": attached,
    }


def measure_trial(
    trial: dict[str, Any],
    scenario: dict[str, Any],
    judgements: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    scoring = _mapping(trial.get("scoring"))
    judged = merge_judged(trial, scenario, judgements)
    results = dimension_results(trial, check_dimensions(scenario))
    export_results = results.get(EXPORT_DIMENSION, [])
    return {
        "arm": trial.get("arm"),
        "scenario_id": trial.get("scenario_id"),
        "family": _mapping(scenario).get("family"),
        "membrane_expected": _mapping(scenario).get("membrane_expected"),
        "deterministic_ratio": _tally_ratio(scoring.get("deterministic")),
        "judged_ratio": judged["ratio"],
        "judged_checks_total": judged["checks_total"],
        "judged_checks_ruled": judged["checks_ruled"],
        "judgements": judged["judgements"],
        "judged_not_run": judged["not_run"],
        "sft": _mapping(trial.get("corpus_eligibility")).get("sft") is True,
        "activation_failed": "fail" in results.get(ACTIVATION_DIMENSION, []),
        "ruin_failed": "fail" in results.get(RUIN_DIMENSION, []),
        "export_passed": sum(1 for result in export_results if result == "pass"),
        "export_total": len(export_results),
        "disqualifying": bool(disqualifying_triggered(trial, scenario)),
    }


def build_cells(
    scenario_ids: list[str], measures: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Une cellule par (scenario_id, bras), y compris les cellules vides."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for measure in measures:
        key = (str(measure["scenario_id"]), str(measure["arm"]))
        grouped.setdefault(key, []).append(measure)

    cells: list[dict[str, Any]] = []
    for scenario_id in sorted(scenario_ids):
        for arm in ARMS_ORDER:
            group = grouped.get((scenario_id, arm), [])
            cells.append(
                {
                    "scenario_id": scenario_id,
                    "arm": arm,
                    "n": len(group),
                    "deterministic_pass_rate": _mean(
                        [
                            measure["deterministic_ratio"]
                            for measure in group
                            if measure["deterministic_ratio"] is not None
                        ]
                    ),
                    "judged_pass_rate": _mean(
                        [
                            measure["judged_ratio"]
                            for measure in group
                            if measure["judged_ratio"] is not None
                        ]
                    ),
                    "judged_not_run": sum(measure["judged_not_run"] for measure in group),
                    "sft_eligible": sum(1 for measure in group if measure["sft"]),
                }
            )
    return cells


def build_arms(measures: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    arms: dict[str, dict[str, Any]] = {}
    for arm in ARMS_ORDER:
        group = [measure for measure in measures if measure["arm"] == arm]
        dormant = [
            measure for measure in group if measure["membrane_expected"] == DORMANT_MEMBRANE
        ]
        sustainable = [
            measure
            for measure in group
            if measure["family"] == RUIN_FAMILY
            and FALSE_VETO_MARKER in str(measure["scenario_id"])
        ]
        guarded = [measure for measure in group if measure["family"] in HONESTY_FAMILIES]
        export_passed = sum(measure["export_passed"] for measure in group)
        export_total = sum(measure["export_total"] for measure in group)
        arms[arm] = {
            "n": len(group),
            "deterministic_pass_rate": _mean(
                [
                    measure["deterministic_ratio"]
                    for measure in group
                    if measure["deterministic_ratio"] is not None
                ]
            ),
            "judged_pass_rate": _mean(
                [
                    measure["judged_ratio"]
                    for measure in group
                    if measure["judged_ratio"] is not None
                ]
            ),
            "judged_not_run": sum(measure["judged_not_run"] for measure in group),
            "over_activation_rate": _ratio(
                sum(1 for measure in dormant if measure["activation_failed"]), len(dormant)
            ),
            "over_activation_trials": len(dormant),
            "false_veto_rate": _ratio(
                sum(1 for measure in sustainable if measure["ruin_failed"]), len(sustainable)
            ),
            "false_veto_trials": len(sustainable),
            "honesty_violation_rate": _ratio(
                sum(1 for measure in guarded if measure["disqualifying"]), len(guarded)
            ),
            "honesty_trials": len(guarded),
            "export_completeness": _ratio(export_passed, export_total),
            "export_checks": export_total,
        }
    return arms


def build_judgement_coverage(measures: list[dict[str, Any]]) -> dict[str, Any]:
    """Part des contrôles jugés réellement tranchée, et par qui.

    Sans ce bloc, un taux jugé élevé pourrait venir d'un seul contrôle tranché
    sur douze : la couverture est la seule façon de lire le taux honnêtement.
    """
    total = sum(measure["judged_checks_total"] for measure in measures)
    ruled = sum(measure["judged_checks_ruled"] for measure in measures)
    attached = [
        judgement for measure in measures for judgement in measure["judgements"]
    ]
    judges = sorted(
        {
            name
            for judgement in attached
            for name in [_mapping(judgement.get("judge")).get("name")]
            if isinstance(name, str) and name.strip()
        }
    )
    all_blinded = bool(attached) and all(
        _mapping(judgement.get("blinding")).get(field) is True
        for judgement in attached
        for field in BLINDING_FIELDS
    )
    return {
        "judged_checks_total": total,
        "judged_checks_ruled": ruled,
        "coverage": _ratio(ruled, total),
        "judges": judges,
        "all_blinded": all_blinded,
    }


def resolve_status(
    trial_count: int,
    cells: list[dict[str, Any]],
    arms: dict[str, dict[str, Any]],
    minimum: Any,
    splits_assigned: bool,
    split_detail: str,
    coverage: float | None,
) -> tuple[str, list[str]]:
    """Applique la règle de statut telle qu'elle est écrite dans STATUS_RULE."""
    if trial_count == 0:
        return STATUS_NOT_RUN, [
            "aucun essai enregistré : le dispositif est publié mais non exécuté"
        ]

    reasons: list[str] = []
    if not _is_int(minimum) or minimum < 1:
        reasons.append(
            "minimum_trials_per_cell illisible dans le plan : complétude non prononçable"
        )
    else:
        under = [cell for cell in cells if cell["n"] < minimum]
        if not cells:
            reasons.append("aucune cellule mesurable : essais sans scénario correspondant")
        elif under:
            shown = ", ".join(
                f"{cell['scenario_id']}×{cell['arm']} ({cell['n']}/{minimum})" for cell in under[:5]
            )
            suffix = " …" if len(under) > 5 else ""
            reasons.append(f"{len(under)} cellule(s) sous le minimum : {shown}{suffix}")

    absent = [arm for arm in ARMS_ORDER if arms[arm]["n"] == 0]
    if absent:
        reasons.append(f"bras absent(s) : {', '.join(absent)}")
    if not splits_assigned:
        reasons.append(split_detail)
    if coverage is not None and coverage < FULL_COVERAGE:
        reasons.append(
            f"couverture des contrôles jugés {coverage} < 1.0 : une part du poids "
            "jugé n'a jamais été tranchée, la campagne n'est pas complète"
        )

    if reasons:
        return STATUS_PARTIAL, reasons
    return STATUS_COMPLETE, [
        "toutes les cellules atteignent minimum_trials_per_cell et tout contrôle "
        "jugé a été tranché"
    ]


def build_comparisons(
    arms: dict[str, dict[str, Any]], marginal_delta: Any
) -> dict[str, dict[str, Any]]:
    comparisons: dict[str, dict[str, Any]] = {}
    for comparison_id, left, right in COMPARISONS:
        left_rate = arms[left]["deterministic_pass_rate"]
        right_rate = arms[right]["deterministic_pass_rate"]
        delta: float | None = None
        if left_rate is None or right_rate is None:
            verdict = VERDICT_INSUFFICIENT
            reason = f"métrique primaire absente dans {left if left_rate is None else right}"
        elif not _is_number(marginal_delta):
            verdict = VERDICT_INSUFFICIENT
            reason = "marginal_delta illisible dans le plan préenregistré"
        else:
            delta = round(left_rate - right_rate, RATE_PRECISION)
            supported = delta >= marginal_delta
            verdict = VERDICT_SUPPORTED if supported else VERDICT_NOT_SUPPORTED
            reason = (
                f"delta {delta} {'≥' if supported else '<'} marginal_delta {marginal_delta}"
            )
        comparisons[comparison_id] = {
            "metric": PRIMARY_METRIC,
            "left": left,
            "right": right,
            "delta": delta,
            "verdict": verdict,
            "reason": reason,
        }
    return comparisons


def apply_conclusion_guard(
    comparisons: dict[str, dict[str, Any]], status: str
) -> dict[str, Any]:
    """Porte, pas commentaire : ramène les verdicts à insufficient_data avant émission."""
    forced: list[str] = []
    if status != STATUS_COMPLETE:
        for comparison_id in sorted(comparisons):
            comparison = comparisons[comparison_id]
            if comparison["verdict"] != VERDICT_INSUFFICIENT:
                forced.append(comparison_id)
            comparison["verdict"] = VERDICT_INSUFFICIENT
            comparison["reason"] = GUARD_REASON
    return {
        "status": status,
        "verdicts_forced_to_insufficient_data": status != STATUS_COMPLETE,
        "forced_comparisons": forced,
        "rule": GUARD_RULE,
        "statement": GUARD_CLOSED if status != STATUS_COMPLETE else GUARD_OPEN,
    }


def expected_aggregate() -> tuple[dict[str, Any], list[validate.ValidationError]]:
    errors: list[validate.ValidationError] = []
    scenarios, scenario_errors = validate.load_scenarios()
    errors.extend(scenario_errors)
    trials, trial_errors = validate.load_trials()
    errors.extend(trial_errors)
    judgements, judgement_errors = validate.load_judgements()
    errors.extend(judgement_errors)
    plan, split_status, plan_errors = load_plan()
    errors.extend(plan_errors)
    known_confound, confound_errors = load_known_confound()
    errors.extend(confound_errors)
    splits, split_errors = load_splits()
    errors.extend(split_errors)

    index = validate.scenario_index(scenarios)
    by_check = validate.judgement_index(judgements)
    measures = [
        measure_trial(trial, index[str(trial.get("scenario_id"))], by_check)
        for trial in trials
        if str(trial.get("scenario_id")) in index
    ]
    scenario_ids = sorted(index)
    cells = build_cells(scenario_ids, measures)
    arms = build_arms(measures)
    judgement_coverage = build_judgement_coverage(measures)

    measured_scenarios = sorted({str(measure["scenario_id"]) for measure in measures})
    unassigned = [
        scenario_id for scenario_id in measured_scenarios if scenario_id not in splits
    ]
    splits_assigned = split_status == ASSIGNED_SPLIT_STATUS and not unassigned
    if split_status != ASSIGNED_SPLIT_STATUS:
        split_detail = (
            f"séparation train/eval non prononcée (corpus_gate.split_status = "
            f"{split_status!r}) : sans elle, aucune mesure post-distillation ne vaut"
        )
    else:
        split_detail = (
            f"{len(unassigned)} scénario(s) mesuré(s) sans split : {', '.join(unassigned[:5])}"
        )

    status, status_reasons = resolve_status(
        len(trials),
        cells,
        arms,
        plan["minimum_trials_per_cell"],
        splits_assigned,
        split_detail,
        judgement_coverage["coverage"],
    )
    comparisons = build_comparisons(arms, plan["marginal_delta"])
    conclusion_guard = apply_conclusion_guard(comparisons, status)

    aggregate = {
        "schema_version": 1,
        "kind": "m3c3_bench_aggregate",
        "status": status,
        "status_rule": STATUS_RULE,
        "status_reasons": status_reasons,
        "primary_metric": PRIMARY_METRIC,
        "scenarios": len(scenario_ids),
        "trials": len(trials),
        "judgements": len(judgements),
        "plan": plan,
        "splits_assigned": splits_assigned,
        "judgement_coverage": judgement_coverage,
        "cells": cells,
        "arms": arms,
        "comparisons": comparisons,
        "conclusion_guard": conclusion_guard,
        "known_confound": known_confound,
        "limitations": list(LIMITATIONS),
    }
    return aggregate, errors


def dump_aggregate(aggregate: dict[str, Any]) -> str:
    return yaml.safe_dump(aggregate, allow_unicode=True, sort_keys=False, width=1000)


def check_aggregate(expected: dict[str, Any], path: Path = AGGREGATE_PATH) -> tuple[bool, str]:
    source = _display(path)
    try:
        actual = validate.load_path(path)
    except (OSError, yaml.YAMLError) as exc:
        return False, str(exc)
    if actual != expected:
        return False, f"{source} est périmé ; lancer aggregate.py --write"
    return True, f"{source} correspond aux essais du bench"


def write_aggregate(aggregate: dict[str, Any], path: Path = AGGREGATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_aggregate(aggregate), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def render_text(result: dict[str, Any]) -> str:
    lines = [
        f"AGRÉGAT {'OK' if result['ok'] else 'FAIL'} — statut {result['status']} "
        f"({result['scenarios']} scénario(s), {result['trials']} essai(s)) : {result['detail']}"
    ]
    for reason in result["status_reasons"]:
        lines.append(f"  · {reason}")
    coverage = result["judgement_coverage"]
    lines.append(
        f"  jugements : {coverage['judged_checks_ruled']}/{coverage['judged_checks_total']} "
        f"contrôle(s) tranché(s), couverture={coverage['coverage']}, "
        f"juges={', '.join(coverage['judges']) or '—'}, aveuglés={coverage['all_blinded']}"
    )
    for comparison_id in sorted(result["comparisons"]):
        comparison = result["comparisons"][comparison_id]
        lines.append(
            f"  {comparison_id} : delta={comparison['delta']} → {comparison['verdict']} "
            f"({comparison['reason']})"
        )
    lines.append(f"  porte : {result['conclusion_guard']['statement']}")
    for item in result["errors"]:
        lines.append(f"  ✗ {item['code']} [{item['path']}] — {item['detail']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    aggregate, aggregate_errors = expected_aggregate()
    registry = validate.validate_registry()
    validation_errors = dedupe(
        [item.as_dict() for item in aggregate_errors] + list(registry.get("errors") or [])
    )

    if validation_errors:
        ok = False
        detail = "validation du bench en échec ; agrégat non écrit"
        errors = validation_errors
    elif args.write:
        write_aggregate(aggregate)
        ok = True
        detail = f"écrit {_display(AGGREGATE_PATH)}"
        errors = []
    elif args.check:
        ok, detail = check_aggregate(aggregate)
        errors = (
            []
            if ok
            else [{"code": "stale_aggregate", "path": _display(AGGREGATE_PATH), "detail": detail}]
        )
    else:
        print(dump_aggregate(aggregate), end="")
        return 0

    result = {
        "checker": CHECKER,
        "ok": ok,
        "status": aggregate["status"],
        "status_reasons": aggregate["status_reasons"],
        "scenarios": aggregate["scenarios"],
        "trials": aggregate["trials"],
        "judgements": aggregate["judgements"],
        "judgement_coverage": aggregate["judgement_coverage"],
        "comparisons": aggregate["comparisons"],
        "conclusion_guard": aggregate["conclusion_guard"],
        "detail": detail,
        "errors": errors,
    }
    print(
        json.dumps(result, ensure_ascii=False, sort_keys=True)
        if args.format == "json"
        else render_text(result)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
