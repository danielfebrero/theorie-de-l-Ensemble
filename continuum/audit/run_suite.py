#!/usr/bin/env python3
"""Suite de conformité M3C3 unifiée avec sortie JSON stable."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import yaml


AUDIT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = AUDIT_ROOT.parents[1]
INTEGRATION_ROOT = REPO_ROOT / "continuum" / "weights" / "integration-reports"
RELEASE_AUDIT_PATH = AUDIT_ROOT / "v2.0-2026-08-07" / "results.yaml"
sys.path.insert(0, str(AUDIT_ROOT))
sys.path.insert(0, str(INTEGRATION_ROOT))

import bloc_check  # noqa: E402
import build_index  # noqa: E402
import superset_check  # noqa: E402
import validate as integration_validate  # noqa: E402


def agent_block_from_markdown(path: Path) -> str:
    markdown = path.read_text(encoding="utf-8")
    blocks = re.findall(r"```text\s*\n(.*?)\n```", markdown, re.DOTALL | re.IGNORECASE)
    candidates = [block for block in blocks if "MODE M3C3" in block and "AUTHORSHIP" in block]
    if not candidates:
        raise ValueError(f"agent block not found in {path}")
    return max(candidates, key=len)


def safety_result(master_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["perl", str(AUDIT_ROOT / "safety_check.pl"), "--format", "json", str(master_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = {
            "checker": "safety_kernel",
            "ok": False,
            "failures": [
                {
                    "code": "invalid_checker_output",
                    "detail": (completed.stderr or completed.stdout).strip(),
                }
            ],
        }
    result["exit_code"] = completed.returncode
    if completed.returncode != 0:
        result["ok"] = False
    return result


def capsule_result() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "capsules" / "validate.py"), "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"status": "fail", "errors": [(completed.stderr or completed.stdout).strip()]}
    return {
        "checker": "capsule_runtime_bindings",
        "ok": completed.returncode == 0 and payload.get("status") == "pass",
        "exit_code": completed.returncode,
        **payload,
    }


def json_command_result(checker: str, command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command, cwd=REPO_ROOT, text=True, capture_output=True
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "errors": [(completed.stderr or completed.stdout).strip() or "invalid JSON output"]
        }
    payload_ok = payload.get("ok") is True or payload.get("status") == "pass"
    return {
        "checker": checker,
        "ok": completed.returncode == 0 and payload_ok,
        "exit_code": completed.returncode,
        "command": command,
        "result": payload,
    }


def unittest_result(checker: str, test_directory: str) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        test_directory,
        "-v",
    ]
    completed = subprocess.run(
        command, cwd=REPO_ROOT, text=True, capture_output=True
    )
    transcript = (completed.stdout + completed.stderr).strip()
    match = re.search(r"Ran\s+(\d+)\s+tests?", transcript)
    test_count = int(match.group(1)) if match else None
    return {
        "checker": checker,
        "ok": completed.returncode == 0 and test_count is not None and test_count > 0,
        "exit_code": completed.returncode,
        "command": command,
        "tests": test_count,
        "transcript": transcript,
    }


def index_result() -> dict[str, Any]:
    expected, errors = build_index.expected_index()
    if errors:
        return {
            "checker": "integration_report_index",
            "ok": False,
            "reports": len(expected["reports"]),
            "errors": [item.as_dict() for item in errors],
        }
    ok, detail = build_index.check_index(expected)
    return {
        "checker": "integration_report_index",
        "ok": ok,
        "reports": len(expected["reports"]),
        "detail": detail,
        "errors": [] if ok else [{"code": "stale_index", "detail": detail}],
    }


def release_audit_result(path: Path = RELEASE_AUDIT_PATH) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    try:
        document = superset_check.load_yaml(path)
        audit = document["release_candidate_audit"]
        master = superset_check.load_yaml(REPO_ROOT / "master.yaml")["master_document"]
    except (KeyError, OSError, TypeError, yaml.YAMLError) as exc:
        return {
            "checker": "release_candidate_audit",
            "ok": False,
            "path": str(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path),
            "failures": [{"code": "release_audit_input", "detail": str(exc)}],
        }

    def require(condition: bool, code: str, detail: str) -> None:
        if not condition:
            failures.append({"code": code, "detail": detail})

    baseline = master.get("continuum_memory", {}).get("pattern_index", {}).get(
        "history_base_commit"
    )
    actual_master_sha = hashlib.sha256((REPO_ROOT / "master.yaml").read_bytes()).hexdigest()
    require(audit.get("schema_version") == 1, "release_audit_schema", "schema_version must be 1")
    require(audit.get("framework_version") == "2.0.0", "release_audit_version", "framework_version must be 2.0.0")
    require(audit.get("status") == "release_candidate", "release_audit_status", "status must remain release_candidate")
    require(audit.get("canonical_activation") is False, "release_audit_activation", "candidate must not claim canonical activation")
    require(
        audit.get("implementation_baseline_commit") == baseline,
        "release_audit_baseline",
        "implementation baseline must match the canonical memory history base",
    )
    require(
        audit.get("candidate", {}).get("master_sha256") == actual_master_sha,
        "release_audit_master_hash",
        "audit master SHA-256 is stale",
    )
    required = audit.get("local_gates", {}).get("required", {})
    require(
        required == {"pass": 15, "fail": 0, "not_run": 0},
        "release_audit_required_gates",
        "expected 15 required pass and no fail/not_run",
    )
    require(
        audit.get("local_gates", {}).get("informational", {}).get("external_model_check")
        == "not_run",
        "release_audit_external_model_check",
        "external model check must remain explicitly not_run",
    )
    test_suites = audit.get("test_suites")
    expected_suites = {"runtime", "distribution", "conformance", "continuum_memory", "capsules"}
    require(
        isinstance(test_suites, dict) and set(test_suites) == expected_suites,
        "release_audit_test_suites",
        "test suite inventory is incomplete",
    )
    if isinstance(test_suites, dict):
        for name in sorted(expected_suites):
            item = test_suites.get(name, {})
            require(
                isinstance(item, dict)
                and item.get("status") == "pass"
                and isinstance(item.get("tests"), int)
                and item["tests"] > 0,
                "release_audit_test_result",
                f"{name} must record a positive passing test count",
            )
    require(
        isinstance(audit.get("limitations"), list) and bool(audit["limitations"]),
        "release_audit_limitations",
        "at least one explicit limitation is required",
    )
    return {
        "checker": "release_candidate_audit",
        "ok": not failures,
        "path": str(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path),
        "baseline": baseline,
        "failures": failures,
    }


def negative_test_result() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(AUDIT_ROOT / "test_conformance.py")],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    transcript = (completed.stdout + completed.stderr).strip()
    match = re.search(r"Ran\s+(\d+)\s+tests?", transcript)
    test_count = int(match.group(1)) if match else None
    return {
        "checker": "negative_and_regression_tests",
        "ok": completed.returncode == 0 and test_count is not None and test_count > 0,
        "exit_code": completed.returncode,
        "tests": test_count,
        "transcript": transcript,
    }


def normalize_gate(result: dict[str, Any], required: bool = True) -> dict[str, Any]:
    normalized = dict(result)
    status = normalized.get("status")
    if status not in {"pass", "fail", "not_run"}:
        status = "pass" if normalized.get("ok") is True else "fail"
    # Un exit code en échec ne peut jamais rester marqué pass par le payload.
    if normalized.get("exit_code") not in {None, 0}:
        status = "fail"
    normalized["status"] = status
    normalized["required"] = required
    normalized["ok"] = True if status == "pass" else (None if status == "not_run" else False)
    return normalized


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=Path("master.yaml"))
    parser.add_argument(
        "--base-ref",
        default=superset_check.CANONICAL_V1_REF,
        help="release gate base; must remain the canonical v1.0.0 tag",
    )
    parser.add_argument("--skip-negative", action="store_true")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.base_ref != superset_check.CANONICAL_V1_REF:
        raise ValueError(
            "release conformance is pinned to "
            f"{superset_check.CANONICAL_V1_REF} at {superset_check.CANONICAL_V1_SHA}; "
            "use superset_check.py directly for diagnostic comparisons"
        )
    master_path = args.master if args.master.is_absolute() else REPO_ROOT / args.master
    master = bloc_check.load_yaml(master_path)

    superset_args = superset_check.parse_args(
        ["--ref", args.base_ref, "--candidate", str(master_path)]
    )
    checks: list[dict[str, Any]] = [
        superset_check.run(superset_args),
        safety_result(master_path),
        capsule_result(),
        unittest_result("capsule_tests", "capsules/tests"),
        unittest_result("runtime_tests", "runtime/tests"),
        json_command_result(
            "distribution_profiles",
            [sys.executable, str(REPO_ROOT / "distribution" / "validate.py"), "--json"],
        ),
        unittest_result("distribution_tests", "distribution/tests"),
        json_command_result(
            "continuum_memory",
            [
                sys.executable,
                str(REPO_ROOT / "continuum" / "memory" / "validate.py"),
                "--json",
            ],
        ),
        unittest_result("continuum_memory_tests", "continuum/memory/tests"),
    ]

    try:
        block = agent_block_from_markdown(REPO_ROOT / "docs" / "mode-de-pensee.md")
        checks.append(
            bloc_check.validate_block(
                block, master, "docs/mode-de-pensee.md#agent-block"
            )
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        checks.append(
            {
                "checker": "agent_block",
                "ok": False,
                "failures": [{"code": "block_extraction", "detail": str(exc)}],
            }
        )

    fixture = (AUDIT_ROOT / "fixtures" / "valid-agent-block.txt").read_text(encoding="utf-8")
    fixture_result = bloc_check.validate_block(
        fixture, master, "continuum/audit/fixtures/valid-agent-block.txt"
    )
    fixture_result["checker"] = "agent_block_fixture"
    checks.append(fixture_result)

    checks.append(
        integration_validate.validate_registry(
            include_examples=True, base_ref=args.base_ref
        )
    )
    checks.append(index_result())
    checks.append(release_audit_result())
    if not args.skip_negative:
        checks.append(negative_test_result())
    else:
        checks.append(
            {
                "checker": "negative_and_regression_tests",
                "status": "not_run",
                "reason": "explicitly skipped by --skip-negative",
            }
        )

    required_checks = [normalize_gate(check, required=True) for check in checks]
    required_checks.append(
        normalize_gate(
            {
                "checker": "external_model_check",
                "status": "not_run",
                "reason": "aucun artefact SPIN/TLA et aucun model-checker externe déclaré dans ce dépôt",
            },
            required=False,
        )
    )
    required_ok = all(
        check["status"] == "pass" for check in required_checks if check["required"]
    )

    return {
        "schema_version": 1,
        "suite": "m3c3_conformance",
        "status": "pass" if required_ok else "fail",
        "ok": required_ok,
        "base_ref": args.base_ref,
        "master": str(master_path),
        "checks": required_checks,
    }


def render_text(result: dict[str, Any]) -> str:
    lines = [f"M3C3 CONFORMANCE — {'OK' if result['ok'] else 'FAIL'}"]
    for check in result["checks"]:
        requirement = "required" if check.get("required") else "informational"
        lines.append(
            f"  {str(check.get('status', 'fail')).upper():7}  "
            f"{check.get('checker', 'unknown')} ({requirement})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = run(args)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        result = {
            "schema_version": 1,
            "suite": "m3c3_conformance",
            "status": "fail",
            "ok": False,
            "checks": [
                normalize_gate(
                    {"checker": "suite_input", "ok": False, "detail": str(exc)},
                    required=True,
                )
            ],
        }
    print(
        json.dumps(result, ensure_ascii=False, sort_keys=True)
        if args.format == "json"
        else render_text(result)
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
