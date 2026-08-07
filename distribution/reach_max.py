#!/usr/bin/env python3
"""Portable installer and strict validator primitives for REACH-MAX v2."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


REQUIRED_PROFILES = {
    "core",
    "openai",
    "claude",
    "copilot",
    "cursor",
    "mcp",
    "ci",
    "all",
}

EXPECTED_POLICY = {
    "canonical_authority": "master.yaml",
    "activation": "scoped_adaptive",
    "global_activation_guaranteed": False,
    "scope_propagates": True,
    "permissions_propagate": False,
    "modifies_personal_skill": False,
    "modifies_model_weights": False,
}

REQUIRED_TEMPLATE_MARKERS = {
    "CANON: master.yaml",
    "ACTIVATION: scoped_adaptive",
    "GLOBAL_ACTIVATION: not_guaranteed",
    "SCOPE_PERMISSION: scope_is_not_permission",
}

TOKEN_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BACKUP_STAMP_RE = re.compile(r"^[0-9]{8}T[0-9]{6}\.[0-9]{6}Z(?:-[1-9][0-9]*)?$")
TRANSACTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
TRANSACTION_WAL = ".m3c3/reach-max-transaction.json"
TRANSACTION_ROOT = ".m3c3/reach-max-transactions"


class DistributionError(RuntimeError):
    """Base class for deterministic REACH-MAX failures."""


class ValidationError(DistributionError):
    """Raised when the bundled distribution is internally inconsistent."""


class ConflictError(DistributionError):
    """Raised when a target would be overwritten or removed unsafely."""


def _reject_duplicate_keys(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValidationError("cannot read JSON %s: %s" % (path, exc)) from exc
    if not isinstance(value, dict):
        raise ValidationError("JSON root must be an object: %s" % path)
    return value


def load_yaml_strict(path: Path) -> Dict[str, Any]:
    """Load YAML while rejecting duplicate mapping keys at every depth."""
    try:
        import yaml
    except ImportError as exc:
        raise ValidationError("PyYAML is required for canonical master validation") from exc

    class StrictSafeLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader: Any, node: Any, deep: bool = False) -> Dict[Any, Any]:
        loader.flatten_mapping(node)
        result: Dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            try:
                duplicate = key in result
            except TypeError as exc:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found unhashable key",
                    key_node.start_mark,
                ) from exc
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found duplicate key %r" % key,
                    key_node.start_mark,
                )
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    StrictSafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
    )
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = yaml.load(handle, Loader=StrictSafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError("cannot read strict YAML %s: %s" % (path, exc)) from exc
    if not isinstance(value, dict):
        raise ValidationError("YAML root must be a mapping: %s" % path)
    return value


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(raw: Any) -> Optional[str]:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        return None
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        return None
    return candidate.as_posix()


def _contained_path(root: Path, relative: str) -> Path:
    safe = _safe_relative(relative)
    if safe is None:
        raise ValidationError("unsafe relative path: %r" % relative)
    root = root.resolve()
    candidate = root.joinpath(*PurePosixPath(safe).parts)
    if candidate.is_symlink():
        raise ConflictError("refusing symbolic-link target: %s" % candidate)
    resolved = candidate.resolve(strict=False)
    try:
        common = Path(os.path.commonpath((str(root), str(resolved))))
    except ValueError as exc:
        raise ConflictError("target escapes installation root: %s" % candidate) from exc
    if common != root:
        raise ConflictError("target escapes installation root: %s" % candidate)
    return candidate


def load_manifest(manifest_path: Path) -> Tuple[Path, Dict[str, Any], Dict[str, Dict[str, Any]]]:
    manifest_path = manifest_path.resolve()
    root = manifest_path.parent
    manifest = load_json(manifest_path)
    profiles: Dict[str, Dict[str, Any]] = {}
    declared = manifest.get("profiles", {})
    if isinstance(declared, dict):
        for profile_id, relative in declared.items():
            safe = _safe_relative(relative)
            if safe is None:
                continue
            profile_path = root.joinpath(*PurePosixPath(safe).parts)
            profiles[profile_id] = load_json(profile_path)
    return root, manifest, profiles


def load_canonical_manifest(
    manifest_path: Path,
) -> Tuple[Path, Dict[str, Any], Dict[str, Dict[str, Any]]]:
    manifest_path = manifest_path.resolve()
    canonical = manifest_path.parent / "manifest.yaml"
    if manifest_path != canonical:
        raise ValidationError("installer accepts only the canonical distribution/manifest.yaml")
    return load_manifest(canonical)


def _string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
    )


def _nonempty_string_list(value: Any) -> bool:
    return bool(value) and _string_list(value)


def resolve_profile_ids(
    selected: str, profiles: Mapping[str, Mapping[str, Any]]
) -> List[str]:
    if selected not in profiles:
        raise ValidationError("unknown profile: %s" % selected)
    resolved: List[str] = []
    visiting: List[str] = []

    def visit(profile_id: str) -> None:
        if profile_id in resolved:
            return
        if profile_id in visiting:
            cycle = " -> ".join(visiting + [profile_id])
            raise ValidationError("profile dependency cycle: %s" % cycle)
        profile = profiles.get(profile_id)
        if profile is None:
            raise ValidationError("profile dependency does not exist: %s" % profile_id)
        visiting.append(profile_id)
        dependencies = profile.get("extends", [])
        includes = profile.get("includes", [])
        if not isinstance(dependencies, list) or not isinstance(includes, list):
            raise ValidationError("profile dependencies must be lists: %s" % profile_id)
        for dependency in list(dependencies) + list(includes):
            if not isinstance(dependency, str):
                raise ValidationError("non-string dependency in profile %s" % profile_id)
            visit(dependency)
        visiting.pop()
        resolved.append(profile_id)

    visit(selected)
    return resolved


def render_artifact(
    root: Path,
    manifest: Mapping[str, Any],
    owner_profile: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> bytes:
    parts: List[str] = []
    template_parts = artifact.get("template_parts", [])
    if not _nonempty_string_list(template_parts):
        raise ValidationError("artifact template_parts must be a non-empty string list")
    for relative in template_parts:
        safe = _safe_relative(relative)
        if safe is None:
            raise ValidationError("unsafe template path in %s" % owner_profile.get("id"))
        path = root.joinpath(*PurePosixPath(safe).parts)
        try:
            parts.append(path.read_text(encoding="utf-8").rstrip())
        except OSError as exc:
            raise ValidationError("cannot read template %s: %s" % (path, exc)) from exc
    rendered = "\n\n".join(parts).rstrip() + "\n"
    replacements = {
        "FRAMEWORK_VERSION": str(manifest.get("framework", {}).get("version", "")),
        "PROFILE_ID": str(owner_profile.get("id", "")),
    }
    rendered = TOKEN_RE.sub(lambda match: replacements.get(match.group(1), match.group(0)), rendered)
    unresolved = sorted(set(TOKEN_RE.findall(rendered)))
    if unresolved:
        raise ValidationError("unresolved template tokens: %s" % ", ".join(unresolved))
    return rendered.encode("utf-8")


def resolved_artifacts(
    root: Path,
    manifest: Mapping[str, Any],
    profiles: Mapping[str, Mapping[str, Any]],
    selected: str,
) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    destinations: Dict[str, str] = {}
    for profile_id in resolve_profile_ids(selected, profiles):
        profile = profiles[profile_id]
        profile_artifacts = profile.get("artifacts", [])
        if not isinstance(profile_artifacts, list):
            raise ValidationError("profile artifacts must be a list: %s" % profile_id)
        for artifact in profile_artifacts:
            if not isinstance(artifact, dict):
                raise ValidationError("profile contains a non-object artifact: %s" % profile_id)
            destination = artifact.get("destination")
            if _safe_relative(destination) is None:
                raise ValidationError("unsafe artifact destination in profile %s" % profile_id)
            content = render_artifact(root, manifest, profile, artifact)
            digest = _sha256_bytes(content)
            prior = destinations.get(destination)
            if prior is not None:
                if prior != digest:
                    raise ValidationError(
                        "aggregate produces conflicting content for %s" % destination
                    )
                continue
            destinations[destination] = digest
            artifacts.append(
                {
                    "id": artifact.get("id"),
                    "owner_profile": profile_id,
                    "destination": destination,
                    "content": content,
                    "sha256": digest,
                }
            )
    return artifacts


_MISSING = object()


def _mapping_path(value: Mapping[str, Any], dotted: str) -> Any:
    current: Any = value
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


def _master_contract_errors(master: Mapping[str, Any], framework_version: str) -> List[str]:
    expected = {
        "master_document.version": framework_version,
        "master_document.activation_policy.not_auto_on": True,
        "master_document.activation_policy.still_subordinate_to_agent_rules": True,
        "master_document.activation_policy.membrane_binding.permission_rule": (
            "scope propagation never propagates permissions or authority"
        ),
        "master_document.activation_membrane.mode": "scoped_adaptive",
        "master_document.activation_membrane.propagation.to_subtasks": "scope_only",
        "master_document.activation_membrane.propagation.to_agents": "scope_only",
        "master_document.activation_membrane.propagation.permissions": "never",
        "master_document.activation_membrane.propagation.authority": "never",
        "master_document.reach_max_distribution.manifest": "distribution/manifest.yaml",
        "master_document.reach_max_distribution.profiles": [
            "core",
            "openai",
            "claude",
            "copilot",
            "cursor",
            "mcp",
            "ci",
            "all",
        ],
        "master_document.reach_max_distribution.profile_contract.declares": [
            "files",
            "capabilities",
            "limits",
            "compatibility",
            "validations",
        ],
        "master_document.reach_max_distribution.installer.path": "distribution/install.py",
        "master_document.reach_max_distribution.installer.overwrite_default": False,
        "master_document.reach_max_distribution.installer.force_requires_timestamped_backup": True,
        "master_document.reach_max_distribution.installer.dry_run": True,
        "master_document.reach_max_distribution.authority_rule": (
            "host rules and permissions always dominate profile declarations"
        ),
    }
    errors: List[str] = []
    for path, expected_value in expected.items():
        actual = _mapping_path(master, path)
        if actual is _MISSING:
            errors.append("canonical master lacks contract field: %s" % path)
        elif actual != expected_value:
            errors.append("canonical master contract mismatch at %s" % path)

    hard_limits = _mapping_path(master, "master_document.activation_membrane.hard_limits")
    required_limits = {
        "no claim of global or perpetual activation",
        "no claim of platform permission escalation",
        "no claim of weight mutation from prompt, context or skill",
        "no audit or memory claim without a materialized artifact",
    }
    if (
        not isinstance(hard_limits, list)
        or not all(isinstance(item, str) for item in hard_limits)
        or not required_limits.issubset(set(hard_limits))
    ):
        errors.append("canonical master activation_membrane.hard_limits is incomplete")
    return errors


def validate_distribution(
    distribution_root: Path, repository_root: Optional[Path] = None
) -> List[str]:
    root = distribution_root.resolve()
    manifest_path = root / "manifest.yaml"
    errors: List[str] = []
    try:
        loaded_root, manifest, profiles = load_manifest(manifest_path)
    except ValidationError as exc:
        return [str(exc)]
    if loaded_root != root:
        errors.append("manifest root resolution mismatch")

    if manifest.get("schema_version") != "1.0":
        errors.append("manifest schema_version must be 1.0")
    manifest_version = manifest.get("manifest_version")
    framework_version = manifest.get("framework", {}).get("version")
    distribution_version = manifest.get("distribution", {}).get("version")
    for name, value in (
        ("manifest_version", manifest_version),
        ("framework.version", framework_version),
        ("distribution.version", distribution_version),
    ):
        if not isinstance(value, str) or not SEMVER_RE.fullmatch(value):
            errors.append("%s must be strict semantic version x.y.z" % name)
    if manifest_version != framework_version or manifest_version != distribution_version:
        errors.append("manifest, framework, and distribution versions must match")
    if manifest_version != "2.0.0":
        errors.append("this release requires manifest version 2.0.0")
    if manifest.get("framework", {}).get("name") != "M3C3":
        errors.append("framework name must be M3C3")
    distribution_section = manifest.get("distribution", {})
    if distribution_section.get("name") != "REACH-MAX":
        errors.append("distribution name must be REACH-MAX")
    if distribution_section.get("profile_directory") != "profiles":
        errors.append("distribution profile_directory must be profiles")
    if distribution_section.get("template_directory") != "templates":
        errors.append("distribution template_directory must be templates")
    if distribution_section.get("transaction_wal") != TRANSACTION_WAL:
        errors.append("distribution transaction_wal is not canonical")
    if distribution_section.get("transaction_root") != TRANSACTION_ROOT:
        errors.append("distribution transaction_root is not canonical")
    if manifest.get("invariants") != EXPECTED_POLICY:
        errors.append("manifest invariants do not match the REACH-MAX safety policy")
    if manifest.get("framework", {}).get("canonical_authority") != "master.yaml":
        errors.append("framework canonical authority must be master.yaml")

    declared = manifest.get("profiles")
    if not isinstance(declared, dict):
        errors.append("profiles must be an object")
        declared = {}
    declared_ids = set(declared)
    required_declared = manifest.get("required_profiles")
    if not _string_list(required_declared) or set(required_declared) != REQUIRED_PROFILES:
        errors.append("required_profiles must contain the eight REACH-MAX profiles exactly")
    if declared_ids != REQUIRED_PROFILES:
        errors.append("declared profiles must contain the eight REACH-MAX profiles exactly")
    for profile_id, relative in declared.items():
        if relative != "profiles/%s.json" % profile_id:
            errors.append("profile %s must use its versioned profiles/<id>.json path" % profile_id)
    if set(profiles) != declared_ids:
        errors.append("one or more declared profile files could not be loaded")
    if manifest.get("aggregate_profile") != "all":
        errors.append("aggregate_profile must be all")

    artifact_ids: set = set()
    for declared_id in sorted(declared_ids & set(profiles)):
        profile = profiles[declared_id]
        if profile.get("schema_version") != "1.0":
            errors.append("profile %s schema_version must be 1.0" % declared_id)
        if profile.get("id") != declared_id:
            errors.append("profile file identity mismatch for %s" % declared_id)
        if profile.get("version") != distribution_version:
            errors.append("profile %s version does not match distribution" % declared_id)
        expected_kind = "aggregate" if declared_id == "all" else ("base" if declared_id == "core" else "adapter")
        if profile.get("kind") != expected_kind:
            errors.append("profile %s kind must be %s" % (declared_id, expected_kind))
        if not _string_list(profile.get("extends")):
            errors.append("profile %s extends must be a unique string list" % declared_id)
        if not _nonempty_string_list(profile.get("targets")):
            errors.append("profile %s targets must be a non-empty unique string list" % declared_id)
        if profile.get("policy") != EXPECTED_POLICY:
            errors.append("profile %s has an unsafe or incomplete policy" % declared_id)
        if not _nonempty_string_list(profile.get("capabilities")):
            errors.append("profile %s must declare explicit capabilities" % declared_id)
        if not _nonempty_string_list(profile.get("limits")):
            errors.append("profile %s must declare explicit limits" % declared_id)
        if not _nonempty_string_list(profile.get("files")):
            errors.append("profile %s must declare explicit files" % declared_id)
        compatibility_declaration = profile.get("compatibility")
        if (
            not isinstance(compatibility_declaration, dict)
            or compatibility_declaration.get("matrix") != "compatibility.json"
            or not isinstance(compatibility_declaration.get("status"), str)
        ):
            errors.append("profile %s must declare compatibility" % declared_id)
        if not _nonempty_string_list(profile.get("validations")):
            errors.append("profile %s must declare validations" % declared_id)
        artifacts = profile.get("artifacts")
        if not isinstance(artifacts, list):
            errors.append("profile %s artifacts must be a list" % declared_id)
            artifacts = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                errors.append("profile %s contains a non-object artifact" % declared_id)
                continue
            artifact_id = artifact.get("id")
            if not isinstance(artifact_id, str) or not artifact_id:
                errors.append("profile %s has an artifact without id" % declared_id)
            elif artifact_id in artifact_ids:
                errors.append("duplicate artifact id: %s" % artifact_id)
            else:
                artifact_ids.add(artifact_id)
            if _safe_relative(artifact.get("destination")) is None:
                errors.append("profile %s has unsafe artifact destination" % declared_id)
            parts = artifact.get("template_parts")
            if not _nonempty_string_list(parts):
                errors.append("profile %s artifact %s needs template_parts" % (declared_id, artifact_id))
                continue
            for relative in parts:
                safe = _safe_relative(relative)
                if safe is None or not safe.startswith("templates/"):
                    errors.append("profile %s has template outside templates/: %s" % (declared_id, relative))
                elif not root.joinpath(*PurePosixPath(safe).parts).is_file():
                    errors.append("profile %s references missing/unsafe template %s" % (declared_id, relative))
        if declared_id != "all" and _nonempty_string_list(profile.get("files")):
            artifact_destinations = {
                artifact.get("destination")
                for artifact in artifacts
                if isinstance(artifact, dict) and isinstance(artifact.get("destination"), str)
            }
            if set(profile["files"]) != artifact_destinations:
                errors.append("profile %s files do not match its artifacts" % declared_id)

    aggregate = profiles.get("all", {})
    includes = aggregate.get("includes")
    if not _string_list(includes) or set(includes) != REQUIRED_PROFILES - {"all"}:
        errors.append("all profile must include every non-aggregate profile exactly once")
    if aggregate.get("artifacts") != []:
        errors.append("all profile must aggregate profiles rather than duplicate artifacts")
    for profile_id in REQUIRED_PROFILES - {"core", "all"}:
        if profiles.get(profile_id, {}).get("extends") != ["core"]:
            errors.append("profile %s must extend core exactly once" % profile_id)

    for profile_id in sorted(set(profiles)):
        try:
            resolve_profile_ids(profile_id, profiles)
        except ValidationError as exc:
            errors.append(str(exc))
    try:
        all_artifacts = resolved_artifacts(root, manifest, profiles, "all")
        expected_artifact_count = sum(
            len(profile.get("artifacts", []))
            for profile_id, profile in profiles.items()
            if profile_id != "all"
        )
        if len(all_artifacts) != expected_artifact_count:
            errors.append("all profile does not resolve every unique artifact")
        if _nonempty_string_list(aggregate.get("files")) and set(aggregate["files"]) != {
            artifact["destination"] for artifact in all_artifacts
        }:
            errors.append("all profile files do not match the resolved aggregate")
        if any(
            artifact["destination"] == manifest.get("distribution", {}).get("state_manifest")
            for artifact in all_artifacts
        ):
            errors.append("an artifact destination collides with the installer state manifest")
    except ValidationError as exc:
        errors.append(str(exc))

    compatibility_path = manifest.get("distribution", {}).get("compatibility_matrix")
    if _safe_relative(compatibility_path) is None:
        errors.append("compatibility matrix path is unsafe")
    else:
        try:
            compatibility = load_json(root / compatibility_path)
            rows = compatibility.get("rows")
            if compatibility.get("schema_version") != "1.0":
                errors.append("compatibility matrix schema_version must be 1.0")
            if compatibility.get("distribution_version") != distribution_version:
                errors.append("compatibility matrix version mismatch")
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                errors.append("compatibility rows must be objects")
            else:
                row_ids = [row.get("profile") for row in rows]
                if (
                    not all(isinstance(profile_id, str) for profile_id in row_ids)
                    or len(row_ids) != len(set(row_ids))
                    or set(row_ids) != REQUIRED_PROFILES
                ):
                    errors.append("compatibility matrix must cover each profile exactly once")
                for row in rows:
                    for key in ("environment", "status", "instruction_surface", "loading"):
                        if not isinstance(row.get(key), str) or not row[key]:
                            errors.append("compatibility row %s lacks %s" % (row.get("profile"), key))
                    row_profile = row.get("profile")
                    profile = profiles.get(row_profile, {}) if isinstance(row_profile, str) else {}
                    if profile.get("compatibility", {}).get("status") != row.get("status"):
                        errors.append(
                            "profile %s compatibility status does not match the matrix"
                            % row.get("profile")
                        )
                    if (
                        row_profile != "all"
                        and _nonempty_string_list(profile.get("files"))
                        and len(profile["files"]) == 1
                        and row.get("instruction_surface") != profile["files"][0]
                    ):
                        errors.append(
                            "profile %s instruction surface does not match the matrix"
                            % row_profile
                        )
        except ValidationError as exc:
            errors.append(str(exc))

    core_template = root / "templates" / "core.md"
    try:
        core_text = core_template.read_text(encoding="utf-8")
        for marker in sorted(REQUIRED_TEMPLATE_MARKERS):
            if marker not in core_text:
                errors.append("core template lacks required marker: %s" % marker)
    except OSError as exc:
        errors.append("cannot read core template: %s" % exc)

    state_manifest = manifest.get("distribution", {}).get("state_manifest")
    if _safe_relative(state_manifest) is None:
        errors.append("state manifest path is unsafe")

    if repository_root is not None:
        repository_root = repository_root.resolve()
        master_path = repository_root / "master.yaml"
        if not master_path.is_file():
            errors.append("canonical master.yaml is missing")
        else:
            try:
                master = load_yaml_strict(master_path)
            except ValidationError as exc:
                errors.append(str(exc))
            else:
                errors.extend(_master_contract_errors(master, str(framework_version)))
    return sorted(set(errors))


def _utc_stamp(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    return current.strftime("%Y%m%dT%H%M%S.%fZ")


def _iso_now(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _backup_relative(target: Path, destination: str, stamp: str) -> str:
    pure = PurePosixPath(destination)
    base = pure.with_name(pure.name + ".m3c3-backup-" + stamp)
    candidate = base
    index = 1
    while _contained_path(target, candidate.as_posix()).exists():
        candidate = base.with_name(base.name + "-" + str(index))
        index += 1
    return candidate.as_posix()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".reach-max-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _manifest_sha256(root: Path) -> str:
    return _sha256_path(root / "manifest.yaml")


def _state_skeleton(
    root: Path, manifest: Mapping[str, Any], stamp_iso: str
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "distribution": "REACH-MAX",
        "distribution_version": manifest["distribution"]["version"],
        "manifest_version": manifest["manifest_version"],
        "manifest_sha256": _manifest_sha256(root),
        "installed_profiles": [],
        "created_at": stamp_iso,
        "updated_at": stamp_iso,
        "artifacts": [],
    }


def _backup_belongs_to(destination: str, backup: Any) -> bool:
    if _safe_relative(backup) is None:
        return False
    destination_path = PurePosixPath(destination)
    backup_path = PurePosixPath(backup)
    prefix = destination_path.name + ".m3c3-backup-"
    if backup_path.parent != destination_path.parent or not backup_path.name.startswith(prefix):
        return False
    return bool(BACKUP_STAMP_RE.fullmatch(backup_path.name[len(prefix) :]))


def _expected_state_artifacts(
    root: Path,
    manifest: Mapping[str, Any],
    profiles: Mapping[str, Mapping[str, Any]],
    installed_profiles: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    expected: Dict[str, Dict[str, Any]] = {}
    for selected in installed_profiles:
        for artifact in resolved_artifacts(root, manifest, profiles, selected):
            destination = artifact["destination"]
            prior = expected.get(destination)
            if prior is not None and (
                prior["sha256"] != artifact["sha256"]
                or prior["owner_profile"] != artifact["owner_profile"]
            ):
                raise ValidationError("installed profiles disagree on %s" % destination)
            expected[destination] = artifact
    return expected


def _validate_state(
    state: Mapping[str, Any],
    root: Path,
    manifest: Mapping[str, Any],
    profiles: Mapping[str, Mapping[str, Any]],
    target: Optional[Path] = None,
) -> None:
    if state.get("schema_version") != "1.0" or state.get("distribution") != "REACH-MAX":
        raise ValidationError("target state manifest is not a REACH-MAX v2 manifest")
    if state.get("distribution_version") != manifest["distribution"]["version"]:
        raise ValidationError("state distribution version does not match the canonical manifest")
    if state.get("manifest_version") != manifest["manifest_version"]:
        raise ValidationError("state manifest version does not match the canonical manifest")
    if state.get("manifest_sha256") != _manifest_sha256(root):
        raise ValidationError("state is not bound to the current canonical manifest")
    installed_profiles = state.get("installed_profiles")
    if not _nonempty_string_list(installed_profiles):
        raise ValidationError("state installed_profiles is invalid")
    if installed_profiles != sorted(installed_profiles):
        raise ValidationError("state installed_profiles must be canonical and sorted")
    if not set(installed_profiles).issubset(set(profiles)):
        raise ValidationError("state contains an unknown installed profile")
    expected = _expected_state_artifacts(root, manifest, profiles, installed_profiles)
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValidationError("state artifacts must be a list")
    seen: set = set()
    destination_order: List[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValidationError("state contains a non-object artifact")
        destination = artifact.get("destination")
        if _safe_relative(destination) is None or destination in seen:
            raise ValidationError("state contains unsafe or duplicate destination")
        seen.add(destination)
        destination_order.append(destination)
        canonical = expected.get(destination)
        if canonical is None:
            raise ValidationError("state contains non-canonical destination: %s" % destination)
        if artifact.get("ownership") not in {"created", "replaced", "preexisting_identical"}:
            raise ValidationError("state contains invalid ownership for %s" % destination)
        digest = artifact.get("installed_sha256")
        if digest != canonical["sha256"]:
            raise ValidationError("state digest is not canonical for %s" % destination)
        record_profiles = artifact.get("profiles")
        if record_profiles != [canonical["owner_profile"]]:
            raise ValidationError("state profile ownership is not canonical for %s" % destination)
        safety_backups = artifact.get("safety_backups")
        if not _string_list(safety_backups) and safety_backups != []:
            raise ValidationError("state contains invalid safety backups for %s" % destination)
        if any(not _backup_belongs_to(destination, backup) for backup in safety_backups):
            raise ValidationError("state contains invalid safety backups for %s" % destination)
        ownership = artifact["ownership"]
        if ownership == "replaced":
            original_backup = artifact.get("original_backup")
            original_sha256 = artifact.get("original_sha256")
            if not _backup_belongs_to(destination, original_backup):
                raise ValidationError("state lacks original backup for %s" % destination)
            if not isinstance(original_sha256, str) or not SHA256_RE.fullmatch(original_sha256):
                raise ValidationError("state lacks original digest for %s" % destination)
        elif artifact.get("original_backup") is not None or artifact.get("original_sha256") is not None:
            raise ValidationError("state has impossible original provenance for %s" % destination)

        if target is not None:
            backup_paths = list(safety_backups)
            if ownership == "replaced":
                backup_paths.append(artifact["original_backup"])
            for backup in backup_paths:
                backup_path = _contained_path(target, backup)
                if not backup_path.is_file():
                    raise ValidationError("state backup is missing for %s" % destination)
            if ownership == "replaced":
                original_path = _contained_path(target, artifact["original_backup"])
                if _sha256_path(original_path) != artifact["original_sha256"]:
                    raise ValidationError("state original backup digest mismatch for %s" % destination)
    if seen != set(expected):
        missing = sorted(set(expected) - seen)
        raise ValidationError("state is missing canonical artifacts: %s" % ", ".join(missing))
    if destination_order != sorted(destination_order):
        raise ValidationError("state artifacts must use canonical destination order")


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _transaction_wal_path(target: Path) -> Path:
    return _contained_path(target, TRANSACTION_WAL)


def _transaction_dir_relative(transaction_id: str) -> str:
    return "%s/%s" % (TRANSACTION_ROOT, transaction_id)


def _allowed_transaction_destinations(
    root: Path,
    manifest: Mapping[str, Any],
    profiles: Mapping[str, Mapping[str, Any]],
) -> set:
    destinations = {
        artifact["destination"]
        for artifact in resolved_artifacts(root, manifest, profiles, "all")
    }
    destinations.add(manifest["distribution"]["state_manifest"])
    return destinations


def _validate_transaction_wal(
    wal: Mapping[str, Any],
    target: Path,
    root: Path,
    manifest: Mapping[str, Any],
    profiles: Mapping[str, Mapping[str, Any]],
) -> None:
    expected_wal_keys = {
        "schema_version",
        "distribution",
        "distribution_version",
        "manifest_sha256",
        "transaction_id",
        "status",
        "changes",
        "generated_backups",
    }
    if set(wal) != expected_wal_keys:
        raise ConflictError("pending transaction WAL has an invalid schema")
    if wal.get("schema_version") != "1.0" or wal.get("distribution") != "REACH-MAX":
        raise ConflictError("pending transaction WAL has an invalid identity")
    if wal.get("distribution_version") != manifest["distribution"]["version"]:
        raise ConflictError("pending transaction WAL version does not match the distribution")
    if wal.get("manifest_sha256") != _manifest_sha256(root):
        raise ConflictError("pending transaction WAL is not bound to the canonical manifest")
    transaction_id = wal.get("transaction_id")
    if not isinstance(transaction_id, str) or not TRANSACTION_ID_RE.fullmatch(transaction_id):
        raise ConflictError("pending transaction WAL has an invalid transaction id")
    if wal.get("status") not in {"prepared", "committed", "rolled_back"}:
        raise ConflictError("pending transaction WAL has an invalid status")
    transaction_dir = _transaction_dir_relative(transaction_id)
    allowed = _allowed_transaction_destinations(root, manifest, profiles)
    changes = wal.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ConflictError("pending transaction WAL has no changes")
    seen: set = set()
    expected_snapshots: set = set()
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            raise ConflictError("pending transaction WAL contains an invalid change")
        if set(change) != {
            "destination",
            "before_exists",
            "before_sha256",
            "snapshot",
            "after_exists",
            "after_sha256",
        }:
            raise ConflictError("pending transaction WAL change has an invalid schema")
        destination = change.get("destination")
        if destination not in allowed or destination in seen:
            raise ConflictError("pending transaction WAL contains a non-canonical destination")
        seen.add(destination)
        before_exists = change.get("before_exists")
        if not isinstance(before_exists, bool):
            raise ConflictError("pending transaction WAL has invalid existence provenance")
        expected_snapshot = "%s/snapshot-%04d.bin" % (transaction_dir, index)
        snapshot = change.get("snapshot")
        before_sha256 = change.get("before_sha256")
        if before_exists:
            if snapshot != expected_snapshot or not isinstance(
                before_sha256, str
            ) or not SHA256_RE.fullmatch(before_sha256):
                raise ConflictError("pending transaction WAL has invalid snapshot provenance")
            expected_snapshots.add(snapshot)
            if wal.get("status") == "prepared":
                snapshot_path = _contained_path(target, snapshot)
                if not snapshot_path.is_file() or _sha256_path(snapshot_path) != before_sha256:
                    raise ConflictError("pending transaction snapshot is missing or corrupt")
        elif snapshot is not None or before_sha256 is not None:
            raise ConflictError("pending transaction WAL has impossible absent-file provenance")

        after_exists = change.get("after_exists")
        after_sha256 = change.get("after_sha256")
        if not isinstance(after_exists, bool):
            raise ConflictError("pending transaction WAL has invalid post-state provenance")
        if after_exists:
            if not isinstance(after_sha256, str) or not SHA256_RE.fullmatch(after_sha256):
                raise ConflictError("pending transaction WAL has invalid post-state digest")
        elif after_sha256 is not None:
            raise ConflictError("pending transaction WAL has impossible absent post-state")
        if (before_exists, before_sha256) == (after_exists, after_sha256):
            raise ConflictError("pending transaction WAL contains a no-op change")

    if wal.get("status") == "prepared":
        transaction_path = _contained_path(target, transaction_dir)
        if not transaction_path.is_dir():
            raise ConflictError("pending transaction snapshot root is missing")
        actual_snapshots = set()
        for entry in transaction_path.iterdir():
            if not entry.is_file():
                raise ConflictError("pending transaction snapshot root contains an invalid entry")
            actual_snapshots.add(
                "%s/%s" % (transaction_dir, entry.name)
            )
        if actual_snapshots != expected_snapshots:
            raise ConflictError("pending transaction snapshot set is not canonical")

    generated_backups = wal.get("generated_backups")
    if not _string_list(generated_backups) and generated_backups != []:
        raise ConflictError("pending transaction WAL has invalid generated backups")
    if generated_backups != sorted(generated_backups):
        raise ConflictError("pending transaction WAL backups are not canonical")
    for backup in generated_backups:
        owners = [
            change
            for change in changes
            if _backup_belongs_to(change["destination"], backup)
        ]
        if len(owners) != 1 or not owners[0]["before_exists"]:
            raise ConflictError("pending transaction WAL has an unowned backup path")


def _begin_transaction(
    target: Path,
    root: Path,
    manifest: Mapping[str, Any],
    profiles: Mapping[str, Mapping[str, Any]],
    after_states: Mapping[str, Optional[str]],
    generated_backups: Sequence[str],
) -> Dict[str, Any]:
    transaction_id = secrets.token_hex(16)
    transaction_dir_relative = _transaction_dir_relative(transaction_id)
    transaction_dir = _contained_path(target, transaction_dir_relative)
    if transaction_dir.exists():
        raise ConflictError("transaction directory collision")
    transaction_dir.mkdir(parents=True, exist_ok=False)
    changes: List[Dict[str, Any]] = []
    unique_destinations = list(after_states)
    if not unique_destinations:
        raise ConflictError("transaction must contain at least one mutation")
    try:
        for index, destination in enumerate(unique_destinations):
            after_sha256 = after_states[destination]
            if after_sha256 is not None and (
                not isinstance(after_sha256, str) or not SHA256_RE.fullmatch(after_sha256)
            ):
                raise ConflictError("transaction has an invalid expected post-state digest")
            path = _contained_path(target, destination)
            if path.exists() and not path.is_file():
                raise ConflictError("transaction target is not a regular file: %s" % destination)
            if path.exists():
                snapshot_relative = "%s/snapshot-%04d.bin" % (
                    transaction_dir_relative,
                    index,
                )
                snapshot_path = _contained_path(target, snapshot_relative)
                shutil.copy2(path, snapshot_path)
                changes.append(
                    {
                        "destination": destination,
                        "before_exists": True,
                        "before_sha256": _sha256_path(snapshot_path),
                        "snapshot": snapshot_relative,
                        "after_exists": after_sha256 is not None,
                        "after_sha256": after_sha256,
                    }
                )
            else:
                changes.append(
                    {
                        "destination": destination,
                        "before_exists": False,
                        "before_sha256": None,
                        "snapshot": None,
                        "after_exists": after_sha256 is not None,
                        "after_sha256": after_sha256,
                    }
                )
        for backup in generated_backups:
            backup_path = _contained_path(target, backup)
            if backup_path.exists():
                raise ConflictError("transaction backup target already exists: %s" % backup)
        wal = {
            "schema_version": "1.0",
            "distribution": "REACH-MAX",
            "distribution_version": manifest["distribution"]["version"],
            "manifest_sha256": _manifest_sha256(root),
            "transaction_id": transaction_id,
            "status": "prepared",
            "changes": changes,
            "generated_backups": sorted(set(generated_backups)),
        }
        _validate_transaction_wal(wal, target, root, manifest, profiles)
        _atomic_write(_transaction_wal_path(target), _json_bytes(wal))
        return wal
    except Exception:
        if transaction_dir.exists():
            shutil.rmtree(transaction_dir)
        raise


def _cleanup_transaction(target: Path, wal: Mapping[str, Any]) -> None:
    transaction_id = str(wal["transaction_id"])
    transaction_dir = _contained_path(target, _transaction_dir_relative(transaction_id))
    if transaction_dir.exists():
        if not transaction_dir.is_dir():
            raise ConflictError("transaction snapshot root is not a directory")
        expected_snapshots = {
            change["snapshot"]
            for change in wal["changes"]
            if change["snapshot"] is not None
        }
        actual_snapshots = {
            "%s/%s" % (_transaction_dir_relative(transaction_id), entry.name)
            for entry in transaction_dir.iterdir()
            if entry.is_file()
        }
        if actual_snapshots != expected_snapshots or any(
            not entry.is_file() for entry in transaction_dir.iterdir()
        ):
            raise ConflictError("transaction snapshot root changed before cleanup")
        for snapshot in sorted(expected_snapshots):
            _contained_path(target, snapshot).unlink()
        transaction_dir.rmdir()
    wal_path = _transaction_wal_path(target)
    if wal_path.exists():
        if not wal_path.is_file():
            raise ConflictError("transaction WAL is not a regular file")
        if load_json(wal_path) != wal:
            raise ConflictError("transaction WAL changed before cleanup")
        wal_path.unlink()


def _recover_pending_transaction(
    target: Path,
    root: Path,
    manifest: Mapping[str, Any],
    profiles: Mapping[str, Mapping[str, Any]],
    *,
    trusted_wal: Optional[Mapping[str, Any]] = None,
) -> bool:
    wal_path = _transaction_wal_path(target)
    if not wal_path.exists():
        return False
    if not wal_path.is_file():
        raise ConflictError("transaction WAL is not a regular file")
    wal = load_json(wal_path)
    _validate_transaction_wal(wal, target, root, manifest, profiles)
    if trusted_wal is None:
        raise ConflictError(
            "pending transaction WAL is not authenticated; automatic recovery is refused "
            "and manual reconciliation is required"
        )
    if wal != trusted_wal or wal["status"] != "prepared":
        raise ConflictError("pending transaction WAL does not match the live transaction receipt")

    current_states: Dict[str, Tuple[bool, Optional[str]]] = {}
    for change in wal["changes"]:
        path = _contained_path(target, change["destination"])
        if path.exists() and not path.is_file():
            raise ConflictError("rollback target became non-regular: %s" % change["destination"])
        current = (path.exists(), _sha256_path(path) if path.exists() else None)
        before = (change["before_exists"], change["before_sha256"])
        after = (change["after_exists"], change["after_sha256"])
        if current not in {before, after}:
            raise ConflictError(
                "rollback target does not match a verified before/after state: %s"
                % change["destination"]
            )
        current_states[change["destination"]] = current

    for backup in wal["generated_backups"]:
        backup_path = _contained_path(target, backup)
        if not backup_path.exists():
            continue
        if not backup_path.is_file():
            raise ConflictError("rollback backup became non-regular: %s" % backup)
        owner = next(
            change
            for change in wal["changes"]
            if _backup_belongs_to(change["destination"], backup)
        )
        if _sha256_path(backup_path) != owner["before_sha256"]:
            raise ConflictError("rollback backup does not match its verified source: %s" % backup)

    for change in reversed(wal["changes"]):
        path = _contained_path(target, change["destination"])
        if change["before_exists"]:
            if current_states[change["destination"]] != (
                True,
                change["before_sha256"],
            ):
                snapshot_path = _contained_path(target, change["snapshot"])
                _atomic_write(path, snapshot_path.read_bytes())
                shutil.copymode(snapshot_path, path)
        elif current_states[change["destination"]][0]:
            path.unlink()
    for backup in wal["generated_backups"]:
        backup_path = _contained_path(target, backup)
        if backup_path.exists():
            if not backup_path.is_file():
                raise ConflictError("rollback backup became non-regular: %s" % backup)
            backup_path.unlink()
    rolled_back = copy.deepcopy(wal)
    rolled_back["status"] = "rolled_back"
    _atomic_write(wal_path, _json_bytes(rolled_back))
    _cleanup_transaction(target, rolled_back)
    return True


def _commit_transaction(target: Path, wal: Dict[str, Any]) -> None:
    committed = copy.deepcopy(wal)
    committed["status"] = "committed"
    _atomic_write(_transaction_wal_path(target), _json_bytes(committed))
    _cleanup_transaction(target, committed)


def _assert_expected_digest(target: Path, destination: str, expected: Optional[str]) -> None:
    path = _contained_path(target, destination)
    if path.exists() and not path.is_file():
        raise ConflictError("transaction target became non-regular: %s" % destination)
    actual = _sha256_path(path) if path.exists() else None
    if actual != expected:
        raise ConflictError("target changed after preflight: %s" % destination)


def _public_action(action: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in action.items()
        if key not in {"content", "expected_current_sha256"}
    }


def install(
    manifest_path: Path,
    profile_id: str,
    target: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    now: Optional[datetime] = None,
    _failure_injector: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    root, manifest, profiles = load_canonical_manifest(manifest_path)
    errors = validate_distribution(root)
    if errors:
        raise ValidationError("invalid distribution:\n- " + "\n- ".join(errors))
    target = target.resolve()
    if not target.is_dir():
        raise ValidationError("installation target must be an existing directory: %s" % target)
    if _transaction_wal_path(target).exists():
        if dry_run:
            raise ConflictError("pending transaction requires recovery before dry-run")
        _recover_pending_transaction(target, root, manifest, profiles)
    wanted = resolved_artifacts(root, manifest, profiles, profile_id)
    stamp = _utc_stamp(now)
    stamp_iso = _iso_now(now)
    state_relative = manifest["distribution"]["state_manifest"]
    state_path = _contained_path(target, state_relative)
    expected_state_sha256 = _sha256_path(state_path) if state_path.is_file() else None
    state_backup: Optional[str] = None
    if state_path.exists():
        if not state_path.is_file():
            raise ConflictError("state manifest target is not a regular file: %s" % state_relative)
        try:
            state = load_json(state_path)
            _validate_state(state, root, manifest, profiles, target)
        except ValidationError:
            if not force:
                raise ConflictError(
                    "target contains an invalid state manifest; use --force to preserve and replace it"
                )
            state_backup = _backup_relative(target, state_relative, stamp)
            state = _state_skeleton(root, manifest, stamp_iso)
    else:
        state = _state_skeleton(root, manifest, stamp_iso)

    old_state = copy.deepcopy(state)
    state["distribution_version"] = manifest["distribution"]["version"]
    state["manifest_version"] = manifest["manifest_version"]
    state["manifest_sha256"] = _manifest_sha256(root)
    installed_profiles = set(state.get("installed_profiles", []))
    installed_profiles.add(profile_id)
    state["installed_profiles"] = sorted(installed_profiles)
    records = {artifact["destination"]: copy.deepcopy(artifact) for artifact in state.get("artifacts", [])}
    actions: List[Dict[str, Any]] = []

    for artifact in wanted:
        destination = artifact["destination"]
        path = _contained_path(target, destination)
        record = records.get(destination)
        if path.exists():
            if not path.is_file():
                raise ConflictError("artifact target is not a regular file: %s" % destination)
            current_digest = _sha256_path(path)
            if current_digest == artifact["sha256"]:
                action_name = "unchanged"
                backup = None
            else:
                if not force:
                    raise ConflictError(
                        "refusing to overwrite %s; rerun with --force to create a timestamped backup"
                        % destination
                    )
                action_name = "replace"
                backup = _backup_relative(target, destination, stamp)
        else:
            current_digest = None
            action_name = "create"
            backup = None

        actions.append(
            {
                "action": action_name,
                "destination": destination,
                "sha256": artifact["sha256"],
                "backup": backup,
                "content": artifact["content"],
                "expected_current_sha256": current_digest,
            }
        )

        if record is None:
            if action_name == "replace":
                ownership = "replaced"
                original_backup = backup
                original_sha256 = current_digest
            elif action_name == "create":
                ownership = "created"
                original_backup = None
                original_sha256 = None
            else:
                ownership = "preexisting_identical"
                original_backup = None
                original_sha256 = None
            record = {
                "destination": destination,
                "ownership": ownership,
                "original_backup": original_backup,
                "original_sha256": original_sha256,
                "safety_backups": [],
                "profiles": [artifact["owner_profile"]],
            }
        else:
            record.setdefault("safety_backups", [])
            record.setdefault("profiles", [])
            if record.get("ownership") == "preexisting_identical" and action_name == "replace":
                record["ownership"] = "replaced"
                record["original_backup"] = backup
                record["original_sha256"] = current_digest
            elif record.get("ownership") == "preexisting_identical" and action_name == "create":
                record["ownership"] = "created"
                record["original_backup"] = None
                record["original_sha256"] = None
            elif action_name == "replace" and backup is not None:
                record["safety_backups"].append(backup)
            record["profiles"] = sorted(set(record["profiles"]) | {artifact["owner_profile"]})
        record["installed_sha256"] = artifact["sha256"]
        records[destination] = record

    state["artifacts"] = [records[key] for key in sorted(records)]
    _validate_state(state, root, manifest, profiles)
    comparable_old = copy.deepcopy(old_state)
    comparable_new = copy.deepcopy(state)
    comparable_old.pop("updated_at", None)
    comparable_new.pop("updated_at", None)
    state_changed = comparable_old != comparable_new or state_backup is not None
    if state_changed:
        state["updated_at"] = stamp_iso
    else:
        state["updated_at"] = old_state.get("updated_at", stamp_iso)

    result = {
        "command": "install",
        "profile": profile_id,
        "resolved_profiles": resolve_profile_ids(profile_id, profiles),
        "target": str(target),
        "dry_run": dry_run,
        "state_manifest": state_relative,
        "state_action": "write" if state_changed or not state_path.exists() else "unchanged",
        "state_backup": state_backup,
        "actions": [_public_action(action) for action in actions],
    }
    if dry_run:
        return result

    after_states: Dict[str, Optional[str]] = {
        action["destination"]: action["sha256"]
        for action in actions
        if action["action"] in {"create", "replace"}
    }
    if result["state_action"] == "write":
        after_states[state_relative] = _sha256_bytes(_json_bytes(state))
    generated_backups = [
        backup
        for backup in [state_backup] + [action.get("backup") for action in actions]
        if backup is not None
    ]
    if not after_states:
        return result
    wal = _begin_transaction(
        target,
        root,
        manifest,
        profiles,
        after_states,
        generated_backups,
    )
    try:
        _assert_expected_digest(target, state_relative, expected_state_sha256)
        for action in actions:
            if action["action"] in {"create", "replace"}:
                _assert_expected_digest(
                    target,
                    action["destination"],
                    action["expected_current_sha256"],
                )
        if state_backup is not None:
            backup_path = _contained_path(target, state_backup)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(state_path, backup_path)
        for action in actions:
            path = _contained_path(target, action["destination"])
            if action["action"] == "replace":
                backup_path = _contained_path(target, action["backup"])
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup_path)
                _atomic_write(path, action["content"])
            elif action["action"] == "create":
                _atomic_write(path, action["content"])
            else:
                continue
            if _failure_injector is not None:
                _failure_injector("after_artifact:%s" % action["destination"])
        for action in actions:
            if action["action"] in {"create", "replace"}:
                _assert_expected_digest(target, action["destination"], action["sha256"])
        _validate_state(state, root, manifest, profiles, target)
        if _failure_injector is not None:
            _failure_injector("before_state")
        if result["state_action"] == "write":
            _atomic_write(state_path, _json_bytes(state))
        if _failure_injector is not None:
            _failure_injector("after_state")
        _commit_transaction(target, wal)
    except Exception:
        try:
            _recover_pending_transaction(
                target,
                root,
                manifest,
                profiles,
                trusted_wal=wal,
            )
        except Exception as rollback_error:
            raise ConflictError("installation failed and transactional rollback failed") from rollback_error
        raise
    return result


def uninstall(
    manifest_path: Path,
    target: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    now: Optional[datetime] = None,
    _failure_injector: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    root, manifest, profiles = load_canonical_manifest(manifest_path)
    errors = validate_distribution(root)
    if errors:
        raise ValidationError("invalid distribution:\n- " + "\n- ".join(errors))
    target = target.resolve()
    if not target.is_dir():
        raise ValidationError("installation target must be an existing directory: %s" % target)
    if _transaction_wal_path(target).exists():
        if dry_run:
            raise ConflictError("pending transaction requires recovery before dry-run")
        _recover_pending_transaction(target, root, manifest, profiles)
    state_relative = manifest["distribution"]["state_manifest"]
    state_path = _contained_path(target, state_relative)
    if not state_path.exists():
        return {
            "command": "uninstall",
            "target": str(target),
            "dry_run": dry_run,
            "state_manifest": state_relative,
            "state_action": "absent",
            "actions": [],
        }
    if not state_path.is_file():
        raise ConflictError("state manifest target is not a regular file: %s" % state_relative)
    expected_state_sha256 = _sha256_path(state_path)
    state = load_json(state_path)
    _validate_state(state, root, manifest, profiles, target)
    stamp = _utc_stamp(now)
    actions: List[Dict[str, Any]] = []

    for record in state["artifacts"]:
        destination = record["destination"]
        path = _contained_path(target, destination)
        ownership = record["ownership"]
        if path.exists() and not path.is_file():
            raise ConflictError("artifact target is not a regular file: %s" % destination)
        current_digest = _sha256_path(path) if path.exists() else None
        installed_digest = record["installed_sha256"]
        modified = current_digest is not None and current_digest != installed_digest
        safety_backup = None

        if ownership == "preexisting_identical":
            action_name = "leave-preexisting"
        elif ownership == "created":
            if current_digest is None:
                action_name = "already-absent"
            elif modified and not force:
                raise ConflictError(
                    "refusing to remove modified managed file %s; use --force to preserve a backup"
                    % destination
                )
            else:
                action_name = "remove"
                if modified:
                    safety_backup = _backup_relative(target, destination, stamp)
        else:
            original_backup = record.get("original_backup")
            original_sha256 = record.get("original_sha256")
            if _safe_relative(original_backup) is None:
                raise ConflictError("state lacks a safe original backup for %s" % destination)
            original_path = _contained_path(target, original_backup)
            if not original_path.is_file():
                raise ConflictError("original backup is missing for %s" % destination)
            if _sha256_path(original_path) != original_sha256:
                raise ConflictError("original backup digest mismatch for %s" % destination)
            if modified and not force:
                raise ConflictError(
                    "refusing to replace modified managed file %s; use --force to preserve a backup"
                    % destination
                )
            action_name = "restore"
            if modified:
                safety_backup = _backup_relative(target, destination, stamp)

        actions.append(
            {
                "action": action_name,
                "destination": destination,
                "backup": safety_backup,
                "restore_from": record.get("original_backup") if ownership == "replaced" else None,
                "expected_current_sha256": current_digest,
            }
        )

    result = {
        "command": "uninstall",
        "target": str(target),
        "dry_run": dry_run,
        "state_manifest": state_relative,
        "state_action": "remove",
        "actions": [_public_action(action) for action in actions],
    }
    if dry_run:
        return result

    after_states: Dict[str, Optional[str]] = {}
    for action in actions:
        if action["action"] == "remove":
            after_states[action["destination"]] = None
        elif action["action"] == "restore":
            restore_path = _contained_path(target, action["restore_from"])
            after_states[action["destination"]] = _sha256_path(restore_path)
    after_states[state_relative] = None
    generated_backups = [action["backup"] for action in actions if action["backup"] is not None]
    wal = _begin_transaction(
        target,
        root,
        manifest,
        profiles,
        after_states,
        generated_backups,
    )
    try:
        _assert_expected_digest(target, state_relative, expected_state_sha256)
        for action in actions:
            if action["action"] in {"remove", "restore"}:
                _assert_expected_digest(
                    target,
                    action["destination"],
                    action["expected_current_sha256"],
                )
        for action in actions:
            path = _contained_path(target, action["destination"])
            if action["backup"] is not None and path.exists():
                backup_path = _contained_path(target, action["backup"])
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup_path)
            if action["action"] == "remove":
                path.unlink()
            elif action["action"] == "restore":
                restore_path = _contained_path(target, action["restore_from"])
                _atomic_write(path, restore_path.read_bytes())
                shutil.copymode(restore_path, path)
            else:
                continue
            if _failure_injector is not None:
                _failure_injector("after_artifact:%s" % action["destination"])
        if _failure_injector is not None:
            _failure_injector("before_state")
        state_path.unlink()
        if _failure_injector is not None:
            _failure_injector("after_state")
        _commit_transaction(target, wal)
    except Exception:
        try:
            _recover_pending_transaction(
                target,
                root,
                manifest,
                profiles,
                trusted_wal=wal,
            )
        except Exception as rollback_error:
            raise ConflictError("uninstall failed and transactional rollback failed") from rollback_error
        raise
    return result


def _default_manifest() -> Path:
    return Path(__file__).resolve().with_name("manifest.yaml")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or uninstall REACH-MAX v2 profiles")
    parser.add_argument("--manifest", type=Path, default=_default_manifest())
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="install a versioned profile")
    install_parser.add_argument("--profile", choices=sorted(REQUIRED_PROFILES), default="core")
    install_parser.add_argument("--target", type=Path, default=Path.cwd())
    install_parser.add_argument("--force", action="store_true")
    install_parser.add_argument("--dry-run", action="store_true")

    uninstall_parser = subparsers.add_parser("uninstall", help="uninstall from the state manifest")
    uninstall_parser.add_argument("--target", type=Path, default=Path.cwd())
    uninstall_parser.add_argument("--force", action="store_true")
    uninstall_parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "install":
            result = install(
                args.manifest,
                args.profile,
                args.target,
                force=args.force,
                dry_run=args.dry_run,
            )
        else:
            result = uninstall(
                args.manifest,
                args.target,
                force=args.force,
                dry_run=args.dry_run,
            )
    except ConflictError as exc:
        print(json.dumps({"ok": False, "error": "conflict", "detail": str(exc)}, ensure_ascii=False))
        return 2
    except (DistributionError, OSError) as exc:
        print(json.dumps({"ok": False, "error": "invalid", "detail": str(exc)}, ensure_ascii=False))
        return 3
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
