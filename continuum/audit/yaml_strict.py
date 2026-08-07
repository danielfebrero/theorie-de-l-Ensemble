#!/usr/bin/env python3
"""Chargement YAML sûr avec refus des clés dupliquées."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys
from typing import Any

import yaml


class UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader qui refuse un second exemplaire d'une même clé de mapping."""


def construct_unique_mapping(
    loader: UniqueKeySafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    if not isinstance(node, yaml.nodes.MappingNode):
        raise yaml.constructor.ConstructorError(
            None, None, f"expected a mapping node, got {node.id}", node.start_mark
        )
    seen: dict[Any, yaml.error.Mark] = {}
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=False)
        try:
            duplicate = key in seen
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"unhashable mapping key: {exc}",
                key_node.start_mark,
            ) from exc
        if duplicate:
            first = seen[key]
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}; first declared at line {first.line + 1}",
                key_node.start_mark,
            )
        seen[key] = key_node.start_mark
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping
)


def loads(text: str) -> Any:
    return yaml.load(text, Loader=UniqueKeySafeLoader)


def load_path(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return yaml.load(handle, Loader=UniqueKeySafeLoader)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv or sys.argv[1:])
    failures: list[dict[str, str]] = []
    for raw_path in args.paths:
        try:
            load_path(raw_path)
        except (OSError, yaml.YAMLError) as exc:
            failures.append({"path": raw_path, "code": "strict_yaml", "detail": str(exc)})
    result = {"checker": "strict_yaml", "ok": not failures, "failures": failures}
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif failures:
        for failure in failures:
            print(f"YAML FAIL [{failure['path']}] — {failure['detail']}")
    else:
        print(f"YAML OK — {len(args.paths)} file(s), no duplicate keys")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
