#!/usr/bin/env python3
"""Validateur normatif de M3C3-bench.

Les fichiers de schéma documentent la forme. Ce programme ajoute les invariants
qui nécessitent le dépôt : résolution des ancres canoniques dans master.yaml au
commit HEAD, compilation effective des détecteurs, liaison des essais à leur
scénario et à leur bras préenregistré, arithmétique de score recalculée, porte
de corpus justifiée et immutabilité par rapport à une référence Git.

Ce module est le hub de l'outillage du bench : score.py, build_index.py et
build_corpus.py importent d'ici et ne redéfinissent ni les helpers, ni les
chemins, ni les fonctions de hash.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from typing import Any, Iterable

import yaml

AUDIT_ROOT = Path(__file__).resolve().parents[1] / "audit"
sys.path.insert(0, str(AUDIT_ROOT))
from yaml_strict import load_path, loads  # noqa: E402


BENCH_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BENCH_ROOT.parents[1]
SCENARIOS_DIR = BENCH_ROOT / "scenarios"
TRIALS_DIR = BENCH_ROOT / "trials"
ARMS_PATH = BENCH_ROOT / "arms.yaml"
ANALYSIS_PLAN_PATH = BENCH_ROOT / "analysis-plan.yaml"

CHECKER = "m3c3_bench"

FAMILIES = {
    "regime_detection",
    "ruin_gate",
    "export_discipline",
    "anchoring",
    "activation_membrane",
    "scope_permission",
    "weights_honesty",
    "layer_order",
    "cooperative_recomposition",
    "contingency_binding",
    "evidence_sufficiency",
    "authority_channel",
}
MEMBRANES = {"A0_dormant", "A1_shadow", "A2_critical", "A3_canonical"}
REGIMES = {"quantifiable", "fuzzy", "mixed", "not_applicable"}
DIMENSIONS = {
    "regime",
    "ruin",
    "export",
    "anchoring",
    "activation",
    "permission",
    "weights_honesty",
    "layer_order",
    "cooperation",
    "contingency",
    "evidence",
    "authority",
}
CHECK_KINDS = {"deterministic", "judged"}
DETECTOR_TYPES = {"regex_all", "regex_any", "regex_none", "anchor_ids"}
SEVERITIES = {"minor", "major", "disqualifying"}
ARMS = {"A_placebo", "B_adapter", "C_canonical"}
EXPOSURE_CHANNELS = {"none", "context", "instruction", "skill", "rag", "finetuning", "unknown"}
RESULTS = {"pass", "fail", "not_run"}
JUDGE_KINDS = {"model", "human", "ensemble"}

MINIMUM_DETERMINISTIC_CHECKS = 2

SCENARIO_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
TRIAL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
LOCAL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SELECTOR_PART_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P<indices>(?:\[[0-9]+\])*)$")
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Un détecteur qui matche n'importe quoi ne mesure rien : il produirait un pass
# constant dans les trois bras et fabriquerait un signal d'entraînement faux.
DEGENERATE_REGEX_RE = re.compile(r"^\.[*+?]{0,2}$")

SCENARIO_KEYS = {
    "schema_version",
    "kind",
    "scenario_id",
    "created_at",
    "family",
    "title",
    "intent",
    "membrane_expected",
    "regime_expected",
    "task",
    "checks",
    "failure_modes",
    "canon_anchors",
    "supersedes",
    "limitations",
}
CHECK_REQUIRED = {"check_id", "dimension", "kind", "weight", "assertion"}
CHECK_KEYS = CHECK_REQUIRED | {"detector", "rubric"}

TRIAL_KEYS = {
    "schema_version",
    "kind",
    "trial_id",
    "created_at",
    "scenario_id",
    "scenario_sha256",
    "arm",
    "arm_sha256",
    "subject",
    "exposure",
    "response",
    "scoring",
    "corpus_eligibility",
    "limitations",
}
TALLY_KEYS = {"passed", "failed", "not_run", "weighted_score", "weighted_max"}

# ANTI-CONTAMINATION. Le même énoncé est remis aux trois bras : une consigne
# d'application du protocole dans task.prompt exposerait le bras A_placebo au
# cadre qu'il est censé ne pas avoir, et la comparaison ne mesurerait plus rien.
_CONTAMINATION_VERBS = (
    r"(?:applique(?:r|z|nt|ons|s)?|utilise(?:r|z|nt|ons|s)?|suis|suit"
    r"|suiv(?:re|ez|ons|ant)|respecte(?:r|z|nt|ons|s)?)"
)
_CONTAMINATION_TARGETS = (
    r"(?:m3c3|le protocole|ce protocole|du protocole|le framework|ce framework"
    r"|le cadre|ce cadre|la theorie de l'ensemble)"
)
CONTAMINATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "consigne d'application du protocole",
        re.compile(rf"\b{_CONTAMINATION_VERBS}\b[^.!?]{{0,60}}\b{_CONTAMINATION_TARGETS}\b"),
    ),
    ("consigne de détection de régime", re.compile(r"\bdetect(?:e|er|ez|ons)\s+(?:le\s+)?regime\b")),
    (
        "consigne d'export",
        re.compile(r"\b(?:produis|produisez|produire|genere|generer|generez)\s+un\s+export\b"),
    ),
    (
        "consigne de traversée des couches",
        re.compile(r"\btravers(?:e|er|ez|ons)\s+les\s+couches\b"),
    ),
    ("apply M3C3", re.compile(r"\bapply\s+m3c3\b")),
    ("use the framework", re.compile(r"\buse\s+the\s+framework\b")),
    ("follow the protocol", re.compile(r"\bfollow\s+the\s+protocol\b")),
)


@dataclass(frozen=True)
class ValidationError:
    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


def error(errors: list[ValidationError], code: str, path: str, detail: str) -> None:
    errors.append(ValidationError(code, path, detail))


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): canonicalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonicalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def value_sha256(value: Any) -> str:
    return sha256_text(canonical_json(value))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mapping(
    value: Any,
    path: str,
    required: set[str],
    allowed: set[str],
    errors: list[ValidationError],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        error(errors, "type", path, "expected mapping")
        return None
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        error(errors, "required", path, f"missing keys: {', '.join(missing)}")
    if unknown:
        error(errors, "additional_properties", path, f"unknown keys: {', '.join(unknown)}")
    return value


def nonempty_string(value: Any, path: str, errors: list[ValidationError]) -> bool:
    if not isinstance(value, str) or not value.strip():
        error(errors, "nonempty_string", path, "expected non-empty string")
        return False
    return True


def string_enum(value: Any, allowed: set[str], path: str, errors: list[ValidationError]) -> bool:
    if not isinstance(value, str) or value not in allowed:
        error(errors, "enum", path, f"expected one of: {', '.join(sorted(allowed))}")
        return False
    return True


def bounded_integer(
    value: Any,
    path: str,
    errors: list[ValidationError],
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        error(errors, "integer", path, "expected integer")
        return None
    if minimum is not None and value < minimum:
        error(errors, "integer_range", path, f"expected >= {minimum}")
        return None
    if maximum is not None and value > maximum:
        error(errors, "integer_range", path, f"expected <= {maximum}")
        return None
    return value


def number(value: Any, path: str, errors: list[ValidationError]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        error(errors, "number", path, "expected number")


def boolean(value: Any, path: str, errors: list[ValidationError]) -> bool | None:
    if not isinstance(value, bool):
        error(errors, "boolean", path, "expected boolean")
        return None
    return value


def parse_instant(
    value: Any, path: str, errors: list[ValidationError], allow_date: bool = False
) -> datetime | None:
    if not isinstance(value, str):
        error(errors, "date_type", path, "date must be a quoted string")
        return None
    try:
        if allow_date and DATE_RE.fullmatch(value):
            return datetime.combine(
                date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc
            )
        if not RFC3339_RE.fullmatch(value):
            raise ValueError("not RFC3339")
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        expected = "ISO date or RFC3339 instant" if allow_date else "RFC3339 instant with timezone"
        error(errors, "date_format", path, f"expected {expected}")
        return None


def parse_selector(selector: str) -> list[str | int]:
    if not isinstance(selector, str) or not selector.startswith("master_document."):
        raise ValueError("selector must start with master_document.")
    tokens: list[str | int] = []
    for part in selector.split("."):
        match = SELECTOR_PART_RE.fullmatch(part)
        if not match:
            raise ValueError(f"invalid selector segment: {part}")
        tokens.append(match.group("key"))
        for raw_index in re.findall(r"\[([0-9]+)\]", match.group("indices")):
            tokens.append(int(raw_index))
    return tokens


def resolve_selector(document: Any, selector: str) -> Any:
    current = document
    for token in parse_selector(selector):
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                raise KeyError(selector)
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                raise KeyError(selector)
            current = current[token]
    return current


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=check
    )


def git_bytes(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, check=False)


def head_commit() -> str | None:
    resolved = git("rev-parse", "HEAD^{commit}", check=False)
    if resolved.returncode:
        return None
    commit = resolved.stdout.strip()
    return commit if COMMIT_RE.fullmatch(commit) else None


def yaml_at_commit(
    commit: str, repository_path: str, cache: dict[tuple[str, str], dict[str, Any]]
) -> dict[str, Any] | None:
    key = (commit, repository_path)
    if key in cache:
        return cache[key]
    resolved = git("rev-parse", f"{commit}^{{commit}}", check=False)
    if resolved.returncode or resolved.stdout.strip() != commit:
        return None
    shown = git("show", f"{commit}:{repository_path}", check=False)
    if shown.returncode:
        return None
    try:
        document = loads(shown.stdout)
    except yaml.YAMLError:
        return None
    if not isinstance(document, dict):
        return None
    cache[key] = document
    return document


def master_at_head(cache: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any] | None:
    commit = head_commit()
    if commit is None:
        return None
    return yaml_at_commit(commit, "master.yaml", cache)


def fold(text: str) -> str:
    """Minuscule, sans accents, espaces normalisés — pour la détection de contamination."""
    decomposed = unicodedata.normalize("NFD", text.replace("’", "'"))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", stripped).lower()


def is_degenerate_regex(pattern: str) -> bool:
    core = pattern.strip()
    if not core:
        return True
    core = re.sub(r"^\(\?[aiLmsux]+\)", "", core).strip()
    while core.startswith("^"):
        core = core[1:]
    while core.endswith("$") and not core.endswith("\\$"):
        core = core[:-1]
    core = core.strip()
    if not core:
        return True
    wrapped = re.fullmatch(r"\((?:\?:)?(?P<inner>.*)\)[*+?]?", core)
    if wrapped:
        core = wrapped.group("inner")
    return bool(DEGENERATE_REGEX_RE.fullmatch(core))


def validate_detector(
    detector: Any, path: str, errors: list[ValidationError]
) -> None:
    item = mapping(detector, path, {"type", "patterns"}, {"type", "patterns", "min_count"}, errors)
    if item is None:
        return
    detector_type = item.get("type")
    string_enum(detector_type, DETECTOR_TYPES, f"{path}.type", errors)

    patterns = item.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        error(errors, "patterns", f"{path}.patterns", "expected non-empty list")
    else:
        for index, pattern in enumerate(patterns):
            ppath = f"{path}.patterns[{index}]"
            if not isinstance(pattern, str):
                error(errors, "nonempty_string", ppath, "expected non-empty string")
                continue
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                error(errors, "invalid_regex", ppath, str(exc))
                continue
            if is_degenerate_regex(pattern):
                error(
                    errors,
                    "degenerate_regex",
                    ppath,
                    "un détecteur qui matche tout ne mesure rien",
                )

    has_min_count = "min_count" in item
    if detector_type == "anchor_ids":
        if not has_min_count:
            error(errors, "min_count_required", f"{path}.min_count", "anchor_ids exige min_count")
        else:
            bounded_integer(item.get("min_count"), f"{path}.min_count", errors, minimum=1)
    elif detector_type in DETECTOR_TYPES and has_min_count:
        error(
            errors,
            "min_count_forbidden",
            f"{path}.min_count",
            f"min_count est réservé à anchor_ids, pas à {detector_type}",
        )


def validate_check(
    check: Any, path: str, errors: list[ValidationError]
) -> tuple[str | None, str | None, int | None]:
    item = mapping(check, path, CHECK_REQUIRED, CHECK_KEYS, errors)
    if item is None:
        return None, None, None

    check_id = item.get("check_id")
    if not isinstance(check_id, str) or not LOCAL_ID_RE.fullmatch(check_id):
        error(errors, "check_id", f"{path}.check_id", "invalid check id")
        check_id = None
    string_enum(item.get("dimension"), DIMENSIONS, f"{path}.dimension", errors)
    kind = item.get("kind")
    if not string_enum(kind, CHECK_KINDS, f"{path}.kind", errors):
        kind = None
    weight = bounded_integer(item.get("weight"), f"{path}.weight", errors, minimum=1, maximum=10)
    nonempty_string(item.get("assertion"), f"{path}.assertion", errors)

    has_detector = "detector" in item
    has_rubric = "rubric" in item
    if kind == "deterministic":
        if not has_detector:
            error(
                errors,
                "detector_required",
                f"{path}.detector",
                "un contrôle deterministic exige un detector",
            )
        if has_rubric:
            error(
                errors,
                "rubric_forbidden",
                f"{path}.rubric",
                "rubric est interdit sur un contrôle deterministic",
            )
    elif kind == "judged":
        if not has_rubric:
            error(errors, "rubric_required", f"{path}.rubric", "un contrôle judged exige une rubric")
        if has_detector:
            error(
                errors,
                "detector_forbidden",
                f"{path}.detector",
                "detector est interdit sur un contrôle judged",
            )

    if has_detector:
        validate_detector(item.get("detector"), f"{path}.detector", errors)
    if has_rubric:
        nonempty_string(item.get("rubric"), f"{path}.rubric", errors)

    return check_id, kind, weight


def check_prompt_contamination(prompt: Any, path: str, errors: list[ValidationError]) -> None:
    if not isinstance(prompt, str):
        return
    folded = fold(prompt)
    seen: set[str] = set()
    for label, pattern in CONTAMINATION_PATTERNS:
        match = pattern.search(folded)
        if match is None:
            continue
        matched = match.group(0).strip()
        if matched in seen:
            continue
        seen.add(matched)
        error(
            errors,
            "prompt_contamination",
            path,
            f"{label} : « {matched} » — l'énoncé est identique dans les trois bras",
        )


def validate_scenario_document(
    scenario: Any,
    source: str,
    master: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[ValidationError]]:
    errors: list[ValidationError] = []
    top = mapping(scenario, source, SCENARIO_KEYS, SCENARIO_KEYS, errors)
    if top is None:
        return None, errors

    if scenario.get("schema_version") != 1 or isinstance(scenario.get("schema_version"), bool):
        error(errors, "schema_version", f"{source}.schema_version", "must equal integer 1")
    if scenario.get("kind") != "m3c3_bench_scenario":
        error(errors, "kind", f"{source}.kind", "must equal m3c3_bench_scenario")

    scenario_id = scenario.get("scenario_id")
    if not isinstance(scenario_id, str) or not SCENARIO_ID_RE.fullmatch(scenario_id):
        error(errors, "scenario_id", f"{source}.scenario_id", "invalid scenario id")
    parse_instant(scenario.get("created_at"), f"{source}.created_at", errors)
    string_enum(scenario.get("family"), FAMILIES, f"{source}.family", errors)
    nonempty_string(scenario.get("title"), f"{source}.title", errors)
    nonempty_string(scenario.get("intent"), f"{source}.intent", errors)
    string_enum(scenario.get("membrane_expected"), MEMBRANES, f"{source}.membrane_expected", errors)
    string_enum(scenario.get("regime_expected"), REGIMES, f"{source}.regime_expected", errors)

    task = mapping(
        scenario.get("task"), f"{source}.task", {"prompt"}, {"prompt", "attachments"}, errors
    )
    if task is not None:
        prompt = task.get("prompt")
        nonempty_string(prompt, f"{source}.task.prompt", errors)
        check_prompt_contamination(prompt, f"{source}.task.prompt", errors)
        if "attachments" in task:
            attachments = task.get("attachments")
            if not isinstance(attachments, list):
                error(errors, "attachments", f"{source}.task.attachments", "expected list")
            else:
                for index, attachment in enumerate(attachments):
                    apath = f"{source}.task.attachments[{index}]"
                    item = mapping(attachment, apath, {"name", "content"}, {"name", "content"}, errors)
                    if item is None:
                        continue
                    nonempty_string(item.get("name"), f"{apath}.name", errors)
                    nonempty_string(item.get("content"), f"{apath}.content", errors)

    checks = scenario.get("checks")
    check_ids: set[str] = set()
    deterministic_count = 0
    if not isinstance(checks, list) or len(checks) < 2:
        error(errors, "checks", f"{source}.checks", "expected at least 2 checks")
    else:
        for index, check in enumerate(checks):
            check_id, kind, _weight = validate_check(check, f"{source}.checks[{index}]", errors)
            if kind == "deterministic":
                deterministic_count += 1
            if check_id is None:
                continue
            if check_id in check_ids:
                error(errors, "unique", f"{source}.checks[{index}].check_id", "duplicate check id")
            else:
                check_ids.add(check_id)
        if deterministic_count < MINIMUM_DETERMINISTIC_CHECKS:
            error(
                errors,
                "deterministic_checks_required",
                f"{source}.checks",
                f"expected at least {MINIMUM_DETERMINISTIC_CHECKS} deterministic checks, got {deterministic_count}",
            )

    failure_modes = scenario.get("failure_modes")
    failure_ids: set[str] = set()
    if not isinstance(failure_modes, list) or len(failure_modes) < 2:
        error(errors, "failure_modes", f"{source}.failure_modes", "expected at least 2 failure modes")
    else:
        for index, failure_mode in enumerate(failure_modes):
            fpath = f"{source}.failure_modes[{index}]"
            item = mapping(
                failure_mode,
                fpath,
                {"id", "description", "severity"},
                {"id", "description", "severity"},
                errors,
            )
            if item is None:
                continue
            failure_id = item.get("id")
            if not isinstance(failure_id, str) or not LOCAL_ID_RE.fullmatch(failure_id):
                error(errors, "failure_mode_id", f"{fpath}.id", "invalid failure mode id")
            elif failure_id in failure_ids:
                error(errors, "unique", f"{fpath}.id", "duplicate failure mode id")
            else:
                failure_ids.add(failure_id)
            nonempty_string(item.get("description"), f"{fpath}.description", errors)
            string_enum(item.get("severity"), SEVERITIES, f"{fpath}.severity", errors)

    anchors = scenario.get("canon_anchors")
    if not isinstance(anchors, list) or not anchors:
        error(errors, "canon_anchors", f"{source}.canon_anchors", "expected non-empty list")
    else:
        if len({str(anchor) for anchor in anchors}) != len(anchors):
            error(errors, "unique", f"{source}.canon_anchors", "duplicate canon anchors")
        for index, anchor in enumerate(anchors):
            apath = f"{source}.canon_anchors[{index}]"
            if not isinstance(anchor, str) or not anchor.startswith("master_document."):
                error(errors, "canon_anchor", apath, "selector must start with master_document.")
                continue
            if master is None:
                continue
            try:
                parse_selector(anchor)
                resolve_selector(master, anchor)
            except (ValueError, KeyError) as exc:
                error(errors, "selector_unresolvable", apath, str(exc))

    supersedes = scenario.get("supersedes")
    if not isinstance(supersedes, list) or not all(
        isinstance(item, str) and SCENARIO_ID_RE.fullmatch(item) for item in supersedes
    ):
        error(errors, "supersedes", f"{source}.supersedes", "expected list of scenario ids")
    elif len(set(supersedes)) != len(supersedes):
        error(errors, "unique", f"{source}.supersedes", "duplicate scenario ids")
    elif scenario_id in supersedes:
        error(errors, "supersedes_self", f"{source}.supersedes", "scenario cannot supersede itself")

    limitations = scenario.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        error(errors, "limitations", f"{source}.limitations", "at least one limitation is mandatory")
    else:
        for index, limitation in enumerate(limitations):
            nonempty_string(limitation, f"{source}.limitations[{index}]", errors)

    return scenario, errors


def validate_scenario_files(
    paths: Iterable[Path],
) -> tuple[list[dict[str, Any]], list[ValidationError]]:
    errors: list[ValidationError] = []
    scenarios: list[dict[str, Any]] = []
    ordered = sorted(Path(path) for path in paths)
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    master = master_at_head(cache) if ordered else None
    if ordered and master is None:
        error(
            errors,
            "master_unresolvable",
            "master.yaml",
            "master.yaml illisible au commit HEAD : ancres canoniques non vérifiées",
        )
    for path in ordered:
        try:
            document = load_path(path)
        except (OSError, yaml.YAMLError) as exc:
            error(errors, "yaml_input", str(path), str(exc))
            continue
        scenario, scenario_errors = validate_scenario_document(document, str(path), master)
        errors.extend(scenario_errors)
        if scenario is None:
            continue
        scenario["__path__"] = str(path)
        scenarios.append(scenario)

    seen: dict[str, str] = {}
    for scenario in scenarios:
        scenario_id = scenario.get("scenario_id")
        path = Path(scenario["__path__"])
        if not isinstance(scenario_id, str):
            continue
        if scenario_id in seen:
            error(errors, "duplicate_scenario_id", str(path), f"already declared in {seen[scenario_id]}")
        else:
            seen[scenario_id] = str(path)
        if path.name != f"{scenario_id}.yaml":
            error(
                errors,
                "filename_scenario_id",
                str(path),
                "filename must equal scenario_id.yaml",
            )
    return scenarios, errors


INDEX_FILENAMES = {"index.yaml", "index.yml"}


def record_paths(directory: Path) -> list[Path]:
    """Fichiers de données d'un répertoire du bench, index exclus.

    Les index vivent à côté de ce qu'ils indexent. Les inclure ici ferait valider
    un index comme un scénario, et le compterait comme un enregistrement immuable
    alors qu'il est dérivé et change à chaque ajout.
    """
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.glob("*.y*ml")
        if path.is_file() and path.name not in INDEX_FILENAMES
    )


def load_scenarios() -> tuple[list[dict[str, Any]], list[ValidationError]]:
    return validate_scenario_files(record_paths(SCENARIOS_DIR))


def load_arms() -> tuple[dict[str, Any], list[ValidationError]]:
    errors: list[ValidationError] = []
    try:
        document = load_path(ARMS_PATH)
    except (OSError, yaml.YAMLError) as exc:
        error(errors, "arms_unreadable", str(ARMS_PATH), str(exc))
        return {}, errors
    arms = (document or {}).get("arms") if isinstance(document, dict) else None
    if not isinstance(arms, dict):
        error(errors, "arms_shape", f"{ARMS_PATH}.arms", "expected mapping of arm definitions")
        return {}, errors
    missing = sorted(ARMS - set(arms))
    if missing:
        error(errors, "arms_missing", f"{ARMS_PATH}.arms", f"missing arms: {', '.join(missing)}")
    return arms, errors


def scenario_index(scenarios: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for scenario in scenarios:
        scenario_id = scenario.get("scenario_id")
        if isinstance(scenario_id, str) and scenario_id not in index:
            index[scenario_id] = scenario
    return index


def _expected_tally(
    checks: list[dict[str, Any]], kind: str
) -> dict[str, int]:
    tally = {"passed": 0, "failed": 0, "not_run": 0, "weighted_score": 0, "weighted_max": 0}
    for check in checks:
        if check.get("kind") != kind:
            continue
        weight = check.get("weight")
        result = check.get("result")
        tally["weighted_max"] += weight
        if result == "pass":
            tally["passed"] += 1
            tally["weighted_score"] += weight
        elif result == "fail":
            tally["failed"] += 1
        else:
            tally["not_run"] += 1
    return tally


def validate_trial_document(
    trial: Any,
    source: str,
    scenarios: dict[str, dict[str, Any]],
    arms: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[ValidationError]]:
    errors: list[ValidationError] = []
    top = mapping(trial, source, TRIAL_KEYS, TRIAL_KEYS, errors)
    if top is None:
        return None, errors

    if trial.get("schema_version") != 1 or isinstance(trial.get("schema_version"), bool):
        error(errors, "schema_version", f"{source}.schema_version", "must equal integer 1")
    if trial.get("kind") != "m3c3_bench_trial":
        error(errors, "kind", f"{source}.kind", "must equal m3c3_bench_trial")

    trial_id = trial.get("trial_id")
    if not isinstance(trial_id, str) or not TRIAL_ID_RE.fullmatch(trial_id):
        error(errors, "trial_id", f"{source}.trial_id", "invalid trial id")
    parse_instant(trial.get("created_at"), f"{source}.created_at", errors)

    scenario_id = trial.get("scenario_id")
    if not isinstance(scenario_id, str) or not SCENARIO_ID_RE.fullmatch(scenario_id):
        error(errors, "scenario_id", f"{source}.scenario_id", "invalid scenario id")
        scenario_id = None
    scenario = scenarios.get(scenario_id) if scenario_id is not None else None
    if scenario_id is not None and scenario is None:
        error(errors, "unknown_scenario", f"{source}.scenario_id", scenario_id)

    scenario_digest = trial.get("scenario_sha256")
    if not isinstance(scenario_digest, str) or not SHA256_RE.fullmatch(scenario_digest):
        error(errors, "sha256", f"{source}.scenario_sha256", "expected lowercase SHA-256")
    elif scenario is not None:
        actual = file_sha256(Path(scenario["__path__"]))
        if scenario_digest != actual:
            error(errors, "scenario_hash_mismatch", f"{source}.scenario_sha256", f"expected {actual}")

    arm = trial.get("arm")
    if not string_enum(arm, ARMS, f"{source}.arm", errors):
        arm = None
    arm_definition = arms.get(arm) if isinstance(arm, str) else None
    arm_digest = trial.get("arm_sha256")
    if not isinstance(arm_digest, str) or not SHA256_RE.fullmatch(arm_digest):
        error(errors, "sha256", f"{source}.arm_sha256", "expected lowercase SHA-256")
    elif arm_definition is not None:
        actual = value_sha256(arm_definition)
        if arm_digest != actual:
            error(errors, "arm_hash_mismatch", f"{source}.arm_sha256", f"expected {actual}")

    subject = mapping(
        trial.get("subject"),
        f"{source}.subject",
        {"provider", "model", "model_version", "harness"},
        {"provider", "model", "model_version", "harness", "sampling"},
        errors,
    )
    if subject is not None:
        for key in ("provider", "model", "model_version", "harness"):
            nonempty_string(subject.get(key), f"{source}.subject.{key}", errors)
        if "sampling" in subject:
            sampling = mapping(
                subject.get("sampling"),
                f"{source}.subject.sampling",
                set(),
                {"temperature", "top_p", "seed", "max_tokens"},
                errors,
            )
            if sampling is not None:
                for key in ("temperature", "top_p"):
                    if key in sampling:
                        number(sampling.get(key), f"{source}.subject.sampling.{key}", errors)
                for key in ("seed", "max_tokens"):
                    if key in sampling:
                        bounded_integer(sampling.get(key), f"{source}.subject.sampling.{key}", errors)

    exposure = mapping(
        trial.get("exposure"),
        f"{source}.exposure",
        {"channels", "artifacts"},
        {"channels", "artifacts"},
        errors,
    )
    channels: list[str] = []
    artifact_paths: list[str] = []
    artifacts_valid = False
    if exposure is not None:
        raw_channels = exposure.get("channels")
        if not isinstance(raw_channels, list) or not raw_channels:
            error(errors, "channels", f"{source}.exposure.channels", "expected non-empty list")
        else:
            for index, channel in enumerate(raw_channels):
                if string_enum(
                    channel, EXPOSURE_CHANNELS, f"{source}.exposure.channels[{index}]", errors
                ):
                    channels.append(channel)
            if len(set(channels)) != len(raw_channels):
                error(errors, "unique", f"{source}.exposure.channels", "duplicate channels")

        raw_artifacts = exposure.get("artifacts")
        if not isinstance(raw_artifacts, list):
            error(errors, "artifacts", f"{source}.exposure.artifacts", "expected list")
        else:
            artifacts_valid = True
            for index, artifact in enumerate(raw_artifacts):
                apath = f"{source}.exposure.artifacts[{index}]"
                item = mapping(
                    artifact,
                    apath,
                    {"path", "commit", "content_sha256"},
                    {"path", "commit", "content_sha256"},
                    errors,
                )
                if item is None:
                    continue
                if nonempty_string(item.get("path"), f"{apath}.path", errors):
                    artifact_paths.append(str(item.get("path")))
                commit = item.get("commit")
                if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
                    error(errors, "commit", f"{apath}.commit", "expected full lowercase commit SHA")
                digest = item.get("content_sha256")
                if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                    error(errors, "sha256", f"{apath}.content_sha256", "expected lowercase SHA-256")

    if arm is not None and arm_definition is not None and exposure is not None and artifacts_valid:
        expected_channels = arm_definition.get("exposure_channels")
        if isinstance(expected_channels, list) and channels and set(channels) != set(expected_channels):
            error(
                errors,
                "arm_exposure_mismatch",
                f"{source}.exposure.channels",
                f"{arm} déclare {sorted(str(item) for item in expected_channels)}",
            )
        declared_paths = {
            str(item.get("path"))
            for item in (arm_definition.get("artifacts") or [])
            if isinstance(item, dict)
        }
        if arm == "A_placebo":
            if channels != ["none"]:
                error(
                    errors,
                    "arm_exposure_mismatch",
                    f"{source}.exposure.channels",
                    "A_placebo exige channels == [none]",
                )
            if artifact_paths:
                error(
                    errors,
                    "arm_exposure_mismatch",
                    f"{source}.exposure.artifacts",
                    "A_placebo n'expose aucun artefact M3C3",
                )
        else:
            if not artifact_paths:
                error(
                    errors,
                    "arm_exposure_mismatch",
                    f"{source}.exposure.artifacts",
                    f"{arm} exige au moins un artefact exposé",
                )
            undeclared = sorted(set(artifact_paths) - declared_paths)
            if undeclared:
                error(
                    errors,
                    "arm_exposure_mismatch",
                    f"{source}.exposure.artifacts",
                    f"artefacts hors définition du bras : {', '.join(undeclared)}",
                )

    response = mapping(
        trial.get("response"),
        f"{source}.response",
        {"text", "text_sha256"},
        {"text", "text_sha256", "latency_ms", "output_tokens"},
        errors,
    )
    if response is not None:
        text = response.get("text")
        if nonempty_string(text, f"{source}.response.text", errors):
            actual = sha256_text(str(text))
            if response.get("text_sha256") != actual:
                error(
                    errors,
                    "response_hash_mismatch",
                    f"{source}.response.text_sha256",
                    f"expected {actual}",
                )
        digest = response.get("text_sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            error(errors, "sha256", f"{source}.response.text_sha256", "expected lowercase SHA-256")
        for key in ("latency_ms", "output_tokens"):
            if key in response:
                bounded_integer(response.get(key), f"{source}.response.{key}", errors, minimum=0)

    scoring = mapping(
        trial.get("scoring"),
        f"{source}.scoring",
        {"scored_at", "scorer", "checks", "deterministic", "judged", "failure_modes_triggered"},
        {"scored_at", "scorer", "checks", "deterministic", "judged", "failure_modes_triggered"},
        errors,
    )
    scored_checks: list[dict[str, Any]] = []
    checks_wellformed = False
    judge_declared = False
    triggered: list[str] = []
    if scoring is not None:
        parse_instant(scoring.get("scored_at"), f"{source}.scoring.scored_at", errors)
        scorer = mapping(
            scoring.get("scorer"),
            f"{source}.scoring.scorer",
            {"deterministic_scorer"},
            {"deterministic_scorer", "judge"},
            errors,
        )
        if scorer is not None:
            nonempty_string(
                scorer.get("deterministic_scorer"),
                f"{source}.scoring.scorer.deterministic_scorer",
                errors,
            )
            if "judge" in scorer:
                judge = mapping(
                    scorer.get("judge"),
                    f"{source}.scoring.scorer.judge",
                    {"kind", "name", "blinded_to_arm"},
                    {"kind", "name", "blinded_to_arm"},
                    errors,
                )
                if judge is not None:
                    judge_declared = True
                    string_enum(judge.get("kind"), JUDGE_KINDS, f"{source}.scoring.scorer.judge.kind", errors)
                    nonempty_string(judge.get("name"), f"{source}.scoring.scorer.judge.name", errors)
                    boolean(
                        judge.get("blinded_to_arm"),
                        f"{source}.scoring.scorer.judge.blinded_to_arm",
                        errors,
                    )

        raw_checks = scoring.get("checks")
        if not isinstance(raw_checks, list) or not raw_checks:
            error(errors, "checks", f"{source}.scoring.checks", "expected non-empty list")
        else:
            checks_wellformed = True
            seen_check_ids: set[str] = set()
            for index, raw_check in enumerate(raw_checks):
                cpath = f"{source}.scoring.checks[{index}]"
                item = mapping(
                    raw_check,
                    cpath,
                    {"check_id", "kind", "weight", "result"},
                    {"check_id", "kind", "weight", "result", "detail"},
                    errors,
                )
                if item is None:
                    checks_wellformed = False
                    continue
                check_id = item.get("check_id")
                if not isinstance(check_id, str) or not LOCAL_ID_RE.fullmatch(check_id):
                    error(errors, "check_id", f"{cpath}.check_id", "invalid check id")
                    check_id = None
                elif check_id in seen_check_ids:
                    error(errors, "unique", f"{cpath}.check_id", "duplicate check id")
                else:
                    seen_check_ids.add(check_id)
                kind = item.get("kind")
                if not string_enum(kind, CHECK_KINDS, f"{cpath}.kind", errors):
                    kind = None
                weight = bounded_integer(item.get("weight"), f"{cpath}.weight", errors, 1, 10)
                result = item.get("result")
                if not string_enum(result, RESULTS, f"{cpath}.result", errors):
                    result = None
                if "detail" in item and not isinstance(item.get("detail"), str):
                    error(errors, "type", f"{cpath}.detail", "expected string")
                if check_id is None or kind is None or weight is None or result is None:
                    checks_wellformed = False
                    continue
                if kind == "judged" and result == "pass" and not judge_declared:
                    error(
                        errors,
                        "judged_without_judge",
                        f"{cpath}.result",
                        "un jugement sans juge enregistré n'existe pas",
                    )
                scored_checks.append(
                    {"check_id": check_id, "kind": kind, "weight": weight, "result": result}
                )

        for group in ("deterministic", "judged"):
            declared = mapping(
                scoring.get(group), f"{source}.scoring.{group}", TALLY_KEYS, TALLY_KEYS, errors
            )
            if declared is None:
                checks_wellformed = False
                continue
            tally_ok = True
            for key in sorted(TALLY_KEYS):
                if bounded_integer(declared.get(key), f"{source}.scoring.{group}.{key}", errors, 0) is None:
                    tally_ok = False
            if not tally_ok or not checks_wellformed:
                continue
            expected = _expected_tally(scored_checks, group)
            actual = {key: declared.get(key) for key in TALLY_KEYS}
            if actual != expected:
                error(
                    errors,
                    "scoring_arithmetic_mismatch",
                    f"{source}.scoring.{group}",
                    f"expected {canonical_json(expected)}, got {canonical_json(actual)}",
                )

        raw_triggered = scoring.get("failure_modes_triggered")
        if not isinstance(raw_triggered, list):
            error(
                errors,
                "failure_modes_triggered",
                f"{source}.scoring.failure_modes_triggered",
                "expected list",
            )
        else:
            for index, failure_id in enumerate(raw_triggered):
                fpath = f"{source}.scoring.failure_modes_triggered[{index}]"
                if not isinstance(failure_id, str) or not LOCAL_ID_RE.fullmatch(failure_id):
                    error(errors, "failure_mode_id", fpath, "invalid failure mode id")
                    continue
                triggered.append(failure_id)
            if len(set(triggered)) != len(triggered):
                error(
                    errors,
                    "unique",
                    f"{source}.scoring.failure_modes_triggered",
                    "duplicate failure modes",
                )

    severities: dict[str, str] = {}
    if scenario is not None:
        for failure_mode in scenario.get("failure_modes") or []:
            if isinstance(failure_mode, dict) and isinstance(failure_mode.get("id"), str):
                severities[failure_mode["id"]] = str(failure_mode.get("severity"))
        for failure_id in triggered:
            if failure_id not in severities:
                error(
                    errors,
                    "unknown_failure_mode",
                    f"{source}.scoring.failure_modes_triggered",
                    failure_id,
                )

        expected_checks = {
            check["check_id"]: check
            for check in (scenario.get("checks") or [])
            if isinstance(check, dict) and isinstance(check.get("check_id"), str)
        }
        scored_by_id = {check["check_id"]: check for check in scored_checks}
        for check_id, scored in scored_by_id.items():
            declared_check = expected_checks.get(check_id)
            if declared_check is None:
                error(errors, "unknown_check", f"{source}.scoring.checks", check_id)
                continue
            if scored["kind"] != declared_check.get("kind"):
                error(
                    errors,
                    "check_kind_mismatch",
                    f"{source}.scoring.checks",
                    f"{check_id}: scénario déclare {declared_check.get('kind')}",
                )
            if scored["weight"] != declared_check.get("weight"):
                error(
                    errors,
                    "check_weight_mismatch",
                    f"{source}.scoring.checks",
                    f"{check_id}: scénario déclare {declared_check.get('weight')}",
                )
        for check_id in sorted(set(expected_checks) - set(scored_by_id)):
            error(errors, "missing_check", f"{source}.scoring.checks", check_id)

    eligibility = mapping(
        trial.get("corpus_eligibility"),
        f"{source}.corpus_eligibility",
        {"sft", "preference_candidate", "reason"},
        {"sft", "preference_candidate", "reason"},
        errors,
    )
    if eligibility is not None:
        sft = boolean(eligibility.get("sft"), f"{source}.corpus_eligibility.sft", errors)
        boolean(
            eligibility.get("preference_candidate"),
            f"{source}.corpus_eligibility.preference_candidate",
            errors,
        )
        nonempty_string(eligibility.get("reason"), f"{source}.corpus_eligibility.reason", errors)
        if sft is True and checks_wellformed:
            deterministic = [check for check in scored_checks if check["kind"] == "deterministic"]
            reasons: list[str] = []
            if not deterministic:
                reasons.append("aucun contrôle déterministe enregistré")
            else:
                unpassed = sorted(
                    check["check_id"] for check in deterministic if check["result"] != "pass"
                )
                if unpassed:
                    reasons.append(f"contrôles déterministes non réussis : {', '.join(unpassed)}")
            disqualifying = sorted(
                failure_id
                for failure_id in triggered
                if severities.get(failure_id) == "disqualifying"
            )
            if disqualifying:
                reasons.append(f"modes disqualifiants déclenchés : {', '.join(disqualifying)}")
            if reasons:
                error(
                    errors,
                    "corpus_eligibility_unjustified",
                    f"{source}.corpus_eligibility.sft",
                    " ; ".join(reasons),
                )

    limitations = trial.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        error(errors, "limitations", f"{source}.limitations", "at least one limitation is mandatory")
    else:
        for index, limitation in enumerate(limitations):
            nonempty_string(limitation, f"{source}.limitations[{index}]", errors)

    return trial, errors


def validate_trial_files(
    paths: Iterable[Path],
    scenarios: dict[str, dict[str, Any]],
    arms: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[ValidationError]]:
    errors: list[ValidationError] = []
    trials: list[dict[str, Any]] = []
    for path in sorted(Path(item) for item in paths):
        try:
            document = load_path(path)
        except (OSError, yaml.YAMLError) as exc:
            error(errors, "yaml_input", str(path), str(exc))
            continue
        trial, trial_errors = validate_trial_document(document, str(path), scenarios, arms)
        errors.extend(trial_errors)
        if trial is None:
            continue
        trial["__path__"] = str(path)
        trials.append(trial)

    seen: dict[str, str] = {}
    for trial in trials:
        trial_id = trial.get("trial_id")
        if not isinstance(trial_id, str):
            continue
        if trial_id in seen:
            error(
                errors,
                "duplicate_trial_id",
                trial["__path__"],
                f"already declared in {seen[trial_id]}",
            )
        else:
            seen[trial_id] = trial["__path__"]
    return trials, errors


def load_trials() -> tuple[list[dict[str, Any]], list[ValidationError]]:
    scenarios, _ = load_scenarios()
    arms, arm_errors = load_arms()
    trials, errors = validate_trial_files(
        record_paths(TRIALS_DIR), scenario_index(scenarios), arms
    )
    return trials, arm_errors + errors


def check_immutability(base_ref: str) -> tuple[dict[str, Any], list[ValidationError]]:
    errors: list[ValidationError] = []
    empty = {"base_ref": base_ref, "unchanged": [], "new": [], "deleted": [], "modified": []}
    kinds = {
        SCENARIOS_DIR.relative_to(REPO_ROOT).as_posix(): "scenario",
        TRIALS_DIR.relative_to(REPO_ROOT).as_posix(): "trial",
    }
    listed = git("ls-tree", "-r", "--name-only", base_ref, "--", *sorted(kinds), check=False)
    if listed.returncode:
        error(errors, "base_ref", base_ref, listed.stderr.strip() or "unresolvable ref")
        return empty, errors
    base_paths = {
        line
        for line in listed.stdout.splitlines()
        if line.endswith((".yaml", ".yml")) and Path(line).name not in INDEX_FILENAMES
    }
    current_paths: set[str] = set()
    for directory in (SCENARIOS_DIR, TRIALS_DIR):
        current_paths.update(
            path.relative_to(REPO_ROOT).as_posix() for path in record_paths(directory)
        )

    def record_kind(relative: str) -> str:
        for prefix, kind in kinds.items():
            if relative.startswith(f"{prefix}/"):
                return kind
        return "record"

    unchanged: list[str] = []
    modified: list[str] = []
    for relative in sorted(base_paths & current_paths):
        old = git_bytes("show", f"{base_ref}:{relative}")
        current = (REPO_ROOT / relative).read_bytes()
        if old.returncode or old.stdout != current:
            modified.append(relative)
            error(
                errors,
                f"immutable_{record_kind(relative)}_modified",
                relative,
                f"differs from {base_ref}",
            )
        else:
            unchanged.append(relative)
    deleted = sorted(base_paths - current_paths)
    new = sorted(current_paths - base_paths)
    for relative in deleted:
        error(errors, f"immutable_{record_kind(relative)}_deleted", relative, f"present in {base_ref}")
    return {
        "base_ref": base_ref,
        "unchanged": unchanged,
        "new": new,
        "deleted": deleted,
        "modified": modified,
    }, errors


def validate_registry(base_ref: str | None = None) -> dict[str, Any]:
    scenarios, errors = load_scenarios()
    arms, arm_errors = load_arms()
    errors.extend(arm_errors)
    trials, trial_errors = validate_trial_files(
        record_paths(TRIALS_DIR), scenario_index(scenarios), arms
    )
    errors.extend(trial_errors)
    immutability = None
    if base_ref:
        immutability, immutable_errors = check_immutability(base_ref)
        errors.extend(immutable_errors)
    return {
        "checker": CHECKER,
        "ok": not errors,
        "scenarios": len(scenarios),
        "trials": len(trials),
        "base_ref_diff": immutability,
        "errors": [item.as_dict() for item in errors],
    }


def partition_paths(
    paths: Iterable[Path], errors: list[ValidationError]
) -> tuple[list[Path], list[Path]]:
    scenario_paths: list[Path] = []
    trial_paths: list[Path] = []
    for path in sorted(Path(item) for item in paths):
        try:
            document = load_path(path)
        except (OSError, yaml.YAMLError) as exc:
            error(errors, "yaml_input", str(path), str(exc))
            continue
        kind = document.get("kind") if isinstance(document, dict) else None
        if kind == "m3c3_bench_scenario":
            scenario_paths.append(path)
        elif kind == "m3c3_bench_trial":
            trial_paths.append(path)
        else:
            error(errors, "unknown_kind", str(path), f"kind={kind!r}")
    return scenario_paths, trial_paths


def validate_paths(paths: Iterable[Path]) -> dict[str, Any]:
    errors: list[ValidationError] = []
    scenario_paths, trial_paths = partition_paths(paths, errors)
    scenarios, scenario_errors = validate_scenario_files(scenario_paths)
    errors.extend(scenario_errors)
    arms, arm_errors = load_arms()
    errors.extend(arm_errors)
    # Un essai reste interprétable via le registre même si son scénario n'est pas
    # passé en argument ; les scénarios explicites priment sur ceux du dépôt.
    registry_scenarios, _ = load_scenarios()
    index = scenario_index(registry_scenarios)
    index.update(scenario_index(scenarios))
    trials, trial_errors = validate_trial_files(trial_paths, index, arms)
    errors.extend(trial_errors)
    return {
        "checker": CHECKER,
        "ok": not errors,
        "scenarios": len(scenarios),
        "trials": len(trials),
        "base_ref_diff": None,
        "errors": [item.as_dict() for item in errors],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def render_text(result: dict[str, Any]) -> str:
    lines = [f"Scénarios : {result['scenarios']} · essais : {result['trials']}"]
    if result["base_ref_diff"] is not None:
        diff = result["base_ref_diff"]
        lines.append(
            f"Diff {diff['base_ref']} : {len(diff['unchanged'])} inchangé(s), "
            f"{len(diff['new'])} nouveau(x), {len(diff['modified'])} modifié(s), "
            f"{len(diff['deleted'])} supprimé(s)"
        )
    if result["errors"]:
        lines.append(f"ÉCHEC — {len(result['errors'])} erreur(s) :")
        lines.extend(
            f"  ✗ {item['code']} [{item['path']}] — {item['detail']}" for item in result["errors"]
        )
    else:
        lines.append("CONFORME — schémas, ancres, détecteurs, hashes et arithmétique vérifiés.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.paths:
        result = validate_paths(args.paths)
        if args.base_ref:
            immutability, immutable_errors = check_immutability(args.base_ref)
            result["base_ref_diff"] = immutability
            result["errors"].extend(item.as_dict() for item in immutable_errors)
            result["ok"] = not result["errors"]
    else:
        result = validate_registry(args.base_ref)
    print(
        json.dumps(result, ensure_ascii=False, sort_keys=True)
        if args.format == "json"
        else render_text(result)
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
