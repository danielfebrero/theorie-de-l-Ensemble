#!/usr/bin/env python3
"""Validate v2 capsule maturity and observable runtime bindings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STATUS_DOMAIN = {"specified", "implemented", "tested"}


class CapsuleValidationError(ValueError):
    """Raised for an ambiguous YAML document."""


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> Any:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise CapsuleValidationError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return yaml.load(stream, Loader=UniqueKeyLoader)


def _binding_reference(root: Path, raw: Any) -> tuple[Path, str | None] | None:
    if not isinstance(raw, str) or not raw:
        return None
    parts = raw.split("::", 1)
    relative = parts[0]
    selector = parts[1] if len(parts) == 2 else None
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate, selector


def validate_capsule_document(document: Any, source: str, root: Path) -> list[str]:
    errors: list[str] = []
    capsule = document.get("cdxx_capsule") if isinstance(document, dict) else None
    if not isinstance(capsule, dict):
        return [f"{source}: cdxx_capsule missing"]
    name = capsule.get("name", source)
    if capsule.get("activation") != "scope_controlled":
        errors.append(f"{name}: activation must be scope_controlled")
    status = capsule.get("status")
    if status not in STATUS_DOMAIN:
        errors.append(f"{name}: status must be specified, implemented or tested")
    binding = capsule.get("runtime_binding")
    if not isinstance(binding, dict):
        errors.append(f"{name}: runtime_binding missing")
        return errors
    if binding.get("version") != "2.0.0":
        errors.append(f"{name}: runtime binding version must be 2.0.0")
    for field in ("implementation", "verification"):
        reference = _binding_reference(root, binding.get(field))
        if reference is None or not reference[0].is_file():
            errors.append(f"{name}: invalid {field} binding")
            continue
        path, selector = reference
        if selector:
            source_text = path.read_text(encoding="utf-8")
            symbol = selector.rsplit(".", 1)[-1]
            if not re.search(rf"\b(?:class|def)\s+{re.escape(symbol)}\b", source_text):
                errors.append(f"{name}: {field} symbol {selector} not found")
    if not binding.get("coverage"):
        errors.append(f"{name}: runtime coverage must be explicit")
    limitations = binding.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        errors.append(f"{name}: limitations must be non-empty")
    return errors


def validate_capsules(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    root = root.resolve()
    master = _load(root / "master.yaml")["master_document"]
    expected = set(master.get("active_capsules", []))
    observed: set[str] = set()
    errors: list[str] = []
    for path in sorted((root / "capsules").glob("*.yaml")):
        try:
            document = _load(path)
        except (OSError, yaml.YAMLError, CapsuleValidationError) as error:
            errors.append(f"{path.name}: {error}")
            continue
        capsule = document.get("cdxx_capsule", {}) if isinstance(document, dict) else {}
        if isinstance(capsule.get("name"), str):
            observed.add(capsule["name"])
        errors.extend(validate_capsule_document(document, path.name, root))
    if observed != expected:
        errors.append(
            f"active capsule set drift: missing={sorted(expected-observed)}, extra={sorted(observed-expected)}"
        )
    return {
        "status": "fail" if errors else "pass",
        "capsules_checked": len(observed),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        result = validate_capsules(args.root)
    except (KeyError, TypeError, OSError, yaml.YAMLError, CapsuleValidationError) as error:
        result = {"status": "fail", "capsules_checked": 0, "errors": [str(error)]}
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif result["status"] == "pass":
        print(f"PASS capsules: {result['capsules_checked']} bindings")
    else:
        print("FAIL capsules: " + "; ".join(result["errors"]))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
