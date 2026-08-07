#!/usr/bin/env python3
"""Construit ou vérifie l'index déterministe des rapports réels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml

import validate


INDEX_PATH = validate.INTEGRATION_ROOT / "index.yaml"


def expected_index() -> tuple[dict[str, Any], list[validate.ValidationError]]:
    paths = list(validate.REPORTS_DIR.glob("*.y*ml"))
    reports, errors = validate.validate_report_files(paths, "evidence_record")
    errors.extend(validate.validate_master_contract())
    validate.validate_supersedes(reports, errors)
    entries: list[dict[str, Any]] = []
    for report in sorted(reports, key=lambda item: str(item.get("report_id", ""))):
        path = Path(report["__path__"])
        subject = report.get("subject") or {}
        entries.append(
            {
                "report_id": report.get("report_id"),
                "path": path.relative_to(validate.INTEGRATION_ROOT).as_posix(),
                "file_sha256": validate.file_sha256(path),
                "created_at": report.get("created_at"),
                "provider": subject.get("provider"),
                "model": subject.get("model"),
                "model_version": subject.get("model_version"),
                "classification": report.get("classification"),
                "supersedes": report.get("supersedes") or [],
            }
        )
    return {
        "schema_version": 1,
        "kind": "integration_report_index",
        "reports_sha256": validate.sha256_text(validate.canonical_json(entries)),
        "reports": entries,
    }, errors


def dump_index(index: dict[str, Any]) -> str:
    return yaml.safe_dump(index, allow_unicode=True, sort_keys=False, width=1000)


def check_index(expected: dict[str, Any], path: Path = INDEX_PATH) -> tuple[bool, str]:
    try:
        actual = validate.load_path(path)
    except (OSError, yaml.YAMLError) as exc:
        return False, str(exc)
    if actual != expected:
        return False, "index.yaml is stale; run build_index.py --write"
    return True, "index.yaml matches all immutable report files"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    expected, validation_errors = expected_index()
    if validation_errors:
        result = {
            "checker": "integration_report_index",
            "ok": False,
            "reports": len(expected["reports"]),
            "detail": "report validation failed",
            "errors": [item.as_dict() for item in validation_errors],
        }
    elif args.write:
        INDEX_PATH.write_text(dump_index(expected), encoding="utf-8")
        result = {
            "checker": "integration_report_index",
            "ok": True,
            "reports": len(expected["reports"]),
            "detail": f"wrote {INDEX_PATH}",
            "errors": [],
        }
    elif args.check:
        ok, detail = check_index(expected)
        result = {
            "checker": "integration_report_index",
            "ok": ok,
            "reports": len(expected["reports"]),
            "detail": detail,
            "errors": [] if ok else [{"code": "stale_index", "path": str(INDEX_PATH), "detail": detail}],
        }
    else:
        print(dump_index(expected), end="")
        return 0

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        prefix = "OK" if result["ok"] else "FAIL"
        print(f"INDEX {prefix} — {result['detail']} ({result['reports']} rapport(s))")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
