#!/usr/bin/env python3
"""Construit ou vérifie les index déterministes de M3C3-bench.

Trois index sont dérivés des fichiers réellement présents : celui des scénarios,
celui des essais et celui des jugements. Ils ne sont jamais écrits à la main et
ne sont écrits que si la validation du registre passe : un index qui décrit un
bench invalide donnerait l'apparence d'un dispositif vérifié.

L'index des jugements est distinct de celui des essais parce que les deux
enregistrements le sont : un jugement s'ajoute, il ne retouche pas la mesure
qu'il analyse. Un index de jugements vide est un état légitime — il dit qu'aucun
juge n'est passé, ce qui n'est pas la même chose qu'un juge favorable.
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


SCENARIO_INDEX_PATH = validate.SCENARIOS_DIR / "index.yaml"
TRIAL_INDEX_PATH = validate.TRIALS_DIR / "index.yaml"
JUDGEMENT_INDEX_PATH = validate.JUDGEMENTS_DIR / "index.yaml"
SPLITS_PATH = validate.BENCH_ROOT / "splits.yaml"
SPLIT_VALUES = {"train", "eval"}
# Tant que la séparation train/eval n'est pas prononcée, la seule valeur honnête
# est « unassigned » : inventer un split fabriquerait une garantie anti-fuite
# qui n'existe pas — analysis-plan.yaml#corpus_gate.anti_leak.
UNASSIGNED_SPLIT = "unassigned"
CHECKER = "m3c3_bench_index"
INDEX_PATHS = {SCENARIO_INDEX_PATH, TRIAL_INDEX_PATH, JUDGEMENT_INDEX_PATH}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _relative_to_bench(path: Path) -> str:
    return path.relative_to(validate.BENCH_ROOT).as_posix()


def _display(path: Path) -> str:
    return path.relative_to(validate.REPO_ROOT).as_posix()


def check_counts(scenario: dict[str, Any]) -> tuple[int, int, int]:
    """Retourne (contrôles déterministes, contrôles jugés, poids déterministe total)."""
    checks = scenario.get("checks")
    if not isinstance(checks, list):
        return 0, 0, 0
    deterministic = 0
    judged = 0
    weighted_max = 0
    for raw_check in checks:
        check = _mapping(raw_check)
        kind = check.get("kind")
        if kind == "deterministic":
            deterministic += 1
            weight = check.get("weight")
            if _is_int(weight):
                weighted_max += weight
        elif kind == "judged":
            judged += 1
    return deterministic, judged, weighted_max


def load_splits(scenario_ids: list[str]) -> tuple[dict[str, str], list[validate.ValidationError]]:
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
            validate.ValidationError("splits_type", source, "attendu : mapping scenario_id -> train|eval")
        )
        return {}, errors
    known = set(scenario_ids)
    splits: dict[str, str] = {}
    for raw_id, raw_split in document.items():
        scenario_id = str(raw_id)
        if raw_split not in SPLIT_VALUES:
            errors.append(
                validate.ValidationError(
                    "splits_value",
                    f"{source}.{scenario_id}",
                    "attendu : train ou eval",
                )
            )
            continue
        if scenario_id not in known:
            errors.append(
                validate.ValidationError(
                    "splits_unknown_scenario",
                    f"{source}.{scenario_id}",
                    "affectation sans scénario correspondant",
                )
            )
            continue
        splits[scenario_id] = raw_split
    return splits, errors


def expected_scenario_index() -> tuple[dict[str, Any], list[validate.ValidationError]]:
    scenarios, errors = validate.load_scenarios()
    # L'index vit dans le répertoire des cas ; il n'est jamais son propre cas.
    scenarios = [
        scenario
        for scenario in scenarios
        if Path(scenario["__path__"]).resolve() not in INDEX_PATHS
    ]
    scenario_ids = [str(scenario.get("scenario_id", "")) for scenario in scenarios]
    splits, split_errors = load_splits(scenario_ids)
    errors.extend(split_errors)
    entries: list[dict[str, Any]] = []
    for scenario in sorted(scenarios, key=lambda item: str(item.get("scenario_id", ""))):
        path = Path(scenario["__path__"])
        deterministic, judged, weighted_max = check_counts(scenario)
        scenario_id = scenario.get("scenario_id")
        entries.append(
            {
                "scenario_id": scenario_id,
                "path": _relative_to_bench(path),
                "file_sha256": validate.file_sha256(path),
                "created_at": scenario.get("created_at"),
                "family": scenario.get("family"),
                "membrane_expected": scenario.get("membrane_expected"),
                "regime_expected": scenario.get("regime_expected"),
                "deterministic_checks": deterministic,
                "judged_checks": judged,
                "weighted_max": weighted_max,
                "split": splits.get(str(scenario_id), UNASSIGNED_SPLIT),
                "supersedes": scenario.get("supersedes") or [],
            }
        )
    return {
        "schema_version": 1,
        "kind": "m3c3_bench_scenario_index",
        "scenarios_sha256": validate.sha256_text(validate.canonical_json(entries)),
        "scenarios": entries,
    }, errors


def expected_trial_index() -> tuple[dict[str, Any], list[validate.ValidationError]]:
    trials, errors = validate.load_trials()
    trials = [
        trial for trial in trials if Path(trial["__path__"]).resolve() not in INDEX_PATHS
    ]
    entries: list[dict[str, Any]] = []
    for trial in sorted(trials, key=lambda item: str(item.get("trial_id", ""))):
        path = Path(trial["__path__"])
        subject = _mapping(trial.get("subject"))
        scoring = _mapping(trial.get("scoring"))
        deterministic = _mapping(scoring.get("deterministic"))
        judged = _mapping(scoring.get("judged"))
        eligibility = _mapping(trial.get("corpus_eligibility"))
        entries.append(
            {
                "trial_id": trial.get("trial_id"),
                "path": _relative_to_bench(path),
                "file_sha256": validate.file_sha256(path),
                "created_at": trial.get("created_at"),
                "scenario_id": trial.get("scenario_id"),
                "arm": trial.get("arm"),
                "subject_model": subject.get("model"),
                "deterministic_weighted_score": deterministic.get("weighted_score"),
                "deterministic_weighted_max": deterministic.get("weighted_max"),
                "judged_not_run": judged.get("not_run"),
                "corpus_sft": eligibility.get("sft"),
            }
        )
    return {
        "schema_version": 1,
        "kind": "m3c3_bench_trial_index",
        "trials_sha256": validate.sha256_text(validate.canonical_json(entries)),
        "trials": entries,
    }, errors


def expected_judgement_index() -> tuple[dict[str, Any], list[validate.ValidationError]]:
    judgements, errors = validate.load_judgements()
    judgements = [
        judgement
        for judgement in judgements
        if Path(judgement["__path__"]).resolve() not in INDEX_PATHS
    ]
    # Même définition du remplacement que judgement_index : deux lectures de
    # « actif » divergeraient tôt ou tard, et l'index cesserait de décrire ce
    # que l'agrégateur compte.
    replaced = validate._superseded_ids(judgements)
    entries: list[dict[str, Any]] = []
    for judgement in sorted(judgements, key=lambda item: str(item.get("judgement_id", ""))):
        path = Path(judgement["__path__"])
        judge = _mapping(judgement.get("judge"))
        entries.append(
            {
                "judgement_id": judgement.get("judgement_id"),
                "path": _relative_to_bench(path),
                "file_sha256": validate.file_sha256(path),
                "created_at": judgement.get("created_at"),
                "trial_id": judgement.get("trial_id"),
                "check_id": judgement.get("check_id"),
                "judge_name": judge.get("name"),
                "verdict": judgement.get("verdict"),
                "superseded": str(judgement.get("judgement_id")) in replaced,
            }
        )
    return {
        "schema_version": 1,
        "kind": "m3c3_bench_judgement_index",
        "judgements_sha256": validate.sha256_text(validate.canonical_json(entries)),
        "judgements": entries,
    }, errors


def dump_index(index: dict[str, Any]) -> str:
    return yaml.safe_dump(index, allow_unicode=True, sort_keys=False, width=1000)


def check_index(expected: dict[str, Any], path: Path) -> tuple[bool, str]:
    source = _display(path)
    try:
        actual = validate.load_path(path)
    except (OSError, yaml.YAMLError) as exc:
        return False, str(exc)
    if actual != expected:
        return False, f"{source} est périmé ; lancer build_index.py --write"
    return True, f"{source} correspond aux fichiers du bench"


def write_index(index: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_index(index), encoding="utf-8")


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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    scenario_index, scenario_errors = expected_scenario_index()
    trial_index, trial_errors = expected_trial_index()
    judgement_index, judgement_errors = expected_judgement_index()
    registry = validate.validate_registry()
    validation_errors = dedupe(
        [item.as_dict() for item in scenario_errors]
        + [item.as_dict() for item in trial_errors]
        + [item.as_dict() for item in judgement_errors]
        + list(registry.get("errors") or [])
    )
    counts = {
        "scenarios": len(scenario_index["scenarios"]),
        "trials": len(trial_index["trials"]),
        "judgements": len(judgement_index["judgements"]),
    }
    targets = (
        (scenario_index, SCENARIO_INDEX_PATH),
        (trial_index, TRIAL_INDEX_PATH),
        (judgement_index, JUDGEMENT_INDEX_PATH),
    )

    if validation_errors:
        result = {
            "checker": CHECKER,
            "ok": False,
            **counts,
            "detail": "validation du bench en échec ; index non écrit",
            "errors": validation_errors,
        }
    elif args.write:
        for index, path in targets:
            write_index(index, path)
        result = {
            "checker": CHECKER,
            "ok": True,
            **counts,
            "detail": "écrit " + ", ".join(_display(path) for _, path in targets),
            "errors": [],
        }
    elif args.check:
        outcomes = [(path, *check_index(index, path)) for index, path in targets]
        stale = [
            {"code": "stale_index", "path": _display(path), "detail": detail}
            for path, ok, detail in outcomes
            if not ok
        ]
        result = {
            "checker": CHECKER,
            "ok": all(ok for _, ok, _ in outcomes),
            **counts,
            "detail": " ; ".join(detail for _, _, detail in outcomes),
            "errors": stale,
        }
    else:
        for position, (index, _) in enumerate(targets):
            if position:
                print("---")
            print(dump_index(index), end="")
        return 0

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        prefix = "OK" if result["ok"] else "FAIL"
        print(
            f"INDEX {prefix} — {result['detail']} "
            f"({result['scenarios']} scénario(s), {result['trials']} essai(s), "
            f"{result['judgements']} jugement(s))"
        )
        for item in result["errors"]:
            print(f"  ✗ {item['code']} [{item['path']}] — {item['detail']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
