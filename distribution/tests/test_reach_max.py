from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


DISTRIBUTION_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = DISTRIBUTION_ROOT.parent
MANIFEST = DISTRIBUTION_ROOT / "manifest.yaml"
sys.path.insert(0, str(DISTRIBUTION_ROOT))

from reach_max import (  # noqa: E402
    ConflictError,
    ValidationError,
    install,
    load_manifest,
    resolved_artifacts,
    uninstall,
    validate_distribution,
)


FIXED_NOW = datetime(2026, 8, 7, 18, 30, 45, 123456, tzinfo=timezone.utc)


class DistributionValidationTests(unittest.TestCase):
    def test_distribution_and_all_profile_are_valid(self) -> None:
        self.assertEqual(validate_distribution(DISTRIBUTION_ROOT), [])
        root, manifest, profiles = load_manifest(MANIFEST)
        artifacts = resolved_artifacts(root, manifest, profiles, "all")
        self.assertEqual(
            {artifact["destination"] for artifact in artifacts},
            {
                ".m3c3/M3C3.md",
                "AGENTS.md",
                "CLAUDE.md",
                ".github/copilot-instructions.md",
                ".cursor/rules/m3c3.mdc",
                ".m3c3/mcp/INSTRUCTIONS.md",
                ".m3c3/ci/INSTRUCTIONS.md",
            },
        )
        cursor = next(
            artifact for artifact in artifacts if artifact["destination"] == ".cursor/rules/m3c3.mdc"
        )
        self.assertTrue(cursor["content"].startswith(b"---\n"))

    def _copy_distribution(self, temporary: str) -> Path:
        copied = Path(temporary) / "distribution"
        shutil.copytree(
            DISTRIBUTION_ROOT,
            copied,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        return copied

    def test_rejects_aggregate_that_omits_a_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = self._copy_distribution(temporary)
            path = copied / "profiles" / "all.json"
            profile = json.loads(path.read_text(encoding="utf-8"))
            profile["includes"].remove("ci")
            path.write_text(json.dumps(profile), encoding="utf-8")
            errors = validate_distribution(copied)
            self.assertTrue(any("all profile must include" in error for error in errors))

    def test_rejects_permission_or_global_activation_uplift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = self._copy_distribution(temporary)
            path = copied / "profiles" / "openai.json"
            profile = json.loads(path.read_text(encoding="utf-8"))
            profile["policy"]["permissions_propagate"] = True
            profile["policy"]["global_activation_guaranteed"] = True
            path.write_text(json.dumps(profile), encoding="utf-8")
            errors = validate_distribution(copied)
            self.assertTrue(any("unsafe or incomplete policy" in error for error in errors))

    def test_rejects_each_hard_policy_claim_drift(self) -> None:
        invalid_values = {
            "canonical_authority": "adapter.md",
            "activation": "global_default",
            "global_activation_guaranteed": True,
            "scope_propagates": False,
            "permissions_propagate": True,
            "modifies_personal_skill": True,
            "modifies_model_weights": True,
        }
        for key, value in invalid_values.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                copied = self._copy_distribution(temporary)
                path = copied / "profiles" / "core.json"
                profile = json.loads(path.read_text(encoding="utf-8"))
                profile["policy"][key] = value
                path.write_text(json.dumps(profile), encoding="utf-8")
                errors = validate_distribution(copied)
                self.assertTrue(any("unsafe or incomplete policy" in error for error in errors))

    def test_rejects_empty_capabilities_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = self._copy_distribution(temporary)
            path = copied / "profiles" / "mcp.json"
            profile = json.loads(path.read_text(encoding="utf-8"))
            profile["capabilities"] = []
            profile["limits"] = []
            path.write_text(json.dumps(profile), encoding="utf-8")
            errors = validate_distribution(copied)
            self.assertTrue(any("explicit capabilities" in error for error in errors))
            self.assertTrue(any("explicit limits" in error for error in errors))

    def test_rejects_missing_template_policy_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = self._copy_distribution(temporary)
            path = copied / "templates" / "core.md"
            text = path.read_text(encoding="utf-8").replace(
                "GLOBAL_ACTIVATION: not_guaranteed", "GLOBAL_ACTIVATION: guaranteed"
            )
            path.write_text(text, encoding="utf-8")
            errors = validate_distribution(copied)
            self.assertTrue(any("core template lacks required marker" in error for error in errors))

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = self._copy_distribution(temporary)
            path = copied / "profiles" / "core.json"
            profile = json.loads(path.read_text(encoding="utf-8"))
            profile["artifacts"][0]["destination"] = "../AGENTS.md"
            path.write_text(json.dumps(profile), encoding="utf-8")
            errors = validate_distribution(copied)
            self.assertTrue(any("unsafe artifact destination" in error for error in errors))

    def test_repository_check_rejects_master_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = self._copy_distribution(temporary)
            repository = Path(temporary)
            (repository / "master.yaml").write_text(
                "master_document:\n  version: 1.9.9\n", encoding="utf-8"
            )
            errors = validate_distribution(copied, repository)
            self.assertTrue(any("master_document.version" in error for error in errors))

    def test_repository_check_requires_canonical_reach_max_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = self._copy_distribution(temporary)
            repository = Path(temporary)
            (repository / "master.yaml").write_text(
                "master_document:\n  version: 2.0.0\n", encoding="utf-8"
            )
            errors = validate_distribution(copied, repository)
            self.assertTrue(any("canonical master lacks contract field" in error for error in errors))

    def test_repository_check_rejects_duplicate_master_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = self._copy_distribution(temporary)
            repository = Path(temporary)
            (repository / "master.yaml").write_text(
                "master_document:\n  version: 2.0.0\n  version: 2.0.0\n",
                encoding="utf-8",
            )
            errors = validate_distribution(copied, repository)
            self.assertTrue(any("duplicate key" in error for error in errors))

    def test_master_comments_cannot_satisfy_the_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = self._copy_distribution(temporary)
            repository = Path(temporary)
            (repository / "master.yaml").write_text(
                """master_document:
  version: 2.0.0
  activation_membrane:
    mode: global_default
# mode: scoped_adaptive
# permissions: never
# authority: never
# manifest: distribution/manifest.yaml
# profiles: [core, openai, claude, copilot, cursor, mcp, ci, all]
# path: distribution/install.py
""",
                encoding="utf-8",
            )
            errors = validate_distribution(copied, repository)
            self.assertTrue(any("activation_membrane.mode" in error for error in errors))
            self.assertTrue(any("reach_max_distribution.manifest" in error for error in errors))


class InstallerTests(unittest.TestCase):
    def test_install_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            first = install(MANIFEST, "core", target, now=FIXED_NOW)
            installed = target / ".m3c3" / "M3C3.md"
            first_content = installed.read_bytes()
            second = install(MANIFEST, "core", target, now=FIXED_NOW)
            self.assertEqual(first["actions"][0]["action"], "create")
            self.assertEqual(second["actions"][0]["action"], "unchanged")
            self.assertEqual(second["state_action"], "unchanged")
            self.assertEqual(installed.read_bytes(), first_content)

    def test_refuses_overwrite_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            existing = target / "AGENTS.md"
            existing.write_text("user content\n", encoding="utf-8")
            with self.assertRaises(ConflictError):
                install(MANIFEST, "openai", target, now=FIXED_NOW)
            self.assertEqual(existing.read_text(encoding="utf-8"), "user content\n")
            self.assertFalse((target / ".m3c3").exists())

    def test_refuses_non_regular_artifact_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "AGENTS.md").mkdir()
            with self.assertRaises(ConflictError):
                install(MANIFEST, "openai", target, force=True, now=FIXED_NOW)
            self.assertFalse((target / ".m3c3").exists())

    def test_force_creates_timestamped_backup_and_state_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            existing = target / "AGENTS.md"
            existing.write_text("user content\n", encoding="utf-8")
            result = install(MANIFEST, "openai", target, force=True, now=FIXED_NOW)
            action = next(item for item in result["actions"] if item["destination"] == "AGENTS.md")
            self.assertEqual(action["action"], "replace")
            self.assertIn("20260807T183045.123456Z", action["backup"])
            self.assertEqual((target / action["backup"]).read_text(encoding="utf-8"), "user content\n")
            state = json.loads((target / ".m3c3" / "reach-max-install.json").read_text(encoding="utf-8"))
            record = next(item for item in state["artifacts"] if item["destination"] == "AGENTS.md")
            self.assertEqual(record["ownership"], "replaced")
            self.assertEqual(record["original_backup"], action["backup"])

    def test_force_preserves_invalid_preexisting_state_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            state = target / ".m3c3" / "reach-max-install.json"
            state.parent.mkdir()
            state.write_text("not valid JSON\n", encoding="utf-8")
            with self.assertRaises(ConflictError):
                install(MANIFEST, "core", target, now=FIXED_NOW)
            result = install(MANIFEST, "core", target, force=True, now=FIXED_NOW)
            self.assertIsNotNone(result["state_backup"])
            self.assertEqual(
                (target / result["state_backup"]).read_text(encoding="utf-8"),
                "not valid JSON\n",
            )
            installed_state = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(installed_state["distribution"], "REACH-MAX")

    def _write_forged_state(self, target: Path, version: str) -> Path:
        important = target / "important.txt"
        important.write_text("must survive\n", encoding="utf-8")
        state_path = target / ".m3c3" / "reach-max-install.json"
        state_path.parent.mkdir()
        forged = {
            "schema_version": "1.0",
            "distribution": "REACH-MAX",
            "distribution_version": version,
            "manifest_version": "2.0.0",
            "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
            "installed_profiles": ["core"],
            "created_at": "2026-08-07T18:30:45Z",
            "updated_at": "2026-08-07T18:30:45Z",
            "artifacts": [
                {
                    "destination": "important.txt",
                    "ownership": "created",
                    "installed_sha256": hashlib.sha256(important.read_bytes()).hexdigest(),
                    "original_backup": None,
                    "original_sha256": None,
                    "safety_backups": [],
                    "profiles": ["core"],
                }
            ],
        }
        state_path.write_text(json.dumps(forged), encoding="utf-8")
        return state_path

    def test_forged_state_with_arbitrary_version_cannot_delete_arbitrary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            state_path = self._write_forged_state(target, "999.0.0")
            with self.assertRaises(ValidationError):
                uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertEqual((target / "important.txt").read_text(encoding="utf-8"), "must survive\n")
            self.assertTrue(state_path.exists())

    def test_exact_version_forged_destination_is_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            state_path = self._write_forged_state(target, "2.0.0")
            with self.assertRaises(ValidationError):
                uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertEqual((target / "important.txt").read_text(encoding="utf-8"), "must survive\n")
            self.assertTrue(state_path.exists())

    def test_state_binding_rejects_digest_profile_and_backup_tampering(self) -> None:
        cases = ("manifest_digest", "artifact_digest", "artifact_owner", "profile_set", "backup")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary)
                install(MANIFEST, "core", target, now=FIXED_NOW)
                artifact_path = target / ".m3c3" / "M3C3.md"
                state_path = target / ".m3c3" / "reach-max-install.json"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if case == "manifest_digest":
                    state["manifest_sha256"] = "0" * 64
                elif case == "artifact_digest":
                    state["artifacts"][0]["installed_sha256"] = "0" * 64
                elif case == "artifact_owner":
                    state["artifacts"][0]["profiles"] = ["openai"]
                elif case == "profile_set":
                    state["installed_profiles"] = ["openai"]
                else:
                    state["artifacts"][0]["ownership"] = "replaced"
                    state["artifacts"][0]["original_backup"] = "../important.txt"
                    state["artifacts"][0]["original_sha256"] = "0" * 64
                state_path.write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises(ValidationError):
                    uninstall(MANIFEST, target, now=FIXED_NOW)
                self.assertTrue(artifact_path.is_file())

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            result = install(MANIFEST, "all", target, dry_run=True, now=FIXED_NOW)
            self.assertEqual(len(result["actions"]), 7)
            self.assertEqual(list(target.iterdir()), [])

    def test_all_profile_installs_and_uninstalls_every_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            installed = install(MANIFEST, "all", target, now=FIXED_NOW)
            destinations = [item["destination"] for item in installed["actions"]]
            self.assertEqual(len(destinations), 7)
            self.assertTrue(all((target / destination).is_file() for destination in destinations))
            uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertTrue(all(not (target / destination).exists() for destination in destinations))

    def test_install_failure_rolls_back_all_artifacts_and_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            existing = target / "AGENTS.md"
            existing.write_text("original instructions\n", encoding="utf-8")

            def fail_before_state(phase: str) -> None:
                if phase == "before_state":
                    raise RuntimeError("injected write failure")

            with self.assertRaisesRegex(RuntimeError, "injected write failure"):
                install(
                    MANIFEST,
                    "all",
                    target,
                    force=True,
                    now=FIXED_NOW,
                    _failure_injector=fail_before_state,
                )
            self.assertEqual(existing.read_text(encoding="utf-8"), "original instructions\n")
            self.assertFalse((target / "CLAUDE.md").exists())
            self.assertFalse((target / ".m3c3" / "M3C3.md").exists())
            self.assertFalse((target / ".m3c3" / "reach-max-install.json").exists())
            self.assertFalse((target / ".m3c3" / "reach-max-transaction.json").exists())
            self.assertEqual(list(target.glob("AGENTS.md.m3c3-backup-*")), [])

    def test_crash_wal_requires_manual_reconciliation_without_mutating_again(self) -> None:
        class SimulatedCrash(BaseException):
            pass

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)

            def crash_after_first_artifact(phase: str) -> None:
                if phase.startswith("after_artifact:"):
                    raise SimulatedCrash()

            with self.assertRaises(SimulatedCrash):
                install(
                    MANIFEST,
                    "all",
                    target,
                    now=FIXED_NOW,
                    _failure_injector=crash_after_first_artifact,
                )
            wal_path = target / ".m3c3" / "reach-max-transaction.json"
            self.assertTrue(wal_path.is_file())
            before_retry = {
                path.relative_to(target).as_posix(): path.read_bytes()
                for path in target.rglob("*")
                if path.is_file()
            }
            with self.assertRaisesRegex(ConflictError, "automatic recovery is refused"):
                install(MANIFEST, "core", target, now=FIXED_NOW)
            after_retry = {
                path.relative_to(target).as_posix(): path.read_bytes()
                for path in target.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_retry, before_retry)
            self.assertTrue(wal_path.is_file())

    def test_forged_wal_cannot_target_arbitrary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            important = target / "important.txt"
            important.write_text("must survive\n", encoding="utf-8")
            wal_path = target / ".m3c3" / "reach-max-transaction.json"
            wal_path.parent.mkdir()
            forged = {
                "schema_version": "1.0",
                "distribution": "REACH-MAX",
                "distribution_version": "2.0.0",
                "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                "transaction_id": "a" * 32,
                "status": "prepared",
                "changes": [
                    {
                        "destination": "important.txt",
                        "before_exists": False,
                        "before_sha256": None,
                        "snapshot": None,
                        "after_exists": True,
                        "after_sha256": hashlib.sha256(important.read_bytes()).hexdigest(),
                    }
                ],
                "generated_backups": [],
            }
            wal_path.write_text(json.dumps(forged), encoding="utf-8")
            with self.assertRaises(ConflictError):
                install(MANIFEST, "core", target, now=FIXED_NOW)
            self.assertEqual(important.read_text(encoding="utf-8"), "must survive\n")

    def test_forged_wal_cannot_delete_existing_canonical_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            agents = target / "AGENTS.md"
            agents.write_text("must survive\n", encoding="utf-8")
            transaction_id = "b" * 32
            transaction_dir = (
                target / ".m3c3" / "reach-max-transactions" / transaction_id
            )
            transaction_dir.mkdir(parents=True)
            wal_path = target / ".m3c3" / "reach-max-transaction.json"
            forged = {
                "schema_version": "1.0",
                "distribution": "REACH-MAX",
                "distribution_version": "2.0.0",
                "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                "transaction_id": transaction_id,
                "status": "prepared",
                "changes": [
                    {
                        "destination": "AGENTS.md",
                        "before_exists": False,
                        "before_sha256": None,
                        "snapshot": None,
                        "after_exists": True,
                        "after_sha256": hashlib.sha256(agents.read_bytes()).hexdigest(),
                    }
                ],
                "generated_backups": [],
            }
            wal_path.write_text(json.dumps(forged), encoding="utf-8")
            with self.assertRaisesRegex(ConflictError, "automatic recovery is refused"):
                install(MANIFEST, "core", target, now=FIXED_NOW)
            self.assertEqual(agents.read_text(encoding="utf-8"), "must survive\n")
            self.assertTrue(wal_path.is_file())

    def test_forged_snapshot_cannot_restore_over_canonical_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            agents = target / "AGENTS.md"
            agents.write_text("must survive\n", encoding="utf-8")
            transaction_id = "c" * 32
            transaction_dir = (
                target / ".m3c3" / "reach-max-transactions" / transaction_id
            )
            transaction_dir.mkdir(parents=True)
            snapshot = transaction_dir / "snapshot-0000.bin"
            snapshot.write_text("forged replacement\n", encoding="utf-8")
            wal_path = target / ".m3c3" / "reach-max-transaction.json"
            forged = {
                "schema_version": "1.0",
                "distribution": "REACH-MAX",
                "distribution_version": "2.0.0",
                "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                "transaction_id": transaction_id,
                "status": "prepared",
                "changes": [
                    {
                        "destination": "AGENTS.md",
                        "before_exists": True,
                        "before_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                        "snapshot": (
                            ".m3c3/reach-max-transactions/%s/snapshot-0000.bin"
                            % transaction_id
                        ),
                        "after_exists": True,
                        "after_sha256": hashlib.sha256(agents.read_bytes()).hexdigest(),
                    }
                ],
                "generated_backups": [],
            }
            wal_path.write_text(json.dumps(forged), encoding="utf-8")
            with self.assertRaisesRegex(ConflictError, "automatic recovery is refused"):
                install(MANIFEST, "core", target, now=FIXED_NOW)
            self.assertEqual(agents.read_text(encoding="utf-8"), "must survive\n")
            self.assertEqual(snapshot.read_text(encoding="utf-8"), "forged replacement\n")

    def test_uninstall_removes_created_artifact_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            install(MANIFEST, "core", target, now=FIXED_NOW)
            result = uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertEqual(result["actions"][0]["action"], "remove")
            self.assertFalse((target / ".m3c3" / "M3C3.md").exists())
            self.assertFalse((target / ".m3c3" / "reach-max-install.json").exists())
            second = uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertEqual(second["state_action"], "absent")

    def test_uninstall_dry_run_preserves_files_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            install(MANIFEST, "core", target, now=FIXED_NOW)
            result = uninstall(MANIFEST, target, dry_run=True, now=FIXED_NOW)
            self.assertTrue(result["dry_run"])
            self.assertTrue((target / ".m3c3" / "M3C3.md").exists())
            self.assertTrue((target / ".m3c3" / "reach-max-install.json").exists())

    def test_uninstall_failure_rolls_back_artifacts_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            result = install(MANIFEST, "all", target, now=FIXED_NOW)
            destinations = [item["destination"] for item in result["actions"]]
            before = {destination: (target / destination).read_bytes() for destination in destinations}
            state_path = target / ".m3c3" / "reach-max-install.json"
            state_before = state_path.read_bytes()

            def fail_before_state(phase: str) -> None:
                if phase == "before_state":
                    raise RuntimeError("injected uninstall failure")

            with self.assertRaisesRegex(RuntimeError, "injected uninstall failure"):
                uninstall(
                    MANIFEST,
                    target,
                    now=FIXED_NOW,
                    _failure_injector=fail_before_state,
                )
            for destination, content in before.items():
                self.assertEqual((target / destination).read_bytes(), content)
            self.assertEqual(state_path.read_bytes(), state_before)
            self.assertFalse((target / ".m3c3" / "reach-max-transaction.json").exists())

    def test_uninstall_restores_force_overwritten_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            existing = target / "AGENTS.md"
            existing.write_text("original\n", encoding="utf-8")
            install(MANIFEST, "openai", target, force=True, now=FIXED_NOW)
            uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertEqual(existing.read_text(encoding="utf-8"), "original\n")

    def test_uninstall_refuses_modified_managed_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            install(MANIFEST, "core", target, now=FIXED_NOW)
            installed = target / ".m3c3" / "M3C3.md"
            installed.write_text("modified after install\n", encoding="utf-8")
            with self.assertRaises(ConflictError):
                uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertTrue(installed.exists())
            self.assertTrue((target / ".m3c3" / "reach-max-install.json").exists())

    def test_force_uninstall_preserves_modified_file_before_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            install(MANIFEST, "core", target, now=FIXED_NOW)
            installed = target / ".m3c3" / "M3C3.md"
            installed.write_text("modified after install\n", encoding="utf-8")
            result = uninstall(MANIFEST, target, force=True, now=FIXED_NOW)
            action = result["actions"][0]
            self.assertEqual(action["action"], "remove")
            self.assertEqual(
                (target / action["backup"]).read_text(encoding="utf-8"),
                "modified after install\n",
            )
            self.assertFalse(installed.exists())

    def test_preexisting_identical_artifact_survives_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            root, manifest, profiles = load_manifest(MANIFEST)
            artifact = resolved_artifacts(root, manifest, profiles, "core")[0]
            destination = target / artifact["destination"]
            destination.parent.mkdir(parents=True)
            destination.write_bytes(artifact["content"])
            install(MANIFEST, "core", target, now=FIXED_NOW)
            result = uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertEqual(result["actions"][0]["action"], "leave-preexisting")
            self.assertTrue(destination.exists())

    def test_force_reinstall_tracks_changed_preexisting_file_for_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            root, manifest, profiles = load_manifest(MANIFEST)
            artifact = resolved_artifacts(root, manifest, profiles, "core")[0]
            destination = target / artifact["destination"]
            destination.parent.mkdir(parents=True)
            destination.write_bytes(artifact["content"])
            install(MANIFEST, "core", target, now=FIXED_NOW)
            destination.write_text("user changed preexisting file\n", encoding="utf-8")
            install(MANIFEST, "core", target, force=True, now=FIXED_NOW)
            uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "user changed preexisting file\n",
            )

    def test_reinstall_after_preexisting_file_was_deleted_becomes_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            root, manifest, profiles = load_manifest(MANIFEST)
            artifact = resolved_artifacts(root, manifest, profiles, "core")[0]
            destination = target / artifact["destination"]
            destination.parent.mkdir(parents=True)
            destination.write_bytes(artifact["content"])
            install(MANIFEST, "core", target, now=FIXED_NOW)
            destination.unlink()
            install(MANIFEST, "core", target, now=FIXED_NOW)
            uninstall(MANIFEST, target, now=FIXED_NOW)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
