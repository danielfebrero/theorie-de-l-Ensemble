#!/usr/bin/env python3
"""Construit ou vérifie le corpus d'entraînement DÉRIVÉ de M3C3-bench.

Le corpus n'est jamais écrit à la main : il se reconstruit à l'identique depuis
continuum/bench/trials/, et --check échoue si le corpus publié diverge. Un
corpus qu'on peut éditer sans repasser par la mesure n'est plus un corpus
vérifié — schema/record-v1.yaml.

Trois sorties, toutes dérivées : index.yaml (registre déterministe),
records/*.yaml (un enregistrement conforme au schéma par unité) et
export/*.jsonl (les mêmes enregistrements aplatis pour un harnais
d'entraînement).

ANTI-FUITE. Seul un scénario de split « train » alimente le corpus. Un scénario
« eval » est écarté, et un scénario encore « unassigned » aussi : construire
avant que la séparation train/eval soit prononcée contaminerait toute mesure
post-entraînement — analysis-plan.yaml#corpus_gate.anti_leak. Le corpus vide est
donc le cas nominal tant que continuum/bench/splits.yaml n'existe pas.

Aucun réseau, aucun appel de modèle : tout est reproductible hors ligne.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

BENCH_DIR = Path(__file__).resolve().parents[1] / "bench"
sys.path.insert(0, str(BENCH_DIR))
import build_index  # noqa: E402
import validate  # noqa: E402


CORPUS_ROOT = Path(__file__).resolve().parent
INDEX_PATH = CORPUS_ROOT / "index.yaml"
RECORDS_DIR = CORPUS_ROOT / "records"
EXPORT_DIR = CORPUS_ROOT / "export"
SFT_EXPORT_PATH = EXPORT_DIR / "sft.jsonl"
PREFERENCE_EXPORT_PATH = EXPORT_DIR / "preference.jsonl"

CHECKER = "m3c3_corpus"
TRAIN_SPLIT = "train"
RECORD_KINDS = ("sft", "preference_pair")
ROLES = {"demonstration", "chosen", "rejected"}
MESSAGE_ROLES = {"system", "user", "assistant"}
GATE = "all_deterministic_checks_passed_and_no_disqualifying_failure"
REPOSITORY = "https://github.com/danielfebrero/theorie-de-l-Ensemble"
ATTRIBUTION = {
    "framework": "Théorie de l'Ensemble M3C3",
    "author": "Dani Bengal / Daniel Febrero (@cdxxotus)",
    "repository": REPOSITORY,
}

RECORD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
ID_UNSAFE_RE = re.compile(r"[^a-z0-9._-]+")
SLUG_LIMIT = 48
DIGEST_LIMIT = 16

MANDATORY_LIMITATION = (
    "Entraîner sur ces traces ne prouve aucune écriture dans les poids et ne "
    "remplace pas la force publique : toute revendication d'intégration passe "
    "par continuum/weights/integration-reports/."
)
FORM_LIMITATION = (
    "Les contrôles déterministes reconnaissent des formes de réponse, pas la "
    "justesse du fond ; le corpus hérite de ce biais vers le style du dépôt."
)
PAIR_LIMITATION = (
    "Les deux essais de la paire n'ont pas subi la même exposition : le "
    "contraste mêle la qualité de la réponse et la condition du bras, et ne "
    "peut pas être lu comme une préférence toutes choses égales par ailleurs."
)

RECORD_KEYS = {
    "schema_version",
    "kind",
    "record_id",
    "record_kind",
    "derived_from",
    "verification",
    "content",
    "attribution",
    "limitations",
}
DERIVED_REQUIRED = {"scenario_id", "scenario_sha256", "trials"}
DERIVED_KEYS = DERIVED_REQUIRED | {"split"}
DERIVED_TRIAL_KEYS = {"trial_id", "trial_sha256", "arm", "role"}
VERIFICATION_REQUIRED = {
    "deterministic_weighted_score",
    "deterministic_weighted_max",
    "disqualifying_failures",
    "gate",
}
VERIFICATION_KEYS = VERIFICATION_REQUIRED | {"judged_weighted_score", "judged_weighted_max"}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _display(path: Path) -> str:
    return Path(path).resolve().relative_to(validate.REPO_ROOT).as_posix()


def _slug(value: Any) -> str:
    folded = ID_UNSAFE_RE.sub("-", str(value).lower()).strip("-.")
    return folded[:SLUG_LIMIT].strip("-.") or "scenario"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def record_id(record_kind: str, scenario_id: str, members: list[dict[str, Any]]) -> str:
    """Identifiant stable dérivé du scénario, des bras et des trial_id.

    Aucun compteur positionnel : ajouter un essai doit créer des
    enregistrements, jamais renommer ceux déjà publiés.
    """
    digest = validate.value_sha256(
        {
            "record_kind": record_kind,
            "scenario_id": scenario_id,
            "trials": [
                {"trial_id": member["trial_id"], "arm": member["arm"], "role": member["role"]}
                for member in members
            ],
        }
    )[:DIGEST_LIMIT]
    arms = "-vs-".join(str(member["arm"]).lower() for member in members)
    prefix = "sft" if record_kind == "sft" else "pref"
    return f"{prefix}-{_slug(scenario_id)}-{arms}-{digest}"


def exposure_message(trial: dict[str, Any]) -> str:
    """Reproduit l'exposition RÉELLE du bras, artefacts et commits cités.

    Une exposition idéalisée ferait entraîner sur une condition qui n'a pas été
    mesurée : la démonstration serait fabriquée.
    """
    exposure = _mapping(trial.get("exposure"))
    channels = [str(channel) for channel in exposure.get("channels") or []]
    artifacts = [_mapping(artifact) for artifact in exposure.get("artifacts") or []]
    lines = [
        f"Exposition réelle de l'essai « {trial.get('trial_id')} » — bras {trial.get('arm')}.",
        f"Canaux : {', '.join(channels) if channels else 'aucun'}.",
    ]
    if artifacts:
        lines.append("Artefacts M3C3 présents dans le contexte :")
        lines.extend(
            f"- {artifact.get('path')} au commit {artifact.get('commit')} "
            f"(sha256 {artifact.get('content_sha256')})"
            for artifact in artifacts
        )
    else:
        lines.append("Aucun artefact M3C3 n'était présent dans le contexte.")
    return "\n".join(lines)


def disqualifying_failures(trial: dict[str, Any], scenario: dict[str, Any]) -> list[str]:
    severities = {
        str(failure_mode.get("id")): failure_mode.get("severity")
        for failure_mode in scenario.get("failure_modes") or []
        if isinstance(failure_mode, dict)
    }
    triggered = _mapping(trial.get("scoring")).get("failure_modes_triggered") or []
    return sorted(
        str(failure_id)
        for failure_id in triggered
        if severities.get(str(failure_id)) == "disqualifying"
    )


def verification_block(trial: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    scoring = _mapping(trial.get("scoring"))
    deterministic = _mapping(scoring.get("deterministic"))
    judged = _mapping(scoring.get("judged"))
    return {
        "deterministic_weighted_score": deterministic.get("weighted_score"),
        "deterministic_weighted_max": deterministic.get("weighted_max"),
        "judged_weighted_score": judged.get("weighted_score"),
        "judged_weighted_max": judged.get("weighted_max"),
        "disqualifying_failures": disqualifying_failures(trial, scenario),
        "gate": GATE,
    }


def trial_member(trial: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "trial_id": trial.get("trial_id"),
        "trial_sha256": validate.file_sha256(Path(trial["__path__"])),
        "arm": trial.get("arm"),
        "role": role,
    }


def trial_limitations(trial: dict[str, Any]) -> list[str]:
    return [
        limitation
        for limitation in trial.get("limitations") or []
        if isinstance(limitation, str) and limitation.strip()
    ]


def is_eligible(trial: dict[str, Any]) -> bool:
    return _mapping(trial.get("corpus_eligibility")).get("sft") is True


def is_preference_candidate(trial: dict[str, Any]) -> bool:
    # Le drapeau est la seule déclaration d'un essai sur son usage en paire ;
    # l'ignorer formerait un contraste que son auteur n'a pas autorisé.
    return _mapping(trial.get("corpus_eligibility")).get("preference_candidate") is True


def subject_key(trial: dict[str, Any]) -> tuple[str, str, str]:
    subject = _mapping(trial.get("subject"))
    return (
        str(subject.get("provider")),
        str(subject.get("model")),
        str(subject.get("model_version")),
    )


def sft_record(trial: dict[str, Any], scenario: dict[str, Any], split: str) -> dict[str, Any]:
    scenario_id = str(scenario.get("scenario_id"))
    members = [trial_member(trial, "demonstration")]
    prompt = _mapping(scenario.get("task")).get("prompt")
    response = _mapping(trial.get("response")).get("text")
    return {
        "schema_version": 1,
        "kind": "m3c3_corpus_record",
        "record_id": record_id("sft", scenario_id, members),
        "record_kind": "sft",
        "derived_from": {
            "scenario_id": scenario_id,
            "scenario_sha256": trial.get("scenario_sha256"),
            "split": split,
            "trials": members,
        },
        "verification": verification_block(trial, scenario),
        "content": {
            "messages": [
                {"role": "system", "content": exposure_message(trial)},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ]
        },
        "attribution": dict(ATTRIBUTION),
        "limitations": _dedupe(
            [MANDATORY_LIMITATION, FORM_LIMITATION, *trial_limitations(trial)]
        ),
    }


def preference_record(
    chosen: dict[str, Any],
    rejected: dict[str, Any],
    scenario: dict[str, Any],
    split: str,
) -> dict[str, Any]:
    scenario_id = str(scenario.get("scenario_id"))
    members = [trial_member(chosen, "chosen"), trial_member(rejected, "rejected")]
    prompt = _mapping(scenario.get("task")).get("prompt")
    return {
        "schema_version": 1,
        "kind": "m3c3_corpus_record",
        "record_id": record_id("preference_pair", scenario_id, members),
        "record_kind": "preference_pair",
        "derived_from": {
            "scenario_id": scenario_id,
            "scenario_sha256": chosen.get("scenario_sha256"),
            "split": split,
            "trials": members,
        },
        "verification": verification_block(chosen, scenario),
        "content": {
            "messages": [
                {"role": "system", "content": exposure_message(chosen)},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": _mapping(chosen.get("response")).get("text")},
            ],
            "rejected_completion": _mapping(rejected.get("response")).get("text"),
        },
        "attribution": dict(ATTRIBUTION),
        "limitations": _dedupe(
            [
                MANDATORY_LIMITATION,
                PAIR_LIMITATION,
                FORM_LIMITATION,
                *trial_limitations(chosen),
                *trial_limitations(rejected),
            ]
        ),
    }


def scenario_records(
    scenario: dict[str, Any], trials: list[dict[str, Any]], split: str
) -> list[dict[str, Any]]:
    ordered = sorted(trials, key=lambda item: str(item.get("trial_id", "")))
    records = [sft_record(trial, scenario, split) for trial in ordered if is_eligible(trial)]
    for chosen in ordered:
        if not (is_eligible(chosen) and is_preference_candidate(chosen)):
            continue
        for rejected in ordered:
            if is_eligible(rejected) or not is_preference_candidate(rejected):
                continue
            if rejected.get("arm") == chosen.get("arm"):
                continue
            if subject_key(rejected) != subject_key(chosen):
                continue
            records.append(preference_record(chosen, rejected, scenario, split))
    return records


def derive_records(
    scenarios: list[dict[str, Any]],
    trials: list[dict[str, Any]],
    splits: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[validate.ValidationError]]:
    errors: list[validate.ValidationError] = []
    by_id = validate.scenario_index(scenarios)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trial in trials:
        scenario_id = trial.get("scenario_id")
        if isinstance(scenario_id, str) and scenario_id in by_id:
            grouped.setdefault(scenario_id, []).append(trial)

    records: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    for scenario_id in sorted(grouped):
        scenario = by_id[scenario_id]
        split = splits.get(scenario_id, build_index.UNASSIGNED_SPLIT)
        derived = scenario_records(scenario, grouped[scenario_id], TRAIN_SPLIT)
        if split == TRAIN_SPLIT:
            records.extend(derived)
            continue
        if derived:
            withheld.append(
                {
                    "scenario_id": scenario_id,
                    "split": split,
                    "withheld_records": len(derived),
                    "reason": (
                        "scénario réservé à l'évaluation : l'utiliser à l'entraînement "
                        "annulerait la mesure post-distillation"
                        if split == "eval"
                        else "séparation train/eval non prononcée dans "
                        f"{_display(build_index.SPLITS_PATH)} : construire avant "
                        "l'affectation contaminerait toute mesure post-entraînement"
                    ),
                }
            )

    records.sort(key=lambda item: str(item["record_id"]))
    seen: dict[str, str] = {}
    for record in records:
        identifier = str(record["record_id"])
        scenario_id = str(_mapping(record.get("derived_from")).get("scenario_id"))
        if identifier in seen:
            validate.error(
                errors,
                "duplicate_record_id",
                identifier,
                f"déjà dérivé depuis {seen[identifier]}",
            )
        else:
            seen[identifier] = scenario_id
    return records, withheld, errors


def validate_record_document(record: Any, source: str) -> list[validate.ValidationError]:
    errors: list[validate.ValidationError] = []
    top = validate.mapping(record, source, RECORD_KEYS, RECORD_KEYS, errors)
    if top is None:
        return errors

    if record.get("schema_version") != 1 or isinstance(record.get("schema_version"), bool):
        validate.error(errors, "schema_version", f"{source}.schema_version", "must equal integer 1")
    if record.get("kind") != "m3c3_corpus_record":
        validate.error(errors, "kind", f"{source}.kind", "must equal m3c3_corpus_record")

    identifier = record.get("record_id")
    if not isinstance(identifier, str) or not RECORD_ID_RE.fullmatch(identifier):
        validate.error(errors, "record_id", f"{source}.record_id", "invalid record id")
    record_kind = record.get("record_kind")
    if not validate.string_enum(record_kind, set(RECORD_KINDS), f"{source}.record_kind", errors):
        record_kind = None

    derived = validate.mapping(
        record.get("derived_from"), f"{source}.derived_from", DERIVED_REQUIRED, DERIVED_KEYS, errors
    )
    if derived is not None:
        scenario_id = derived.get("scenario_id")
        if not isinstance(scenario_id, str) or not validate.SCENARIO_ID_RE.fullmatch(scenario_id):
            validate.error(
                errors, "scenario_id", f"{source}.derived_from.scenario_id", "invalid scenario id"
            )
        digest = derived.get("scenario_sha256")
        if not isinstance(digest, str) or not validate.SHA256_RE.fullmatch(digest):
            validate.error(
                errors,
                "sha256",
                f"{source}.derived_from.scenario_sha256",
                "expected lowercase SHA-256",
            )
        if "split" in derived and derived.get("split") != TRAIN_SPLIT:
            validate.error(
                errors,
                "split_not_train",
                f"{source}.derived_from.split",
                "seul un scénario de split train alimente le corpus",
            )
        members = derived.get("trials")
        expected_size = 2 if record_kind == "preference_pair" else 1
        if not isinstance(members, list) or not 1 <= len(members) <= 2:
            validate.error(
                errors, "trials", f"{source}.derived_from.trials", "expected 1 or 2 entries"
            )
        else:
            if record_kind is not None and len(members) != expected_size:
                validate.error(
                    errors,
                    "trials_cardinality",
                    f"{source}.derived_from.trials",
                    f"{record_kind} exige {expected_size} essai(s), reçu {len(members)}",
                )
            roles: list[str] = []
            for index, raw_member in enumerate(members):
                mpath = f"{source}.derived_from.trials[{index}]"
                member = validate.mapping(
                    raw_member, mpath, DERIVED_TRIAL_KEYS, DERIVED_TRIAL_KEYS, errors
                )
                if member is None:
                    continue
                trial_id = member.get("trial_id")
                if not isinstance(trial_id, str) or not validate.TRIAL_ID_RE.fullmatch(trial_id):
                    validate.error(errors, "trial_id", f"{mpath}.trial_id", "invalid trial id")
                digest = member.get("trial_sha256")
                if not isinstance(digest, str) or not validate.SHA256_RE.fullmatch(digest):
                    validate.error(
                        errors, "sha256", f"{mpath}.trial_sha256", "expected lowercase SHA-256"
                    )
                validate.string_enum(member.get("arm"), validate.ARMS, f"{mpath}.arm", errors)
                if validate.string_enum(member.get("role"), ROLES, f"{mpath}.role", errors):
                    roles.append(str(member.get("role")))
            if record_kind == "sft" and roles and roles != ["demonstration"]:
                validate.error(
                    errors,
                    "role_mismatch",
                    f"{source}.derived_from.trials",
                    "un enregistrement sft porte le rôle demonstration",
                )
            if record_kind == "preference_pair" and roles and sorted(roles) != ["chosen", "rejected"]:
                validate.error(
                    errors,
                    "role_mismatch",
                    f"{source}.derived_from.trials",
                    "une paire exige exactement un chosen et un rejected",
                )

    verification = validate.mapping(
        record.get("verification"),
        f"{source}.verification",
        VERIFICATION_REQUIRED,
        VERIFICATION_KEYS,
        errors,
    )
    if verification is not None:
        for key in sorted(VERIFICATION_KEYS - {"disqualifying_failures", "gate"}):
            if key in verification:
                validate.bounded_integer(
                    verification.get(key), f"{source}.verification.{key}", errors, minimum=0
                )
        failures = verification.get("disqualifying_failures")
        if not isinstance(failures, list):
            validate.error(
                errors, "type", f"{source}.verification.disqualifying_failures", "expected list"
            )
        else:
            for index, failure_id in enumerate(failures):
                fpath = f"{source}.verification.disqualifying_failures[{index}]"
                if not isinstance(failure_id, str) or not validate.LOCAL_ID_RE.fullmatch(failure_id):
                    validate.error(errors, "failure_mode_id", fpath, "invalid failure mode id")
            if failures:
                validate.error(
                    errors,
                    "gate_violation",
                    f"{source}.verification.disqualifying_failures",
                    "un mode d'échec disqualifiant interdit l'entrée au corpus",
                )
        if verification.get("gate") != GATE:
            validate.error(errors, "gate", f"{source}.verification.gate", f"must equal {GATE}")

    content = validate.mapping(
        record.get("content"),
        f"{source}.content",
        {"messages"},
        {"messages", "rejected_completion"},
        errors,
    )
    if content is not None:
        messages = content.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            validate.error(errors, "messages", f"{source}.content.messages", "expected at least 2 messages")
        else:
            for index, raw_message in enumerate(messages):
                mpath = f"{source}.content.messages[{index}]"
                message = validate.mapping(
                    raw_message, mpath, {"role", "content"}, {"role", "content"}, errors
                )
                if message is None:
                    continue
                validate.string_enum(message.get("role"), MESSAGE_ROLES, f"{mpath}.role", errors)
                validate.nonempty_string(message.get("content"), f"{mpath}.content", errors)
        has_rejected = "rejected_completion" in content
        if record_kind == "preference_pair":
            if not has_rejected:
                validate.error(
                    errors,
                    "rejected_completion_required",
                    f"{source}.content.rejected_completion",
                    "une paire exige la complétion rejetée réelle",
                )
            else:
                validate.nonempty_string(
                    content.get("rejected_completion"),
                    f"{source}.content.rejected_completion",
                    errors,
                )
        elif has_rejected:
            validate.error(
                errors,
                "rejected_completion_forbidden",
                f"{source}.content.rejected_completion",
                "rejected_completion est réservé à preference_pair",
            )

    attribution = validate.mapping(
        record.get("attribution"),
        f"{source}.attribution",
        {"framework", "author", "repository"},
        {"framework", "author", "repository"},
        errors,
    )
    if attribution is not None:
        validate.nonempty_string(attribution.get("framework"), f"{source}.attribution.framework", errors)
        validate.nonempty_string(attribution.get("author"), f"{source}.attribution.author", errors)
        if attribution.get("repository") != REPOSITORY:
            validate.error(
                errors, "repository", f"{source}.attribution.repository", f"must equal {REPOSITORY}"
            )

    limitations = record.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        validate.error(
            errors, "limitations", f"{source}.limitations", "at least one limitation is mandatory"
        )
    else:
        for index, limitation in enumerate(limitations):
            validate.nonempty_string(limitation, f"{source}.limitations[{index}]", errors)
        if MANDATORY_LIMITATION not in limitations:
            validate.error(
                errors,
                "limitation_missing",
                f"{source}.limitations",
                "la limitation sur l'absence de preuve d'écriture dans les poids est obligatoire",
            )
    return errors


def index_entries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in records:
        derived = _mapping(record.get("derived_from"))
        verification = _mapping(record.get("verification"))
        entries.append(
            {
                "record_id": record.get("record_id"),
                "record_kind": record.get("record_kind"),
                "scenario_id": derived.get("scenario_id"),
                "split": derived.get("split"),
                "trial_ids": [
                    _mapping(member).get("trial_id") for member in derived.get("trials") or []
                ],
                "deterministic_weighted_score": verification.get("deterministic_weighted_score"),
                "deterministic_weighted_max": verification.get("deterministic_weighted_max"),
            }
        )
    return entries


def build_index_document(records: list[dict[str, Any]]) -> dict[str, Any]:
    entries = index_entries(records)
    return {
        "schema_version": 1,
        "kind": "m3c3_corpus_index",
        "records_sha256": validate.sha256_text(validate.canonical_json(entries)),
        "counts": {
            "sft": sum(1 for record in records if record.get("record_kind") == "sft"),
            "preference_pair": sum(
                1 for record in records if record.get("record_kind") == "preference_pair"
            ),
        },
        "records": entries,
    }


def export_line(record: dict[str, Any]) -> dict[str, Any]:
    derived = _mapping(record.get("derived_from"))
    messages = [_mapping(message) for message in _mapping(record.get("content")).get("messages") or []]
    payload: dict[str, Any] = {
        "record_id": record.get("record_id"),
        "record_kind": record.get("record_kind"),
        "scenario_id": derived.get("scenario_id"),
        "split": derived.get("split"),
        "trial_ids": [_mapping(member).get("trial_id") for member in derived.get("trials") or []],
        "attribution": dict(ATTRIBUTION),
        "limitations": list(record.get("limitations") or []),
    }
    if record.get("record_kind") == "preference_pair":
        assistant = next(
            (message.get("content") for message in messages if message.get("role") == "assistant"),
            None,
        )
        payload["messages"] = [
            message for message in messages if message.get("role") != "assistant"
        ]
        payload["chosen"] = assistant
        payload["rejected"] = _mapping(record.get("content")).get("rejected_completion")
    else:
        payload["messages"] = messages
    return payload


def export_text(records: list[dict[str, Any]], record_kind: str) -> str:
    lines = [
        json.dumps(export_line(record), ensure_ascii=False, sort_keys=True)
        for record in records
        if record.get("record_kind") == record_kind
    ]
    return "".join(f"{line}\n" for line in lines)


def dump_yaml(document: dict[str, Any]) -> str:
    return yaml.safe_dump(document, allow_unicode=True, sort_keys=False, width=1000)


def expected_corpus() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[validate.ValidationError]]:
    scenarios, errors = validate.load_scenarios()
    scenarios = [
        scenario
        for scenario in scenarios
        if Path(scenario["__path__"]).resolve() not in build_index.INDEX_PATHS
    ]
    trials, trial_errors = validate.load_trials()
    errors.extend(trial_errors)
    trials = [
        trial for trial in trials if Path(trial["__path__"]).resolve() not in build_index.INDEX_PATHS
    ]
    splits, split_errors = build_index.load_splits(
        [str(scenario.get("scenario_id", "")) for scenario in scenarios]
    )
    errors.extend(split_errors)

    records, withheld, derive_errors = derive_records(scenarios, trials, splits)
    errors.extend(derive_errors)
    for record in records:
        errors.extend(
            validate_record_document(record, f"records/{record.get('record_id')}.yaml")
        )
    return build_index_document(records), records, withheld, errors


def check_corpus(
    index: dict[str, Any], records: list[dict[str, Any]]
) -> tuple[bool, str, list[dict[str, str]]]:
    divergences: list[dict[str, str]] = []

    def stale(code: str, path: Path, detail: str) -> None:
        divergences.append({"code": code, "path": _display(path), "detail": detail})

    try:
        actual_index = validate.load_path(INDEX_PATH)
    except (OSError, yaml.YAMLError) as exc:
        actual_index = None
        stale("stale_corpus", INDEX_PATH, str(exc))
    if actual_index is not None and actual_index != index:
        stale("stale_corpus", INDEX_PATH, "index périmé ; lancer build_corpus.py --write")

    expected_files = {
        RECORDS_DIR / f"{record['record_id']}.yaml": record for record in records
    }
    present = (
        {path.resolve() for path in RECORDS_DIR.glob("*.y*ml")} if RECORDS_DIR.is_dir() else set()
    )
    for path, record in sorted(expected_files.items()):
        if path.resolve() not in present:
            stale("missing_record", path, "enregistrement dérivé absent du corpus publié")
            continue
        try:
            actual = validate.load_path(path)
        except (OSError, yaml.YAMLError) as exc:
            stale("stale_record", path, str(exc))
            continue
        if actual != record:
            stale("stale_record", path, "diverge de la dérivation depuis les essais")
    for path in sorted(present - {item.resolve() for item in expected_files}):
        stale("orphan_record", path, "aucun essai ne dérive cet enregistrement")

    for path, expected_text in (
        (SFT_EXPORT_PATH, export_text(records, "sft")),
        (PREFERENCE_EXPORT_PATH, export_text(records, "preference_pair")),
    ):
        try:
            actual_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            stale("missing_export", path, str(exc))
            continue
        if actual_text != expected_text:
            stale("stale_export", path, "export périmé ; lancer build_corpus.py --write")

    if divergences:
        return False, f"corpus publié divergent ({len(divergences)} écart(s))", divergences
    return True, "le corpus publié correspond aux essais vérifiés", []


def write_corpus(index: dict[str, Any], records: list[dict[str, Any]]) -> None:
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(dump_yaml(index), encoding="utf-8")
    expected_paths: set[Path] = set()
    for record in records:
        path = RECORDS_DIR / f"{record['record_id']}.yaml"
        path.write_text(dump_yaml(record), encoding="utf-8")
        expected_paths.add(path.resolve())
    for path in sorted(RECORDS_DIR.glob("*.y*ml")):
        if path.resolve() not in expected_paths:
            path.unlink()
    SFT_EXPORT_PATH.write_text(export_text(records, "sft"), encoding="utf-8")
    PREFERENCE_EXPORT_PATH.write_text(export_text(records, "preference_pair"), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def render_text(result: dict[str, Any]) -> str:
    prefix = "OK" if result["ok"] else "FAIL"
    lines = [
        f"CORPUS {prefix} — {result['detail']} "
        f"({result['records']} enregistrement(s) : {result['sft']} sft, "
        f"{result['preference_pairs']} paire(s))"
    ]
    for item in result["withheld"]:
        lines.append(
            f"  ⚠ anti-fuite [{item['scenario_id']}] — split {item['split']} : "
            f"{item['withheld_records']} enregistrement(s) retenus hors corpus ; {item['reason']}"
        )
    for item in result["errors"]:
        lines.append(f"  ✗ {item['code']} [{item['path']}] — {item['detail']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    index, records, withheld, validation_errors = expected_corpus()
    counts = {
        "records": len(records),
        "sft": index["counts"]["sft"],
        "preference_pairs": index["counts"]["preference_pair"],
        "withheld": withheld,
    }

    if validation_errors:
        result = {
            "checker": CHECKER,
            "ok": False,
            **counts,
            "detail": "validation du bench ou des enregistrements en échec ; corpus non écrit",
            "errors": [item.as_dict() for item in validation_errors],
        }
    elif args.write:
        write_corpus(index, records)
        result = {
            "checker": CHECKER,
            "ok": True,
            **counts,
            "detail": f"écrit {_display(INDEX_PATH)}, {_display(RECORDS_DIR)}/ et {_display(EXPORT_DIR)}/",
            "errors": [],
        }
    elif args.check:
        ok, detail, divergences = check_corpus(index, records)
        result = {
            "checker": CHECKER,
            "ok": ok,
            **counts,
            "detail": detail,
            "errors": divergences,
        }
    else:
        print(dump_yaml(index), end="")
        return 0

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
