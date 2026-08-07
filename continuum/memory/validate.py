#!/usr/bin/env python3
"""Validate the content-addressed, append-only M3C3 Continuum memory."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = Path("continuum/memory/index.yaml")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class MemoryValidationError(ValueError):
    """Raised when a memory artifact violates the v2 contract."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses ambiguous duplicate mapping keys."""


def _unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> Any:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise MemoryValidationError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def _loads_yaml(content: bytes | str, source: str) -> Any:
    try:
        return yaml.load(content, Loader=UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise MemoryValidationError(f"{source}: invalid YAML: {error}") from error


def _load_yaml(path: Path) -> Any:
    return _loads_yaml(path.read_text(encoding="utf-8"), str(path))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MemoryValidationError(f"{label} must be a mapping")
    return value


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryValidationError(f"{label} must be a non-empty string")
    return value


def _string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise MemoryValidationError(f"{label} must be a {'possibly empty ' if allow_empty else 'non-empty '}list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise MemoryValidationError(f"{label} must contain only non-empty strings")
    if len(value) != len(set(value)):
        raise MemoryValidationError(f"{label} contains duplicates")
    return value


def _inside(root: Path, relative: Any) -> Path:
    relative = _nonempty_string(relative, "repository path")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise MemoryValidationError(f"path escapes repository: {relative}") from error
    return candidate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise MemoryValidationError(f"{label} must be a lowercase SHA-256")
    return value


def _verify_artifact(root: Path, record: Mapping[str, Any], label: str) -> tuple[str, Path]:
    path_text = _nonempty_string(record.get("path"), f"{label}.path")
    path = _inside(root, path_text)
    if not path.is_file():
        raise MemoryValidationError(f"missing {label}: {path_text}")
    expected = _expected_sha(record.get("sha256"), f"{label}.sha256")
    actual = _sha256(path)
    if actual != expected:
        raise MemoryValidationError(f"{label} content hash mismatch for {path_text}")
    return path_text, path


def _timestamp(value: Any, label: str) -> None:
    text = _nonempty_string(value, label)
    if not (text.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", text)):
        raise MemoryValidationError(f"{label} must include an RFC3339 timezone")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise MemoryValidationError(f"{label} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise MemoryValidationError(f"{label} must include an RFC3339 timezone")


def _git_file(root: Path, reference: str, relative: str) -> bytes | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "show", f"{reference}:{relative}"],
        capture_output=True,
    )
    return completed.stdout if completed.returncode == 0 else None


def _validate_git_history(
    root: Path,
    reference: str,
    managed_paths: set[str],
) -> list[str]:
    _nonempty_string(reference, "history_base")
    exists = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", f"{reference}^{{commit}}"],
        capture_output=True,
    )
    if exists.returncode != 0:
        raise MemoryValidationError(f"history base does not resolve to a commit: {reference}")

    base_index_bytes = _git_file(root, reference, INDEX_PATH.as_posix())
    base_managed: set[str] = set()
    if base_index_bytes is not None:
        base_document = _mapping(
            _loads_yaml(base_index_bytes, f"{reference}:{INDEX_PATH}"),
            f"{reference}:{INDEX_PATH}",
        )
        base_index = _mapping(base_document.get("continuum_memory_index"), "base memory index")
        for item in base_index.get("entries", []):
            base_managed.add(_nonempty_string(_mapping(item, "base entry").get("path"), "base entry.path"))
        for item in base_index.get("snapshots", []):
            if isinstance(item, str):
                base_managed.add(item)
            else:
                base_managed.add(_nonempty_string(_mapping(item, "base snapshot").get("path"), "base snapshot.path"))
        creator = base_index.get("creator_index")
        if isinstance(creator, str):
            base_managed.add(creator)
        elif isinstance(creator, Mapping):
            base_managed.add(_nonempty_string(creator.get("path"), "base creator_index.path"))
        removed = sorted(base_managed - managed_paths)
        if removed:
            raise MemoryValidationError(
                f"append-only history removed artifacts from {reference}: {removed}"
            )

    compared: list[str] = []
    for relative in sorted(managed_paths | base_managed):
        old_bytes = _git_file(root, reference, relative)
        if old_bytes is None:
            continue
        current = _inside(root, relative)
        if not current.is_file() or current.read_bytes() != old_bytes:
            raise MemoryValidationError(
                f"immutable memory artifact modified since {reference}: {relative}; publish a new revision with supersedes"
            )
        compared.append(relative)
    return compared


def validate_repository(
    root: Path = REPOSITORY_ROOT,
    *,
    base_ref: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    schema_document = _mapping(_load_yaml(root / "continuum/memory/schema-v2.yaml"), "memory schema")
    schema_doc = _mapping(schema_document.get("schema"), "schema")
    index_document = _mapping(_load_yaml(root / INDEX_PATH), "memory index document")
    index = _mapping(index_document.get("continuum_memory_index"), "continuum_memory_index")

    required = set(_string_list(schema_doc.get("required"), "schema.required"))
    enums = _mapping(schema_doc.get("enums"), "schema.enums")
    allowed_status = set(_string_list(enums.get("status"), "schema.enums.status"))
    allowed_kind = set(_string_list(enums.get("kind"), "schema.enums.kind"))
    allowed_evidence = set(_string_list(enums.get("evidence_class"), "schema.enums.evidence_class"))
    allowed_result = set(_string_list(enums.get("evidence_result"), "schema.enums.evidence_result"))
    source_required = set(
        _string_list(_mapping(schema_doc.get("source_contract"), "source_contract").get("required"), "source_contract.required")
    )
    lifecycle_required = set(
        _string_list(_mapping(schema_doc.get("lifecycle_contract"), "lifecycle_contract").get("required"), "lifecycle_contract.required")
    )

    if index.get("mutability") != "append_only":
        raise MemoryValidationError("index mutability must be append_only")
    rollback = _mapping(index.get("rollback"), "index.rollback")
    if not rollback.get("destructive_rewrite_forbidden"):
        raise MemoryValidationError("destructive memory rewrites must be forbidden")
    promotion = _mapping(index.get("promotion"), "index.promotion")
    _string_list(promotion.get("required"), "index.promotion.required")

    indexed_records = index.get("entries")
    if not isinstance(indexed_records, list) or not indexed_records:
        raise MemoryValidationError("index.entries must be a non-empty list")

    entry_documents: list[tuple[Mapping[str, Any], Mapping[str, Any], str]] = []
    ids: set[str] = set()
    entry_paths: set[str] = set()
    managed_paths: set[str] = set()
    checked: list[str] = []
    for position, raw_indexed in enumerate(indexed_records):
        indexed = _mapping(raw_indexed, f"index.entries[{position}]")
        path_text, path = _verify_artifact(root, indexed, f"memory entry {position}")
        if path_text in entry_paths:
            raise MemoryValidationError(f"duplicate indexed memory path: {path_text}")
        entry_paths.add(path_text)
        managed_paths.add(path_text)
        document = _mapping(_load_yaml(path), path_text)
        entry = _mapping(document.get("memory_entry"), f"{path_text}.memory_entry")
        entry_id = _nonempty_string(entry.get("id"), f"{path_text}.id")
        if entry_id in ids:
            raise MemoryValidationError(f"duplicate memory id: {entry_id}")
        ids.add(entry_id)
        if entry_id != indexed.get("id") or entry.get("status") != indexed.get("status"):
            raise MemoryValidationError(f"index drift for {entry_id}")
        entry_documents.append((entry, indexed, path_text))

    for entry, _indexed, path_text in entry_documents:
        entry_id = str(entry["id"])
        missing = sorted(required - set(entry))
        if missing:
            raise MemoryValidationError(f"{path_text}: missing {missing}")
        _nonempty_string(entry.get("version"), f"{entry_id}.version")
        if entry.get("status") not in allowed_status or entry.get("kind") not in allowed_kind:
            raise MemoryValidationError(f"invalid status or kind for {entry_id}")
        _nonempty_string(entry.get("statement"), f"{entry_id}.statement")
        if not _mapping(entry.get("scope"), f"{entry_id}.scope"):
            raise MemoryValidationError(f"{entry_id}.scope cannot be empty")
        _timestamp(entry.get("observed_at"), f"{entry_id}.observed_at")

        evidence_summary = _mapping(entry.get("evidence_summary"), f"{entry_id}.evidence_summary")
        _nonempty_string(evidence_summary.get("strength"), f"{entry_id}.evidence_summary.strength")
        if evidence_summary.get("result") not in allowed_result:
            raise MemoryValidationError(f"{entry_id}: invalid evidence summary result")
        _string_list(
            evidence_summary.get("limitations"),
            f"{entry_id}.evidence_summary.limitations",
            allow_empty=True,
        )

        lifecycle = _mapping(entry.get("lifecycle"), f"{entry_id}.lifecycle")
        lifecycle_missing = lifecycle_required - set(lifecycle)
        if lifecycle_missing:
            raise MemoryValidationError(
                f"{entry_id}: incomplete lifecycle {sorted(lifecycle_missing)}"
            )
        _nonempty_string(lifecycle.get("rollback_if"), f"{entry_id}.lifecycle.rollback_if")
        supersedes = lifecycle.get("supersedes")
        if supersedes is not None:
            supersedes = _nonempty_string(supersedes, f"{entry_id}.lifecycle.supersedes")
            if supersedes == entry_id or supersedes not in ids:
                raise MemoryValidationError(f"{entry_id}: supersedes must name another indexed entry")
        if entry.get("status") in {"rolled_back", "deprecated"} and supersedes is None:
            raise MemoryValidationError(f"{entry_id}: terminal revision must supersede a prior entry")

        raw_sources = entry.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise MemoryValidationError(f"{entry_id}: sources cannot be empty")
        source_paths: set[str] = set()
        for source_position, raw_source in enumerate(raw_sources):
            source = _mapping(raw_source, f"{entry_id}.sources[{source_position}]")
            source_missing = source_required - set(source)
            if source_missing:
                raise MemoryValidationError(
                    f"{entry_id}: incomplete source {sorted(source_missing)}"
                )
            evidence_class = source.get("evidence_class")
            if evidence_class not in allowed_evidence:
                raise MemoryValidationError(f"{entry_id}: invalid evidence_class")
            if evidence_class == "provider_attested":
                raise MemoryValidationError(
                    f"{entry_id}: provider_attested is unverifiable without a configured trust verifier"
                )
            if source.get("result") not in allowed_result:
                raise MemoryValidationError(f"{entry_id}: invalid evidence result")
            source_path_text = _nonempty_string(source.get("path"), f"{entry_id}.source.path")
            if source_path_text in source_paths:
                raise MemoryValidationError(f"{entry_id}: duplicate source path {source_path_text}")
            source_paths.add(source_path_text)
            source_path = _inside(root, source_path_text)
            if not source_path.is_file():
                raise MemoryValidationError(f"{entry_id}: missing source {source_path_text}")
            actual = _sha256(source_path)
            expected = _expected_sha(source.get("sha256"), f"{entry_id}.source.sha256")
            if actual != expected:
                raise MemoryValidationError(
                    f"{entry_id}: source hash mismatch for {source_path_text}"
                )

        promoted_by = lifecycle.get("promoted_by")
        promotion_event = lifecycle.get("promotion_event")
        if entry.get("status") in {"active", "active_with_known_limitations"}:
            _nonempty_string(promoted_by, f"{entry_id}.lifecycle.promoted_by")
            event = _nonempty_string(promotion_event, f"{entry_id}.lifecycle.promotion_event")
            if event not in source_paths:
                raise MemoryValidationError(f"{entry_id}: promotion_event must be a hashed source")
        elif entry.get("status") == "candidate" and (promoted_by is not None or promotion_event is not None):
            raise MemoryValidationError(f"{entry_id}: candidate cannot claim promotion")
        checked.append(entry_id)

    patterns_root = root / "continuum/memory/patterns"
    pattern_index_path = patterns_root / "index.yaml"
    actual_pattern_paths = {
        path.relative_to(root).as_posix()
        for path in patterns_root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".yaml", ".yml"}
        and path != pattern_index_path
    }
    if actual_pattern_paths != entry_paths:
        raise MemoryValidationError(
            f"pattern files and memory index disagree: indexed={sorted(entry_paths)}, actual={sorted(actual_pattern_paths)}"
        )
    pattern_document = _mapping(
        _load_yaml(pattern_index_path), "pattern index document"
    )
    pattern_index = _mapping(pattern_document.get("pattern_index"), "pattern_index")
    pattern_names = set(_string_list(pattern_index.get("entries"), "pattern_index.entries"))
    if pattern_names != {Path(path).name for path in entry_paths}:
        raise MemoryValidationError("pattern index and memory index disagree")

    snapshot_records = index.get("snapshots")
    if not isinstance(snapshot_records, list) or not snapshot_records:
        raise MemoryValidationError("index.snapshots must be a non-empty list")
    snapshot_paths: set[str] = set()
    for position, raw_snapshot in enumerate(snapshot_records):
        snapshot = _mapping(raw_snapshot, f"index.snapshots[{position}]")
        path_text, path = _verify_artifact(root, snapshot, f"parameter snapshot {position}")
        if path_text in snapshot_paths:
            raise MemoryValidationError(f"duplicate snapshot path: {path_text}")
        snapshot_paths.add(path_text)
        managed_paths.add(path_text)
        payload = _mapping(_mapping(_load_yaml(path), path_text).get("snapshot"), f"{path_text}.snapshot")
        _nonempty_string(payload.get("master_version"), f"{path_text}.snapshot.master_version")
        _timestamp(payload.get("taken_at"), f"{path_text}.snapshot.taken_at")
    actual_snapshot_paths = {
        path.relative_to(root).as_posix()
        for path in (root / "continuum/memory/parameters").rglob("*")
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    }
    if actual_snapshot_paths != snapshot_paths:
        raise MemoryValidationError("snapshot files and memory index disagree")

    creator_record = _mapping(index.get("creator_index"), "index.creator_index")
    creator_path_text, creator_path = _verify_artifact(root, creator_record, "creator index")
    managed_paths.add(creator_path_text)
    creator = _mapping(
        _mapping(_load_yaml(creator_path), creator_path_text).get("creator_index"),
        f"{creator_path_text}.creator_index",
    )
    _nonempty_string(creator.get("author_creator"), "creator_index.author_creator")
    _nonempty_string(creator.get("handle"), "creator_index.handle")
    _string_list(creator.get("evidence"), "creator_index.evidence")
    actual_creator_paths = {
        path.relative_to(root).as_posix()
        for path in (root / "continuum/memory/creator").rglob("*")
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    }
    if actual_creator_paths != {creator_path_text}:
        raise MemoryValidationError("creator files and memory index disagree")

    allowed_yaml_paths = (
        entry_paths
        | snapshot_paths
        | {creator_path_text}
        | {
            "continuum/memory/index.yaml",
            "continuum/memory/schema-v2.yaml",
            "continuum/memory/patterns/index.yaml",
        }
    )
    actual_yaml_paths = {
        path.relative_to(root).as_posix()
        for path in (root / "continuum/memory").rglob("*")
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    }
    if actual_yaml_paths != allowed_yaml_paths:
        raise MemoryValidationError(
            "YAML files and memory index disagree: "
            f"allowed={sorted(allowed_yaml_paths)}, actual={sorted(actual_yaml_paths)}"
        )

    selected_base = base_ref if base_ref is not None else index.get("history_base")
    history_checked: list[str] = []
    if selected_base is not None:
        history_checked = _validate_git_history(
            root,
            _nonempty_string(selected_base, "history_base"),
            managed_paths,
        )

    return {
        "status": "pass",
        "entries_checked": checked,
        "count": len(checked),
        "artifacts_checked": len(managed_paths),
        "history_base": selected_base,
        "history_compared": history_checked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--base-ref")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        result = validate_repository(args.root, base_ref=args.base_ref)
    except (KeyError, TypeError, OSError, yaml.YAMLError, MemoryValidationError) as error:
        result = {"status": "fail", "error": str(error)}
        if args.as_json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        else:
            print(f"FAIL continuum memory: {error}")
        return 1
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"PASS continuum memory: {result['count']} entries, "
            f"{result['artifacts_checked']} content-addressed artifacts"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
