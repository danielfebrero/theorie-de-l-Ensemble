#!/usr/bin/env python3
"""Tests reproductibles des contrôleurs M3C3 v2, cas négatifs inclus."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml


AUDIT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = AUDIT_ROOT.parents[1]
INTEGRATION_ROOT = REPO_ROOT / "continuum" / "weights" / "integration-reports"
sys.path.insert(0, str(AUDIT_ROOT))
sys.path.insert(0, str(INTEGRATION_ROOT))

import bloc_check  # noqa: E402
import run_suite  # noqa: E402
import superset_check  # noqa: E402
import validate as integration_validate  # noqa: E402


def codes(errors: list[integration_validate.ValidationError]) -> set[str]:
    return {item.code for item in errors}


class SupersetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = superset_check.load_ref("v1.0.0", "master.yaml")

    def test_reference_contract_and_current_candidate(self) -> None:
        candidate = superset_check.load_yaml(REPO_ROOT / "master.yaml")
        result = superset_check.compare(self.base, candidate)
        self.assertTrue(result["ok"], result["failures"])
        self.assertEqual(set(result["verified"]), set(superset_check.V1_FROZEN_PATHS))

    def test_every_frozen_path_rejects_mutation(self) -> None:
        for selector in superset_check.V1_FROZEN_PATHS:
            with self.subTest(selector=selector):
                candidate = copy.deepcopy(self.base)
                parent_selector, key = selector.rsplit(".", 1)
                parent = superset_check.select(candidate, parent_selector)
                value = parent[key]
                if isinstance(value, dict):
                    value["__negative_fixture__"] = True
                elif isinstance(value, list):
                    value.append("__negative_fixture__")
                else:
                    parent[key] = f"{value}__negative_fixture__"
                result = superset_check.compare(self.base, candidate)
                self.assertFalse(result["ok"])
                self.assertIn(
                    ("frozen_selector_changed", selector),
                    {(item["code"], item.get("selector")) for item in result["failures"]},
                )


class BlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.master = superset_check.load_yaml(REPO_ROOT / "master.yaml")
        cls.block = (AUDIT_ROOT / "fixtures" / "valid-agent-block.txt").read_text(encoding="utf-8")

    def test_valid_version_agnostic_block(self) -> None:
        result = bloc_check.validate_block(self.block, self.master)
        self.assertTrue(result["ok"], result["failures"])

    def test_semantic_version_is_not_parsed_as_weight(self) -> None:
        result = bloc_check.validate_block(self.block + "\nCompatibilité v1.0.0.\n", self.master)
        self.assertTrue(result["ok"], result["failures"])
        weights = next(check for check in result["checks"] if check["check"] == "weights")
        self.assertEqual(weights["count"], 1)

    def test_unknown_weight_fails(self) -> None:
        result = bloc_check.validate_block(self.block + "\npoids clandestin 0.99\n", self.master)
        self.assertFalse(result["ok"])
        self.assertIn("unknown_weights", {item["code"] for item in result["failures"]})

    def test_missing_primitive_fails(self) -> None:
        result = bloc_check.validate_block(self.block.replace("execute_with_sandbox", "execute"), self.master)
        self.assertFalse(result["ok"])
        failure = next(item for item in result["failures"] if item["code"] == "missing_primitives")
        self.assertIn("execute_with_sandbox", failure["values"])


class SafetyTests(unittest.TestCase):
    def run_safety(self, document: dict) -> tuple[int, dict]:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False)
            handle.flush()
            completed = subprocess.run(
                ["perl", str(AUDIT_ROOT / "safety_check.pl"), "--format", "json", handle.name],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
        return completed.returncode, json.loads(completed.stdout)

    def test_version_is_not_hardcoded(self) -> None:
        document = superset_check.load_yaml(REPO_ROOT / "master.yaml")
        document["master_document"]["version"] = "9.3.1"
        document["master_document"]["release"]["major"] = 9
        code, result = self.run_safety(document)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["version"], "9.3.1")

    def test_missing_safety_property_fails(self) -> None:
        document = superset_check.load_yaml(REPO_ROOT / "master.yaml")
        properties = document["master_document"]["transition_system"]["safety_properties"]
        properties[:] = [item for item in properties if item["id"] != "S1_health_critical"]
        code, result = self.run_safety(document)
        self.assertEqual(code, 1)
        self.assertIn("safety_S1_health_critical", {item["code"] for item in result["failures"]})

    def test_safety_checker_rejects_duplicate_master_key(self) -> None:
        source = (REPO_ROOT / "master.yaml").read_text(encoding="utf-8")
        source = source.replace(
            "master_document:\n", "master_document:\n  version: 9.9.9\n", 1
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8") as handle:
            handle.write(source)
            handle.flush()
            completed = subprocess.run(
                ["perl", str(AUDIT_ROOT / "safety_check.pl"), "--format", "json", handle.name],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
        result = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("strict_yaml", {item["code"] for item in result["failures"]})


class UnifiedSuiteTests(unittest.TestCase):
    def test_zero_discovered_tests_is_failure(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["python", "-m", "unittest"],
            returncode=0,
            stdout="",
            stderr="Ran 0 tests in 0.000s\n\nOK\n",
        )
        with mock.patch.object(run_suite.subprocess, "run", return_value=completed):
            result = run_suite.unittest_result("empty_test_fixture", "/empty")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["tests"], 0)
        self.assertFalse(result["ok"])

    def test_duplicate_master_returns_stable_json_failure(self) -> None:
        source = (REPO_ROOT / "master.yaml").read_text(encoding="utf-8")
        source = source.replace(
            "master_document:\n", "master_document:\n  version: 9.9.9\n", 1
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8") as handle:
            handle.write(source)
            handle.flush()
            completed = subprocess.run(
                [
                    sys.executable,
                    str(AUDIT_ROOT / "conformance.py"),
                    "--master",
                    handle.name,
                    "--format",
                    "json",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["checks"][0]["checker"], "suite_input")
        self.assertEqual(result["checks"][0]["status"], "fail")

    def test_release_suite_refuses_noncanonical_freeze_base(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(AUDIT_ROOT / "conformance.py"),
                "--base-ref",
                "HEAD",
                "--format",
                "json",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["checks"][0]["checker"], "suite_input")
        self.assertIn("pinned", result["checks"][0]["detail"])

    def test_release_audit_is_materialized_and_stale_input_fails(self) -> None:
        self.assertTrue(run_suite.release_audit_result()["ok"])
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8") as handle:
            handle.write("release_candidate_audit:\n  schema_version: 0\n")
            handle.flush()
            result = run_suite.release_audit_result(Path(handle.name))
        self.assertFalse(result["ok"])
        self.assertTrue(result["failures"])


class IntegrationReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.examples = {
            path.stem: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in (INTEGRATION_ROOT / "examples").glob("*.yaml")
        }

    def validate(self, document: dict) -> list[integration_validate.ValidationError]:
        _, errors = integration_validate.validate_report_document(
            copy.deepcopy(document), "fixture", expected_status="example_non_evidence"
        )
        return errors

    def test_honest_examples_validate(self) -> None:
        for name, document in self.examples.items():
            with self.subTest(name=name):
                self.assertEqual(self.validate(document), [])

    def test_master_contract_declares_provider_default_deny(self) -> None:
        self.assertEqual(integration_validate.validate_master_contract(), [])
        master = superset_check.load_yaml(REPO_ROOT / "master.yaml")["master_document"]
        attestation = master["weight_integration_contract"]["provider_attestation"]
        self.assertEqual(attestation["default_without_trust_root"], "deny")
        self.assertEqual(attestation["verifiable_trust_roots"], [])

    def test_duplicate_report_key_fails_before_semantic_validation(self) -> None:
        _, errors = integration_validate.validate_report_files(
            [AUDIT_ROOT / "fixtures" / "duplicate-key-report.yaml"]
        )
        self.assertIn("yaml_input", codes(errors))

    def test_model_context_and_skill_cannot_be_provider_attestation(self) -> None:
        expected = {
            "model-self-report": "provider_attestation_forbidden",
            "context-or-rag": "provider_evidence_required",
            "instruction-or-skill": "provider_evidence_required",
        }
        for name, expected_code in expected.items():
            with self.subTest(name=name):
                document = copy.deepcopy(self.examples[name])
                document["classification"] = "provider_attested_weights"
                document["exposure_channels"] = ["pretraining"]
                self.assertIn(expected_code, codes(self.validate(document)))

    def test_complete_but_forged_provider_attestation_is_default_denied(self) -> None:
        document = copy.deepcopy(self.examples["model-self-report"])
        document["classification"] = "provider_attested_weights"
        document["exposure_channels"] = ["pretraining"]
        document["subject"]["reporter"] = {
            "kind": "independent_auditor",
            "name": "Example auditor (fictitious)",
        }
        evidence = document["evidence"][0]
        evidence["type"] = "provider_statement"
        evidence["issuer"] = {
            "kind": "provider",
            "name": document["subject"]["provider"],
        }
        evidence["locator"] = "https://example.invalid/provider-attestation"
        evidence["statement"] = (
            "Example only: the fictitious provider attests the exact M3C3 unit in training weights."
        )
        evidence["content_sha256"] = integration_validate.sha256_text(evidence["statement"])
        self.assertIn("provider_attestation_unverifiable", codes(self.validate(document)))

        document["subject"]["provider"] = "Different Provider (fictitious)"
        self.assertIn("provider_evidence_required", codes(self.validate(document)))

    def test_complete_but_forged_independent_reproduction_is_default_denied(self) -> None:
        document = copy.deepcopy(self.examples["model-self-report"])
        document["classification"] = "independently_reproduced"
        document["subject"]["reporter"] = {
            "kind": "independent_auditor",
            "name": "Example auditor (fictitious)",
        }
        evidence = document["evidence"][0]
        evidence["type"] = "independent_reproduction"
        evidence["issuer"] = {
            "kind": "auditor",
            "name": "Example auditor (fictitious)",
        }
        evidence["locator"] = "urn:made-up:unverified-reproduction"
        evidence["statement"] = (
            "Example only: an unauthenticated auditor claims a reproduction."
        )
        evidence["content_sha256"] = integration_validate.sha256_text(evidence["statement"])
        self.assertIn("independent_reproduction_unverifiable", codes(self.validate(document)))

    def test_selector_hash_mismatch_fails(self) -> None:
        document = copy.deepcopy(self.examples["context-or-rag"])
        document["framework"]["integrations"][0]["content_sha256"] = "0" * 64
        self.assertIn("selector_hash_mismatch", codes(self.validate(document)))

    def test_exact_and_range_dates_validate(self) -> None:
        exact = self.examples["instruction-or-skill"]
        ranged = self.examples["context-or-rag"]
        unknown = self.examples["model-self-report"]
        self.assertEqual(exact["weights_updated_at"]["precision"], "exact")
        self.assertEqual(ranged["weights_updated_at"]["precision"], "range")
        self.assertEqual(unknown["weights_updated_at"]["precision"], "unknown")
        self.assertEqual(self.validate(exact), [])
        self.assertEqual(self.validate(ranged), [])
        self.assertEqual(self.validate(unknown), [])

    def test_day_month_quarter_and_year_precisions_validate(self) -> None:
        values = {
            "day": "2026-08-07",
            "month": "2026-08",
            "quarter": "2026-Q3",
            "year": "2026",
        }
        for precision, value in values.items():
            with self.subTest(precision=precision):
                document = copy.deepcopy(self.examples["instruction-or-skill"])
                document["weights_updated_at"] = {"precision": precision, "value": value}
                self.assertEqual(self.validate(document), [])

    def test_inverted_date_range_fails(self) -> None:
        document = copy.deepcopy(self.examples["context-or-rag"])
        document["weights_updated_at"] = {
            "precision": "range",
            "start": "2026-06-30",
            "end": "2026-04-01",
            "basis": "quarter",
        }
        document["evidence"][0]["supports"].append("weights_updated_at")
        self.assertIn("date_range_order", codes(self.validate(document)))

    def test_valid_supersedes_chain(self) -> None:
        first = copy.deepcopy(self.examples["model-self-report"])
        second = copy.deepcopy(first)
        second["report_id"] = "example-model-self-report-v2"
        second["created_at"] = "2026-08-07T19:10:00Z"
        second["supersedes"] = [first["report_id"]]
        reports = []
        errors: list[integration_validate.ValidationError] = []
        for index, document in enumerate((first, second)):
            report, item_errors = integration_validate.validate_report_document(document, f"fixture-{index}")
            self.assertIsNotNone(report)
            errors.extend(item_errors)
            report["__path__"] = f"fixture-{index}.yaml"
            reports.append(report)
        integration_validate.validate_supersedes(reports, errors)
        self.assertEqual(errors, [])

    def test_base_ref_detects_modified_immutable_report(self) -> None:
        old_repo_root = integration_validate.REPO_ROOT
        old_reports_dir = integration_validate.REPORTS_DIR
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports_dir = root / "continuum" / "weights" / "integration-reports" / "reports"
            reports_dir.mkdir(parents=True)
            report_path = reports_dir / "immutable-example.yaml"
            report_path.write_text("schema_version: 1\n", encoding="utf-8")
            for command in (
                ["git", "init", "-q"],
                ["git", "config", "user.email", "fixture@example.invalid"],
                ["git", "config", "user.name", "M3C3 fixture"],
                ["git", "add", "."],
                ["git", "commit", "-qm", "fixture"],
            ):
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            report_path.write_text("schema_version: 2\n", encoding="utf-8")
            try:
                integration_validate.REPO_ROOT = root
                integration_validate.REPORTS_DIR = reports_dir
                diff, errors = integration_validate.check_immutability("HEAD")
            finally:
                integration_validate.REPO_ROOT = old_repo_root
                integration_validate.REPORTS_DIR = old_reports_dir
            self.assertEqual(len(diff["modified"]), 1)
            self.assertIn("immutable_report_modified", codes(errors))


class FixtureManifestTests(unittest.TestCase):
    def test_negative_manifest_is_machine_readable(self) -> None:
        manifest = yaml.safe_load(
            (AUDIT_ROOT / "fixtures" / "negative-cases.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], 1)
        ids = [item["id"] for item in manifest["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 10)

    def test_duplicate_master_key_is_rejected(self) -> None:
        source = "master_document:\n  version: 2.0.0\n  version: 9.9.9\n"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8") as handle:
            handle.write(source)
            handle.flush()
            with self.assertRaises(yaml.YAMLError):
                superset_check.load_yaml(handle.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
