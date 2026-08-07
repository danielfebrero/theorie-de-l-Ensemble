from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from continuum.memory.validate import MemoryValidationError, REPOSITORY_ROOT, validate_repository


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_yaml(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")


def build_fixture(root: Path) -> dict[str, Path]:
    memory = root / "continuum/memory"
    patterns = memory / "patterns"
    audit = root / "continuum/audit"
    patterns.mkdir(parents=True)
    audit.mkdir(parents=True)
    (memory / "schema-v2.yaml").write_text(
        (REPOSITORY_ROOT / "continuum/memory/schema-v2.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    source = audit / "source.yaml"
    source.write_text("event: original\n", encoding="utf-8")
    entry_path = patterns / "entry-v1.yaml"
    entry = {
        "memory_entry": {
            "id": "negative-fixture-v1",
            "version": "1.0.0",
            "kind": "decision_pattern",
            "status": "active",
            "statement": "fixture",
            "scope": {"master_paths": ["activation_policy"]},
            "observed_at": "2026-08-07T00:00:00Z",
            "sources": [
                {
                    "path": "continuum/audit/source.yaml",
                    "sha256": digest(source),
                    "evidence_class": "canonical",
                    "result": "supports",
                }
            ],
            "evidence_summary": {
                "strength": "fixture",
                "result": "supports",
                "limitations": [],
            },
            "lifecycle": {
                "promoted_by": "fixture authority",
                "promotion_event": "continuum/audit/source.yaml",
                "rollback_if": "fixture fails",
                "supersedes": None,
            },
        }
    }
    write_yaml(entry_path, entry)
    write_yaml(
        patterns / "index.yaml",
        {"pattern_index": {"version": "2.0.0-rc.1", "entries": ["entry-v1.yaml"]}},
    )

    snapshot_path = memory / "parameters/snapshot.yaml"
    write_yaml(
        snapshot_path,
        {
            "snapshot": {
                "master_version": "1.0.0",
                "taken_at": "2026-08-07T00:00:00Z",
            }
        },
    )
    creator_path = memory / "creator/index.yaml"
    write_yaml(
        creator_path,
        {
            "creator_index": {
                "author_creator": "Fixture Author",
                "handle": "@fixture",
                "evidence": ["fixture"],
            }
        },
    )
    index_path = memory / "index.yaml"
    index = {
        "continuum_memory_index": {
            "version": "2.0.0-rc.1",
            "schema": "continuum/memory/schema-v2.yaml",
            "history_base": None,
            "mutability": "append_only",
            "entries": [
                {
                    "id": "negative-fixture-v1",
                    "path": "continuum/memory/patterns/entry-v1.yaml",
                    "status": "active",
                    "sha256": digest(entry_path),
                }
            ],
            "snapshots": [
                {
                    "path": "continuum/memory/parameters/snapshot.yaml",
                    "sha256": digest(snapshot_path),
                }
            ],
            "creator_index": {
                "path": "continuum/memory/creator/index.yaml",
                "sha256": digest(creator_path),
            },
            "promotion": {
                "required": ["designated_emitter_signal", "evidence_paths", "immutable_revision"]
            },
            "rollback": {
                "action": "append_rolled_back_revision",
                "destructive_rewrite_forbidden": True,
            },
        }
    }
    write_yaml(index_path, index)
    return {
        "source": source,
        "entry": entry_path,
        "index": index_path,
        "patterns": patterns,
    }


def refresh_entry_hash(paths: dict[str, Path]) -> None:
    index = yaml.safe_load(paths["index"].read_text(encoding="utf-8"))
    index["continuum_memory_index"]["entries"][0]["sha256"] = digest(paths["entry"])
    write_yaml(paths["index"], index)


class ContinuumMemoryValidationTests(unittest.TestCase):
    def test_repository_memory_is_valid(self) -> None:
        result = validate_repository(REPOSITORY_ROOT)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["count"], 3)
        self.assertTrue(result["history_base"])
        self.assertGreaterEqual(len(result["history_compared"]), 2)

    def test_tampered_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = build_fixture(root)
            paths["source"].write_text("event: tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(MemoryValidationError, "source hash mismatch"):
                validate_repository(root)

    def test_tampered_entry_is_rejected_by_content_address(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = build_fixture(root)
            document = yaml.safe_load(paths["entry"].read_text(encoding="utf-8"))
            document["memory_entry"]["statement"] = "rewritten in place"
            write_yaml(paths["entry"], document)
            with self.assertRaisesRegex(MemoryValidationError, "content hash mismatch"):
                validate_repository(root)

    def test_unindexed_pattern_yaml_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = build_fixture(root)
            hidden = paths["patterns"] / "nested/hidden.yml"
            hidden.parent.mkdir()
            hidden.write_text("memory_entry: {}\n", encoding="utf-8")
            with self.assertRaisesRegex(MemoryValidationError, "pattern files and memory index disagree"):
                validate_repository(root)

    def test_unindexed_yaml_outside_known_subtrees_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_fixture(root)
            hidden = root / "continuum/memory/hidden/nested-entry.yml"
            hidden.parent.mkdir(parents=True)
            hidden.write_text("memory_entry: {}\n", encoding="utf-8")
            with self.assertRaisesRegex(MemoryValidationError, "YAML files and memory index disagree"):
                validate_repository(root)

    def test_invalid_promotion_lifecycle_is_rejected_even_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = build_fixture(root)
            document = yaml.safe_load(paths["entry"].read_text(encoding="utf-8"))
            document["memory_entry"]["lifecycle"]["promoted_by"] = None
            write_yaml(paths["entry"], document)
            refresh_entry_hash(paths)
            with self.assertRaisesRegex(MemoryValidationError, "promoted_by"):
                validate_repository(root)

    def test_self_declared_provider_attestation_is_default_denied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = build_fixture(root)
            document = yaml.safe_load(paths["entry"].read_text(encoding="utf-8"))
            document["memory_entry"]["sources"][0]["evidence_class"] = "provider_attested"
            write_yaml(paths["entry"], document)
            refresh_entry_hash(paths)
            with self.assertRaisesRegex(MemoryValidationError, "provider_attested is unverifiable"):
                validate_repository(root)

    def test_git_base_ref_rejects_in_place_rewrite_even_if_index_hash_is_updated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = build_fixture(root)
            for command in (
                ["git", "init", "-q"],
                ["git", "config", "user.email", "fixture@example.invalid"],
                ["git", "config", "user.name", "M3C3 fixture"],
                ["git", "add", "."],
                ["git", "commit", "-qm", "fixture"],
            ):
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            document = yaml.safe_load(paths["entry"].read_text(encoding="utf-8"))
            document["memory_entry"]["statement"] = "rewritten after base"
            write_yaml(paths["entry"], document)
            refresh_entry_hash(paths)
            with self.assertRaisesRegex(MemoryValidationError, "immutable memory artifact modified"):
                validate_repository(root, base_ref="HEAD")

    def test_duplicate_yaml_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = root / "continuum/memory"
            memory.mkdir(parents=True)
            (memory / "schema-v2.yaml").write_text(
                (REPOSITORY_ROOT / "continuum/memory/schema-v2.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (memory / "index.yaml").write_text(
                "continuum_memory_index:\n"
                "  mutability: append_only\n"
                "  mutability: mutable\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MemoryValidationError, "duplicate YAML key"):
                validate_repository(root)


if __name__ == "__main__":
    unittest.main()
