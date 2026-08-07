from __future__ import annotations

import unittest

from capsules.validate import REPOSITORY_ROOT, validate_capsule_document, validate_capsules


class CapsuleValidationTests(unittest.TestCase):
    def test_repository_capsules_have_observable_bindings(self) -> None:
        result = validate_capsules(REPOSITORY_ROOT)
        self.assertEqual(result["status"], "pass", result["errors"])
        self.assertEqual(result["capsules_checked"], 7)

    def test_immediate_ready_claim_is_rejected(self) -> None:
        fixture = {
            "cdxx_capsule": {
                "name": "unsafe-fixture",
                "activation": "immediate",
                "status": "ready",
                "runtime_binding": {
                    "version": "2.0.0",
                    "implementation": "runtime/m3c3_runtime/engine.py",
                    "verification": "runtime/tests/test_runtime.py::MissingVerificationSymbol",
                    "coverage": "fixture",
                    "limitations": ["fixture"],
                },
            }
        }
        errors = validate_capsule_document(fixture, "fixture.yaml", REPOSITORY_ROOT)
        self.assertTrue(any("scope_controlled" in error for error in errors))
        self.assertTrue(any("status must" in error for error in errors))
        self.assertTrue(any("symbol" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
