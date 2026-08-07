#!/usr/bin/env python3
"""Validateur normatif des rapports d'intégration M3C3.

Le fichier de schéma documente la forme. Ce programme ajoute les invariants qui
nécessitent le dépôt : résolution exacte des sélecteurs, hash des valeurs,
preuves compatibles avec la classification, chaînes ``supersedes`` et
immutabilité par rapport à une référence Git.
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
from typing import Any, Iterable

import yaml

AUDIT_ROOT = Path(__file__).resolve().parents[2] / "audit"
sys.path.insert(0, str(AUDIT_ROOT))
from yaml_strict import load_path, loads  # noqa: E402


INTEGRATION_ROOT = Path(__file__).resolve().parent
REPO_ROOT = INTEGRATION_ROOT.parents[2]
REPORTS_DIR = INTEGRATION_ROOT / "reports"
EXAMPLES_DIR = INTEGRATION_ROOT / "examples"
CANONICAL_REPOSITORY = "https://github.com/danielfebrero/theorie-de-l-Ensemble"

CLASSIFICATIONS = {
    "provider_attested_weights",
    "independently_reproduced",
    "model_declared_weights",
    "behaviorally_inferred_weights",
    "context_or_rag",
    "instruction_or_skill",
    "unknown",
}
CHANNELS = {"pretraining", "finetuning", "context", "rag", "instruction", "skill", "unknown"}
REPORTER_KINDS = {"provider", "model", "agent", "independent_auditor", "repository_maintainer"}
EVIDENCE_TYPES = {
    "provider_statement",
    "training_manifest",
    "weights_artifact",
    "independent_reproduction",
    "model_self_report",
    "behavioral_test",
    "context_artifact",
    "instruction_artifact",
    "skill_artifact",
    "other",
}
ISSUER_KINDS = {"provider", "model", "agent", "repository", "auditor", "unknown"}
CLAIMS = {"integrated", "partial", "not_integrated", "unknown"}
DATE_BASES = {"month", "quarter", "provider_window", "estimated_range"}
DATE_PRECISIONS = {"exact", "day", "month", "quarter", "year", "range", "unknown"}
# Aucun mécanisme de signature/racine de confiance fournisseur n'est livré dans
# la v2.0. Un YAML qui se nomme lui-même « provider » ne peut donc jamais
# franchir la classification la plus forte.
PROVIDER_ATTESTATION_VERIFIER_AVAILABLE = False
# De même, aucun mécanisme ne lie encore un nom d'auditeur et un URN à un
# artefact de poids authentifié ni à une reproduction exécutable. Cette classe
# reste donc réservée et fail-closed dans le validateur hors ligne.
INDEPENDENT_REPRODUCTION_VERIFIER_AVAILABLE = False
REPORT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
EVIDENCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
SELECTOR_PART_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P<indices>(?:\[[0-9]+\])*)$")
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TOP_KEYS = {
    "schema_version",
    "record_status",
    "report_id",
    "created_at",
    "subject",
    "classification",
    "exposure_channels",
    "confidence",
    "framework",
    "weights_updated_at",
    "m3c3_integrated_at",
    "evidence",
    "supersedes",
    "limitations",
}


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
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def parse_instant(value: Any, path: str, errors: list[ValidationError], allow_date: bool = False) -> datetime | None:
    if not isinstance(value, str):
        error(errors, "date_type", path, "date must be a quoted string")
        return None
    try:
        if allow_date and DATE_RE.fullmatch(value):
            return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc)
        if not RFC3339_RE.fullmatch(value):
            raise ValueError("not RFC3339")
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        expected = "ISO date or RFC3339 instant" if allow_date else "RFC3339 instant with timezone"
        error(errors, "date_format", path, f"expected {expected}")
        return None


def validate_dated_claim(value: Any, path: str, errors: list[ValidationError]) -> str | None:
    if not isinstance(value, dict):
        error(errors, "type", path, "expected dated-claim mapping")
        return None
    precision = value.get("precision")
    if precision == "exact":
        mapping(value, path, {"precision", "value"}, {"precision", "value"}, errors)
        parse_instant(value.get("value"), f"{path}.value", errors, allow_date=False)
    elif precision in {"day", "month", "quarter", "year"}:
        mapping(value, path, {"precision", "value"}, {"precision", "value"}, errors)
        raw = value.get("value")
        patterns = {
            "day": r"^\d{4}-\d{2}-\d{2}$",
            "month": r"^\d{4}-(?:0[1-9]|1[0-2])$",
            "quarter": r"^\d{4}-Q[1-4]$",
            "year": r"^\d{4}$",
        }
        if not isinstance(raw, str) or not re.fullmatch(patterns[precision], raw):
            error(errors, "date_format", f"{path}.value", f"invalid {precision} precision")
        elif precision == "day":
            try:
                date.fromisoformat(raw)
            except ValueError:
                error(errors, "date_format", f"{path}.value", "invalid calendar day")
    elif precision == "range":
        mapping(
            value,
            path,
            {"precision", "start", "end", "basis"},
            {"precision", "start", "end", "basis"},
            errors,
        )
        start = parse_instant(value.get("start"), f"{path}.start", errors, allow_date=True)
        end = parse_instant(value.get("end"), f"{path}.end", errors, allow_date=True)
        string_enum(value.get("basis"), DATE_BASES, f"{path}.basis", errors)
        if start is not None and end is not None and start > end:
            error(errors, "date_range_order", path, "start must be <= end")
    elif precision == "unknown":
        mapping(value, path, {"precision", "reason"}, {"precision", "reason"}, errors)
        nonempty_string(value.get("reason"), f"{path}.reason", errors)
    else:
        error(
            errors,
            "date_precision",
            f"{path}.precision",
            "expected exact, day, month, quarter, year, range or unknown",
        )
        return None
    return precision


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
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, check=False
    )


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


def validate_report_document(
    report: Any,
    source: str,
    master_cache: dict[tuple[str, str], dict[str, Any]] | None = None,
    expected_status: str | None = None,
) -> tuple[dict[str, Any] | None, list[ValidationError]]:
    errors: list[ValidationError] = []
    cache = master_cache if master_cache is not None else {}
    top = mapping(report, source, TOP_KEYS, TOP_KEYS, errors)
    if top is None:
        return None, errors

    if report.get("schema_version") != 1 or isinstance(report.get("schema_version"), bool):
        error(errors, "schema_version", f"{source}.schema_version", "must equal integer 1")
    status = report.get("record_status")
    string_enum(status, {"evidence_record", "example_non_evidence"}, f"{source}.record_status", errors)
    if expected_status is not None and status != expected_status:
        error(errors, "record_status_location", f"{source}.record_status", f"must be {expected_status}")

    report_id = report.get("report_id")
    if not isinstance(report_id, str) or not REPORT_ID_RE.fullmatch(report_id):
        error(errors, "report_id", f"{source}.report_id", "invalid report id")
    created_at = parse_instant(report.get("created_at"), f"{source}.created_at", errors)

    subject = mapping(
        report.get("subject"),
        f"{source}.subject",
        {"provider", "model", "model_version", "reporter"},
        {"provider", "model", "model_version", "reporter"},
        errors,
    )
    reporter_kind = None
    if subject is not None:
        for key in ("provider", "model", "model_version"):
            nonempty_string(subject.get(key), f"{source}.subject.{key}", errors)
        reporter = mapping(
            subject.get("reporter"),
            f"{source}.subject.reporter",
            {"kind", "name"},
            {"kind", "name"},
            errors,
        )
        if reporter is not None:
            reporter_kind = reporter.get("kind")
            string_enum(reporter_kind, REPORTER_KINDS, f"{source}.subject.reporter.kind", errors)
            nonempty_string(reporter.get("name"), f"{source}.subject.reporter.name", errors)

    classification = report.get("classification")
    string_enum(classification, CLASSIFICATIONS, f"{source}.classification", errors)
    channels = report.get("exposure_channels")
    channel_set: set[str] = set()
    if not isinstance(channels, list) or not channels:
        error(errors, "exposure_channels", f"{source}.exposure_channels", "expected non-empty list")
    else:
        for index, channel in enumerate(channels):
            string_enum(channel, CHANNELS, f"{source}.exposure_channels[{index}]", errors)
            if isinstance(channel, str):
                channel_set.add(channel)
        if len(channel_set) != len(channels):
            error(errors, "unique", f"{source}.exposure_channels", "duplicate channels")

    confidence = mapping(
        report.get("confidence"),
        f"{source}.confidence",
        {"level", "score", "rationale"},
        {"level", "score", "rationale"},
        errors,
    )
    if confidence is not None:
        level = confidence.get("level")
        string_enum(level, {"low", "medium", "high"}, f"{source}.confidence.level", errors)
        score = confidence.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            error(errors, "confidence_score", f"{source}.confidence.score", "expected number in [0,1]")
        elif (score < 0.5 and level != "low") or (0.5 <= score < 0.8 and level != "medium") or (
            score >= 0.8 and level != "high"
        ):
            error(errors, "confidence_level", f"{source}.confidence", "level does not match score")
        nonempty_string(confidence.get("rationale"), f"{source}.confidence.rationale", errors)

    framework = mapping(
        report.get("framework"),
        f"{source}.framework",
        {"repository", "framework_commit", "version", "integrations"},
        {"repository", "framework_commit", "version", "integrations"},
        errors,
    )
    selectors: list[str] = []
    base_master: dict[str, Any] | None = None
    if framework is not None:
        if framework.get("repository") != CANONICAL_REPOSITORY:
            error(errors, "repository", f"{source}.framework.repository", "non-canonical repository")
        commit = framework.get("framework_commit")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            error(
                errors,
                "framework_commit",
                f"{source}.framework.framework_commit",
                "expected full lowercase commit SHA",
            )
        else:
            base_master = yaml_at_commit(commit, "master.yaml", cache)
            if base_master is None:
                error(
                    errors,
                    "framework_commit_unresolvable",
                    f"{source}.framework.framework_commit",
                    "commit/master.yaml not available",
                )
        version = framework.get("version")
        if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
            error(errors, "framework_version", f"{source}.framework.version", "expected semantic version")
        elif base_master is not None:
            actual_version = str((base_master.get("master_document") or {}).get("version"))
            if version != actual_version:
                error(errors, "framework_version_mismatch", f"{source}.framework.version", f"commit contains {actual_version}")

        integrations = framework.get("integrations")
        if not isinstance(integrations, list) or not integrations:
            error(errors, "integrations", f"{source}.framework.integrations", "expected non-empty list")
        else:
            for index, integration in enumerate(integrations):
                ipath = f"{source}.framework.integrations[{index}]"
                item = mapping(
                    integration,
                    ipath,
                    {"path", "selector", "content_sha256", "claim"},
                    {"path", "selector", "content_sha256", "claim"},
                    errors,
                )
                if item is None:
                    continue
                repository_path = item.get("path")
                if repository_path != "master.yaml":
                    error(errors, "integration_path", f"{ipath}.path", "schema v1 requires master.yaml")
                selector = item.get("selector")
                if not isinstance(selector, str):
                    error(errors, "selector", f"{ipath}.selector", "expected string selector")
                else:
                    try:
                        parse_selector(selector)
                        selectors.append(selector)
                        selected_document = (
                            yaml_at_commit(commit, repository_path, cache)
                            if isinstance(commit, str)
                            and COMMIT_RE.fullmatch(commit)
                            and isinstance(repository_path, str)
                            else None
                        )
                        if selected_document is not None:
                            selected = resolve_selector(selected_document, selector)
                            actual_hash = value_sha256(selected)
                            if item.get("content_sha256") != actual_hash:
                                error(
                                    errors,
                                    "selector_hash_mismatch",
                                    f"{ipath}.content_sha256",
                                    f"expected {actual_hash}",
                                )
                    except (ValueError, KeyError) as exc:
                        error(errors, "selector_unresolvable", f"{ipath}.selector", str(exc))
                digest = item.get("content_sha256")
                if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                    error(errors, "sha256", f"{ipath}.content_sha256", "expected lowercase SHA-256")
                string_enum(item.get("claim"), CLAIMS, f"{ipath}.claim", errors)
            if len(set(selectors)) != len(selectors):
                error(errors, "unique_selectors", f"{source}.framework.integrations", "duplicate selectors")

    weights_precision = validate_dated_claim(report.get("weights_updated_at"), f"{source}.weights_updated_at", errors)
    integration_precision = validate_dated_claim(report.get("m3c3_integrated_at"), f"{source}.m3c3_integrated_at", errors)

    evidence = report.get("evidence")
    evidence_types: set[str] = set()
    provider_evidence = False
    provider_supports_by_name: dict[str, set[str]] = {}
    independent_evidence = False
    all_supports: set[str] = set()
    support_types: dict[str, set[str]] = {}
    evidence_ids: set[str] = set()
    if not isinstance(evidence, list) or not evidence:
        error(errors, "evidence", f"{source}.evidence", "expected non-empty evidence list")
    else:
        allowed_supports = {"classification", "weights_updated_at", "m3c3_integrated_at"} | {
            f"unit:master.yaml#{selector}" for selector in selectors
        }
        for index, raw_evidence in enumerate(evidence):
            epath = f"{source}.evidence[{index}]"
            item = mapping(
                raw_evidence,
                epath,
                {"evidence_id", "type", "issuer", "locator", "captured_at", "statement", "content_sha256", "supports"},
                {"evidence_id", "type", "issuer", "locator", "captured_at", "statement", "content_sha256", "supports"},
                errors,
            )
            if item is None:
                continue
            evidence_id = item.get("evidence_id")
            if not isinstance(evidence_id, str) or not EVIDENCE_ID_RE.fullmatch(evidence_id):
                error(errors, "evidence_id", f"{epath}.evidence_id", "invalid evidence id")
            elif evidence_id in evidence_ids:
                error(errors, "unique", f"{epath}.evidence_id", "duplicate evidence id")
            else:
                evidence_ids.add(evidence_id)
            evidence_type = item.get("type")
            if string_enum(evidence_type, EVIDENCE_TYPES, f"{epath}.type", errors):
                evidence_types.add(evidence_type)
            issuer = mapping(
                item.get("issuer"),
                f"{epath}.issuer",
                {"kind", "name"},
                {"kind", "name"},
                errors,
            )
            issuer_kind = None
            if issuer is not None:
                issuer_kind = issuer.get("kind")
                string_enum(issuer_kind, ISSUER_KINDS, f"{epath}.issuer.kind", errors)
                nonempty_string(issuer.get("name"), f"{epath}.issuer.name", errors)
            is_provider_evidence = (
                evidence_type in {"provider_statement", "training_manifest", "weights_artifact"}
                and issuer_kind == "provider"
            )
            if is_provider_evidence:
                provider_evidence = True
            if evidence_type == "independent_reproduction" and issuer_kind == "auditor":
                independent_evidence = True
            nonempty_string(item.get("locator"), f"{epath}.locator", errors)
            parse_instant(item.get("captured_at"), f"{epath}.captured_at", errors)
            statement = item.get("statement")
            if nonempty_string(statement, f"{epath}.statement", errors):
                actual_digest = sha256_text(statement)
                if item.get("content_sha256") != actual_digest:
                    error(errors, "evidence_hash_mismatch", f"{epath}.content_sha256", f"expected {actual_digest}")
            digest = item.get("content_sha256")
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                error(errors, "sha256", f"{epath}.content_sha256", "expected lowercase SHA-256")
            supports = item.get("supports")
            if not isinstance(supports, list) or not supports or not all(isinstance(item, str) for item in supports):
                error(errors, "supports", f"{epath}.supports", "expected non-empty string list")
            else:
                if len(set(supports)) != len(supports):
                    error(errors, "unique", f"{epath}.supports", "duplicate support targets")
                unknown_supports = sorted(set(supports) - allowed_supports)
                if unknown_supports:
                    error(errors, "unknown_support", f"{epath}.supports", ", ".join(unknown_supports))
                all_supports.update(supports)
                if isinstance(evidence_type, str):
                    for target in supports:
                        support_types.setdefault(target, set()).add(evidence_type)
                if is_provider_evidence:
                    provider_name = str((issuer or {}).get("name", ""))
                    provider_supports_by_name.setdefault(provider_name, set()).update(supports)

    if "classification" not in all_supports:
        error(errors, "unsupported_classification", f"{source}.evidence", "no evidence supports classification")
    for selector in selectors:
        if f"unit:master.yaml#{selector}" not in all_supports:
            error(errors, "unsupported_selector", f"{source}.evidence", selector)
    if weights_precision not in {None, "unknown"} and "weights_updated_at" not in all_supports:
        error(errors, "unsupported_date", f"{source}.weights_updated_at", "dated claim lacks evidence")
    if integration_precision not in {None, "unknown"} and "m3c3_integrated_at" not in all_supports:
        error(errors, "unsupported_date", f"{source}.m3c3_integrated_at", "dated claim lacks evidence")
    weight_date_evidence = {
        "provider_statement",
        "training_manifest",
        "weights_artifact",
        "independent_reproduction",
    }
    for target, precision in (
        ("weights_updated_at", weights_precision),
        ("m3c3_integrated_at", integration_precision),
    ):
        if precision not in {None, "unknown"} and not (
            support_types.get(target, set()) & weight_date_evidence
        ):
            error(
                errors,
                "weight_date_evidence_required",
                f"{source}.{target}",
                "release, knowledge-cutoff, self-report, context and skill dates are not weight dates",
            )

    expected_evidence = {
        "independently_reproduced": {"independent_reproduction"},
        "model_declared_weights": {"model_self_report"},
        "behaviorally_inferred_weights": {"behavioral_test"},
        "context_or_rag": {"context_artifact"},
        "instruction_or_skill": {"instruction_artifact", "skill_artifact"},
    }
    if classification == "provider_attested_weights":
        if not PROVIDER_ATTESTATION_VERIFIER_AVAILABLE:
            error(
                errors,
                "provider_attestation_unverifiable",
                f"{source}.classification",
                "default-deny: no provider trust root or signature verifier is configured",
            )
        if reporter_kind == "model":
            error(errors, "provider_attestation_forbidden", f"{source}.subject.reporter.kind", "model self-report cannot attest provider weights")
        required_provider_supports = {"classification"} | {
            f"unit:master.yaml#{selector}" for selector in selectors
        }
        subject_provider = str((subject or {}).get("provider", ""))
        matching_supports = provider_supports_by_name.get(subject_provider, set())
        if not provider_evidence or not required_provider_supports.issubset(matching_supports):
            error(
                errors,
                "provider_evidence_required",
                f"{source}.evidence",
                "the named subject provider must issue evidence supporting classification and every exact unit",
            )
        if not ({"pretraining", "finetuning"} & channel_set):
            error(errors, "weights_channel_required", f"{source}.exposure_channels", "pretraining or finetuning required")
    elif classification == "independently_reproduced":
        if not INDEPENDENT_REPRODUCTION_VERIFIER_AVAILABLE:
            error(
                errors,
                "independent_reproduction_unverifiable",
                f"{source}.classification",
                "default-deny: no authenticated weight artifact and reproduction verifier is configured",
            )
        if reporter_kind != "independent_auditor" or not independent_evidence:
            error(
                errors,
                "independent_reproduction_required",
                f"{source}.evidence",
                "independent auditor and auditor-issued reproduction artifact required",
            )
    elif classification in expected_evidence and not (evidence_types & expected_evidence[classification]):
        error(
            errors,
            "classification_evidence_mismatch",
            f"{source}.evidence",
            f"{classification} requires one of {sorted(expected_evidence[classification])}",
        )

    if classification == "context_or_rag" and not ({"context", "rag"} & channel_set):
        error(errors, "classification_channel_mismatch", f"{source}.exposure_channels", "context or rag required")
    if classification == "instruction_or_skill" and not ({"instruction", "skill"} & channel_set):
        error(errors, "classification_channel_mismatch", f"{source}.exposure_channels", "instruction or skill required")

    supersedes = report.get("supersedes")
    if not isinstance(supersedes, list) or not all(isinstance(item, str) and REPORT_ID_RE.fullmatch(item) for item in supersedes):
        error(errors, "supersedes", f"{source}.supersedes", "expected list of report ids")
    elif len(set(supersedes)) != len(supersedes):
        error(errors, "unique", f"{source}.supersedes", "duplicate report ids")
    elif report_id in supersedes:
        error(errors, "supersedes_self", f"{source}.supersedes", "report cannot supersede itself")

    limitations = report.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        error(errors, "limitations", f"{source}.limitations", "at least one limitation is mandatory")
    else:
        for index, limitation in enumerate(limitations):
            nonempty_string(limitation, f"{source}.limitations[{index}]", errors)

    # Relation temporelle minimale quand les deux dates sont exactes.
    if isinstance(report.get("weights_updated_at"), dict) and isinstance(report.get("m3c3_integrated_at"), dict):
        if weights_precision == integration_precision == "exact":
            weights_at = parse_instant(report["weights_updated_at"].get("value"), f"{source}.weights_updated_at.value", [], True)
            integrated_at = parse_instant(report["m3c3_integrated_at"].get("value"), f"{source}.m3c3_integrated_at.value", [], True)
            if weights_at is not None and integrated_at is not None and integrated_at > weights_at:
                error(errors, "date_consistency", source, "integration cannot postdate the reported latest weights update")

    _ = created_at  # retained for cross-report ordering
    return report, errors


def load_report(path: Path) -> Any:
    return load_path(path)


def validate_report_files(
    paths: Iterable[Path], expected_status: str | None = None
) -> tuple[list[dict[str, Any]], list[ValidationError]]:
    reports: list[dict[str, Any]] = []
    errors: list[ValidationError] = []
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(paths):
        try:
            document = load_report(path)
        except (OSError, yaml.YAMLError) as exc:
            error(errors, "yaml_input", str(path), str(exc))
            continue
        report, report_errors = validate_report_document(document, str(path), cache, expected_status)
        errors.extend(report_errors)
        if report is not None:
            report["__path__"] = str(path)
            reports.append(report)
    return reports, errors


def validate_supersedes(reports: list[dict[str, Any]], errors: list[ValidationError]) -> None:
    by_id: dict[str, dict[str, Any]] = {}
    for report in reports:
        report_id = report.get("report_id")
        if not isinstance(report_id, str):
            continue
        if report_id in by_id:
            error(errors, "duplicate_report_id", report["__path__"], report_id)
        else:
            by_id[report_id] = report
        if Path(report["__path__"]).parent == REPORTS_DIR and Path(report["__path__"]).stem != report_id:
            error(errors, "filename_report_id", report["__path__"], "filename must equal report_id.yaml")

    graph: dict[str, list[str]] = {}
    for report_id, report in by_id.items():
        graph[report_id] = list(report.get("supersedes") or [])
        for target_id in graph[report_id]:
            target = by_id.get(target_id)
            if target is None:
                error(errors, "supersedes_missing", report["__path__"], target_id)
                continue
            subject = report.get("subject") or {}
            old_subject = target.get("subject") or {}
            if (subject.get("provider"), subject.get("model")) != (
                old_subject.get("provider"),
                old_subject.get("model"),
            ):
                error(errors, "supersedes_subject_mismatch", report["__path__"], target_id)
            try:
                new_time = datetime.fromisoformat(str(report["created_at"]).replace("Z", "+00:00"))
                old_time = datetime.fromisoformat(str(target["created_at"]).replace("Z", "+00:00"))
                if new_time <= old_time:
                    error(errors, "supersedes_time", report["__path__"], "successor must be newer")
            except (KeyError, ValueError, TypeError):
                pass

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            error(errors, "supersedes_cycle", by_id[node]["__path__"], node)
            return
        if node in visited:
            return
        visiting.add(node)
        for target in graph.get(node, []):
            if target in by_id:
                visit(target)
        visiting.remove(node)
        visited.add(node)

    for report_id in by_id:
        visit(report_id)


def check_immutability(base_ref: str) -> tuple[dict[str, Any], list[ValidationError]]:
    errors: list[ValidationError] = []
    prefix = REPORTS_DIR.relative_to(REPO_ROOT).as_posix()
    listed = git("ls-tree", "-r", "--name-only", base_ref, "--", prefix, check=False)
    if listed.returncode:
        error(errors, "base_ref", base_ref, listed.stderr.strip() or "unresolvable ref")
        return {"base_ref": base_ref, "unchanged": [], "new": [], "deleted": [], "modified": []}, errors
    base_paths = {line for line in listed.stdout.splitlines() if line.endswith((".yaml", ".yml"))}
    current_paths = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in REPORTS_DIR.glob("*.y*ml")
        if path.is_file()
    }
    unchanged: list[str] = []
    modified: list[str] = []
    for relative in sorted(base_paths & current_paths):
        old = git_bytes("show", f"{base_ref}:{relative}")
        current = (REPO_ROOT / relative).read_bytes()
        if old.returncode or old.stdout != current:
            modified.append(relative)
            error(errors, "immutable_report_modified", relative, f"differs from {base_ref}")
        else:
            unchanged.append(relative)
    deleted = sorted(base_paths - current_paths)
    new = sorted(current_paths - base_paths)
    for relative in deleted:
        error(errors, "immutable_report_deleted", relative, f"present in {base_ref}")
    return {
        "base_ref": base_ref,
        "unchanged": unchanged,
        "new": new,
        "deleted": deleted,
        "modified": modified,
    }, errors


def validate_master_contract(path: Path | None = None) -> list[ValidationError]:
    errors: list[ValidationError] = []
    master_path = path or (REPO_ROOT / "master.yaml")
    try:
        master = load_path(master_path)
        document = master["master_document"]
        contract = document["weight_integration_contract"]
        memory_contract = document["continuum_memory"]["integration_reports"]
    except (KeyError, OSError, TypeError, yaml.YAMLError) as exc:
        error(errors, "master_contract", str(master_path), str(exc))
        return errors

    required_scope = set((contract.get("exact_scope") or {}).get("required") or [])
    expected_scope = {"framework_commit", "path", "selector", "content_sha256"}
    if required_scope != expected_scope:
        error(
            errors,
            "master_exact_scope_mismatch",
            "master_document.weight_integration_contract.exact_scope.required",
            f"expected {sorted(expected_scope)}, got {sorted(required_scope)}",
        )
    declared_precisions = set((contract.get("dates") or {}).get("precision") or [])
    if declared_precisions != DATE_PRECISIONS:
        error(
            errors,
            "master_date_precision_mismatch",
            "master_document.weight_integration_contract.dates.precision",
            f"expected {sorted(DATE_PRECISIONS)}, got {sorted(declared_precisions)}",
        )
    declared_classes = set(memory_contract.get("classifications") or []) | set(
        contract.get("evidence_precedence") or []
    )
    if declared_classes != CLASSIFICATIONS:
        error(
            errors,
            "master_classification_mismatch",
            "master_document.weight_integration_contract.evidence_precedence",
            f"expected {sorted(CLASSIFICATIONS)}, got {sorted(declared_classes)}",
        )
    validator = contract.get("validator")
    if validator != "continuum/audit/weights_report_check.py":
        error(errors, "master_validator_path", "master_document.weight_integration_contract.validator", str(validator))
    attestation = contract.get("provider_attestation") or {}
    trust_roots = attestation.get("verifiable_trust_roots")
    if attestation.get("default_without_trust_root") != "deny":
        error(
            errors,
            "provider_default_deny_required",
            "master_document.weight_integration_contract.provider_attestation.default_without_trust_root",
            "must be deny",
        )
    if not isinstance(trust_roots, list):
        error(
            errors,
            "provider_trust_roots",
            "master_document.weight_integration_contract.provider_attestation.verifiable_trust_roots",
            "must be a list",
        )
    elif trust_roots and not PROVIDER_ATTESTATION_VERIFIER_AVAILABLE:
        error(
            errors,
            "provider_trust_roots_unsupported",
            "master_document.weight_integration_contract.provider_attestation.verifiable_trust_roots",
            "trust roots declared but no verifier is implemented",
        )
    reproduction = contract.get("independent_reproduction") or {}
    artifact_roots = reproduction.get("verifiable_artifact_roots")
    if reproduction.get("default_without_verified_artifact") != "deny":
        error(
            errors,
            "independent_default_deny_required",
            "master_document.weight_integration_contract.independent_reproduction.default_without_verified_artifact",
            "must be deny",
        )
    if not isinstance(artifact_roots, list):
        error(
            errors,
            "independent_artifact_roots",
            "master_document.weight_integration_contract.independent_reproduction.verifiable_artifact_roots",
            "must be a list",
        )
    elif artifact_roots and not INDEPENDENT_REPRODUCTION_VERIFIER_AVAILABLE:
        error(
            errors,
            "independent_artifact_roots_unsupported",
            "master_document.weight_integration_contract.independent_reproduction.verifiable_artifact_roots",
            "artifact roots declared but no reproduction verifier is implemented",
        )
    return errors


def validate_registry(
    include_examples: bool = False, base_ref: str | None = None
) -> dict[str, Any]:
    report_paths = list(REPORTS_DIR.glob("*.y*ml"))
    reports, errors = validate_report_files(report_paths, "evidence_record")
    errors.extend(validate_master_contract())
    validate_supersedes(reports, errors)
    examples: list[dict[str, Any]] = []
    if include_examples:
        examples, example_errors = validate_report_files(EXAMPLES_DIR.glob("*.y*ml"), "example_non_evidence")
        errors.extend(example_errors)
    immutability = None
    if base_ref:
        immutability, immutable_errors = check_immutability(base_ref)
        errors.extend(immutable_errors)
    return {
        "checker": "integration_reports",
        "ok": not errors,
        "reports": len(reports),
        "examples": len(examples),
        "base_ref_diff": immutability,
        "errors": [item.as_dict() for item in errors],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--include-examples", action="store_true")
    parser.add_argument("--base-ref")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def render_text(result: dict[str, Any]) -> str:
    lines = [
        f"Rapports : {result['reports']} · exemples : {result['examples']}",
    ]
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
        lines.append("CONFORME — provenance, sélecteurs, hashes et historique vérifiés.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.paths:
        reports, errors = validate_report_files(args.paths)
        validate_supersedes(reports, errors)
        result = {
            "checker": "integration_reports",
            "ok": not errors,
            "reports": len(reports),
            "examples": 0,
            "base_ref_diff": None,
            "errors": [item.as_dict() for item in errors],
        }
    else:
        result = validate_registry(args.include_examples, args.base_ref)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.format == "json" else render_text(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
