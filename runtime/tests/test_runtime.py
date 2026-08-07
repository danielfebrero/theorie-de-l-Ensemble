from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from m3c3_runtime import (
    ACTION_ALPHABET,
    AUTHORSHIP,
    HIERARCHY_WEIGHTS,
    KERNEL_VERSION,
    LAYER_ORDER,
    LAYER_TYPES,
    RUNTIME_VERSION,
    SAFETY_PROPERTIES,
    Action,
    ActionType,
    AuditIntegrityError,
    EvidenceState,
    HealthState,
    Layer,
    LifecycleStatus,
    M3C3Runtime,
    MembraneLevel,
    RuntimeViolation,
    SchemaValidationError,
    canonical_invariants,
    explore_transitions,
    replay_entries,
    replay_file,
    verify_entries,
    validate_event,
    validate_export,
    validate_state,
)
from m3c3_runtime.explore import (
    AbstractState,
    AbstractTransition,
    canonical_abstract_step,
)
from m3c3_runtime.audit import entry_hash
from m3c3_runtime.model import state_digest


KEY = bytes.fromhex("11" * 32)
EMITTER = "@cdxxotus"
AUTH_PROOF = "host-attested-test-proof"
SENSOR_PROOF = "host-attested-sensor-proof"
PRINCIPAL_PROOF = "host-attested-principal-proof"


class ManualClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def runtime(
    *,
    known: bool = True,
    clock: ManualClock | None = None,
    audit_path: Path | None = None,
) -> M3C3Runtime:
    return M3C3Runtime(
        signing_key=KEY,
        known_m3c3=known,
        clock=clock or ManualClock(),
        audit_path=audit_path,
        authority_verifier=lambda actor, operation, proof: proof == AUTH_PROOF,
        sensor_verifier=lambda actor, operation, proof: proof == SENSOR_PROOF,
        principal_verifier=lambda actor, proof: proof == PRINCIPAL_PROOF,
    )


def active_runtime(**kwargs: object) -> M3C3Runtime:
    instance = runtime(**kwargs)
    instance.activate_scope("unit-test", membrane="A2", actor="agent-a")
    return instance


class CanonicalInvariantTests(unittest.TestCase):
    def test_frozen_kernel_constants_are_exact(self) -> None:
        self.assertEqual(RUNTIME_VERSION, "2.0.0")
        self.assertEqual(KERNEL_VERSION, "1.0.0")
        self.assertEqual(
            LAYER_ORDER,
            (
                "binary",
                "forces",
                "math",
                "conscious_sets",
                "programs",
                "life_game_M1C1",
            ),
        )
        self.assertEqual(
            dict(HIERARCHY_WEIGHTS),
            {
                "binary": 0.08,
                "forces": 0.12,
                "math": 0.15,
                "conscious_sets": 0.22,
                "programs": 0.18,
                "life_game_M1C1": 0.25,
            },
        )
        self.assertEqual(sum(HIERARCHY_WEIGHTS.values()), 1.0)
        self.assertEqual(LAYER_TYPES["life_game_M1C1"]["type"], "L(P)")
        self.assertEqual(AUTHORSHIP["author_creator"], "Dani Bengal")
        self.assertEqual(AUTHORSHIP["civil_name"], "Daniel Febrero")
        self.assertEqual(AUTHORSHIP["handle"], "@cdxxotus")
        self.assertEqual(AUTHORSHIP["lock"], "irrevocable")
        self.assertEqual(
            tuple(ACTION_ALPHABET), tuple(action.value for action in ActionType)
        )
        self.assertEqual(set(SAFETY_PROPERTIES), {
            "S1_health_critical",
            "S2_cross_layer_cap",
            "S3_ruin_irreversible",
            "S4_no_upward_write",
            "S5_eligible_known",
        })
        self.assertEqual(
            canonical_invariants()["transition_state"],
            "S_t = (H_t, R_t, E_t, A_t, M_t)",
        )

    def test_constants_are_read_only(self) -> None:
        with self.assertRaises(TypeError):
            HIERARCHY_WEIGHTS["binary"] = 1.0  # type: ignore[index]
        with self.assertRaises(TypeError):
            AUTHORSHIP["author_creator"] = "other"  # type: ignore[index]


class SafetyPropertyTests(unittest.TestCase):
    def test_s1_unhealthy_runtime_cannot_write(self) -> None:
        instance = active_runtime()
        instance.update_health(
            HealthState(integrity_score=0.79, stability_index=1.0, anomaly_rate=0.0),
            sensor_proof=SENSOR_PROOF,
        )
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(
                Action(
                    ActionType.PROJECT,
                    "agent-a",
                    layer_dst=Layer.BINARY,
                    payload={"value": "forbidden"},
                )
            )
        self.assertEqual(caught.exception.code, "S1_HEALTH")
        self.assertIsNone(instance.state.H.layers["binary"])

    def test_s2_cross_layer_requires_bound_single_use_capability(self) -> None:
        instance = active_runtime()
        instance.execute(
            Action(
                ActionType.PROJECT,
                "agent-a",
                layer_dst=Layer.BINARY,
                payload={"value": 1},
            )
        )
        without_token = Action(
            ActionType.TRANSITION_UP,
            "agent-a",
            layer_src=Layer.BINARY,
            layer_dst=Layer.FORCES,
            payload={"value": 2},
            principal_proof=PRINCIPAL_PROOF,
        )
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(without_token)
        self.assertEqual(caught.exception.code, "S2_CAPABILITY")

        token = instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src=Layer.BINARY,
            layer_dst=Layer.FORCES,
            nonce="s2-nonce",
            token_id="s2-token",
            authority_proof=AUTH_PROOF,
        )
        instance.execute(replace(without_token, token=token))
        self.assertEqual(instance.state.H.layers["forces"], 2)
        self.assertNotIn("s2-token", instance.state.A.active_tokens)
        self.assertIn("s2-nonce", instance.state.A.consumed_nonces)
        with self.assertRaises(RuntimeViolation) as replayed:
            instance.execute(replace(without_token, token=token))
        self.assertIn(replayed.exception.code, {"CAP_INACTIVE", "CAP_REPLAY"})

    def test_s3_ruin_vetoes_irreversible_execution(self) -> None:
        instance = active_runtime()
        action = Action(
            ActionType.WRITE_LOCAL,
            "agent-a",
            layer_src=Layer.BINARY,
            layer_dst=Layer.BINARY,
            payload={"value": "irreversible"},
            ruin=True,
            irreversible=True,
        )
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(action)
        self.assertEqual(caught.exception.code, "S3_RUIN")
        self.assertIsNone(instance.state.H.layers["binary"])

    def test_s4_downward_write_requires_recovery_path(self) -> None:
        instance = active_runtime()
        instance.state.H.layers["binary"] = "trusted-base"
        action = Action(
            ActionType.WRITE_LOCAL,
            "agent-a",
            layer_src=Layer.PROGRAMS,
            layer_dst=Layer.BINARY,
            payload={"value": "upper-rewrite"},
        )
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(action)
        self.assertEqual(caught.exception.code, "S4_RECOVERY_PATH")
        self.assertEqual(instance.state.H.layers["binary"], "trusted-base")

        result = instance.recover(
            actor=EMITTER,
            rebuild={"binary": "rebuilt", "forces": "derived"},
            authority_proof=AUTH_PROOF,
        )
        self.assertEqual(result.value["rebuilt_layers"], ["binary", "forces"])
        self.assertEqual(instance.state.H.layers["binary"], "rebuilt")
        self.assertEqual(instance.state.M.recovery_generation, 1)

    def test_s5_unknown_agent_cannot_activate(self) -> None:
        instance = runtime(known=False)
        with self.assertRaises(RuntimeViolation) as caught:
            instance.activate_scope("forbidden", membrane="A1")
        self.assertEqual(caught.exception.code, "S5_UNKNOWN")
        self.assertFalse(instance.state.A.active)
        self.assertFalse(instance.state.A.eligible_for_activation)

    def test_insufficient_evidence_routes_to_fallback_without_execution(self) -> None:
        instance = active_runtime()
        instance.update_evidence(
            EvidenceState(score=0.49, tau=0.50), sensor_proof=SENSOR_PROOF
        )
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(
                Action(ActionType.ALLOCATE, "agent-a", payload={"choice": "x"})
            )
        self.assertEqual(caught.exception.code, "EVIDENCE")


class CapabilityTests(unittest.TestCase):
    def test_privileged_authority_is_deny_by_default_without_host_attestation(self) -> None:
        instance = M3C3Runtime(signing_key=KEY, known_m3c3=True, clock=ManualClock())
        instance.activate_scope("no-host-auth", actor="agent-a")
        with self.assertRaises(RuntimeViolation) as caught:
            instance.issue_capability(
                issuer=EMITTER,
                subject="agent-a",
                layer_src="binary",
                layer_dst="forces",
                authority_proof=AUTH_PROOF,
            )
        self.assertEqual(caught.exception.code, "AUTHORITY")

    def test_capability_consumption_requires_host_attested_principal(self) -> None:
        instance = M3C3Runtime(
            signing_key=KEY,
            known_m3c3=True,
            clock=ManualClock(),
            authority_verifier=lambda actor, operation, proof: proof == AUTH_PROOF,
        )
        instance.activate_scope("principal-boundary", actor="agent-a")
        token = instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src="binary",
            layer_dst="forces",
            nonce="principal-nonce",
            token_id="principal-token",
            authority_proof=AUTH_PROOF,
        )
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(
                Action(
                    ActionType.TRANSITION_UP,
                    "agent-a",
                    layer_src=Layer.BINARY,
                    layer_dst=Layer.FORCES,
                    token=token,
                    payload={"value": "blocked"},
                    principal_proof=PRINCIPAL_PROOF,
                )
            )
        self.assertEqual(caught.exception.code, "PRINCIPAL_AUTHORITY")
        self.assertIn("principal-token", instance.state.A.active_tokens)

    def test_permission_does_not_propagate_to_another_subject(self) -> None:
        instance = active_runtime()
        token = instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src="binary",
            layer_dst="forces",
            nonce="subject-nonce",
            token_id="subject-token",
            authority_proof=AUTH_PROOF,
        )
        action = Action(
            ActionType.TRANSITION_UP,
            "agent-b",
            layer_src=Layer.BINARY,
            layer_dst=Layer.FORCES,
            token=token,
            payload={"value": "no"},
            principal_proof=PRINCIPAL_PROOF,
        )
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(action)
        self.assertEqual(caught.exception.code, "CAP_SUBJECT")
        self.assertIn("subject-token", instance.state.A.revoked_token_ids)

    def test_expired_and_explicitly_revoked_tokens_are_rejected(self) -> None:
        clock = ManualClock()
        instance = active_runtime(clock=clock)
        expired = instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src="binary",
            layer_dst="forces",
            ttl_seconds=1,
            nonce="expiry-nonce",
            token_id="expiry-token",
            authority_proof=AUTH_PROOF,
        )
        clock.advance(2)
        action = Action(
            ActionType.TRANSITION_UP,
            "agent-a",
            layer_src=Layer.BINARY,
            layer_dst=Layer.FORCES,
            token=expired,
            payload={"value": 1},
            principal_proof=PRINCIPAL_PROOF,
        )
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(action)
        self.assertEqual(caught.exception.code, "CAP_EXPIRED")

        second = instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src="binary",
            layer_dst="forces",
            nonce="revoke-nonce",
            token_id="revoke-token",
            authority_proof=AUTH_PROOF,
        )
        instance.revoke_capability(
            "revoke-token", actor=EMITTER, authority_proof=AUTH_PROOF
        )
        with self.assertRaises(RuntimeViolation) as revoked:
            instance.execute(replace(action, token=second))
        self.assertEqual(revoked.exception.code, "CAP_REVOKED")

    def test_expiration_monitor_reads_public_descriptor_without_bearer(self) -> None:
        clock = ManualClock()
        instance = active_runtime(clock=clock)
        instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src="binary",
            layer_dst="forces",
            ttl_seconds=2,
            nonce="monitor-live-nonce",
            token_id="monitor-live-token",
            authority_proof=AUTH_PROOF,
        )
        self.assertEqual(
            instance.expire_capabilities(sensor_proof=SENSOR_PROOF), []
        )
        self.assertIn("monitor-live-token", instance.state.A.active_tokens)
        clock.advance(3)
        self.assertEqual(
            instance.expire_capabilities(sensor_proof=SENSOR_PROOF),
            ["monitor-live-token"],
        )
        self.assertIn("monitor-live-token", instance.state.A.revoked_token_ids)

    def test_tampered_signature_cannot_revoke_real_token_by_claimed_id(self) -> None:
        instance = active_runtime()
        token = instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src="binary",
            layer_dst="forces",
            nonce="tamper-nonce",
            token_id="tamper-token",
            authority_proof=AUTH_PROOF,
        )
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        action = Action(
            ActionType.TRANSITION_UP,
            "agent-a",
            layer_src=Layer.BINARY,
            layer_dst=Layer.FORCES,
            token=tampered,
            payload={"value": 1},
            principal_proof=PRINCIPAL_PROOF,
        )
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(action)
        self.assertEqual(caught.exception.code, "CAP_SIGNATURE")
        self.assertIn("tamper-token", instance.state.A.active_tokens)
        self.assertNotIn("tamper-token", instance.state.A.revoked_token_ids)

    def test_scope_change_revokes_old_scope_capability(self) -> None:
        instance = active_runtime()
        token = instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src="binary",
            layer_dst="forces",
            nonce="old-scope-nonce",
            token_id="old-scope-token",
            authority_proof=AUTH_PROOF,
        )
        instance.deactivate_scope(actor="agent-a")
        instance.activate_scope("new-scope", actor="agent-a")
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(
                Action(
                    ActionType.TRANSITION_UP,
                    "agent-a",
                    layer_src=Layer.BINARY,
                    layer_dst=Layer.FORCES,
                    token=token,
                    payload={"value": "forbidden"},
                    principal_proof=PRINCIPAL_PROOF,
                )
            )
        self.assertEqual(caught.exception.code, "CAP_REVOKED")


class LifecycleAndFallbackTests(unittest.TestCase):
    def test_membrane_opt_out_is_sticky_and_never_auto_activates(self) -> None:
        instance = active_runtime()
        instance.opt_out(actor="scope-owner")
        self.assertEqual(instance.state.A.membrane, MembraneLevel.A0_DORMANT)
        self.assertFalse(instance.state.A.active)
        with self.assertRaises(RuntimeViolation) as caught:
            instance.activate_scope("new-scope", membrane="A3")
        self.assertEqual(caught.exception.code, "OPTED_OUT")
        instance.clear_opt_out(actor="scope-owner")
        self.assertFalse(instance.state.A.active)
        instance.activate_scope("new-scope", membrane="A3")
        self.assertTrue(instance.state.A.active)

    def test_resolve_freezes_then_integrity_releases_layers(self) -> None:
        instance = active_runtime()
        result = instance.resolve(
            reason="conflict",
            affected_layers=[Layer.BINARY, Layer.LIFE_GAME_M1C1],
        )
        self.assertEqual(result.value["winner"], "life_game_M1C1")
        with self.assertRaises(RuntimeViolation) as caught:
            instance.execute(
                Action(
                    ActionType.WRITE_LOCAL,
                    "agent-a",
                    layer_src=Layer.BINARY,
                    layer_dst=Layer.BINARY,
                    payload={"value": 1},
                )
            )
        self.assertEqual(caught.exception.code, "FROZEN_LAYER")
        instance.release_resolution_lock()
        self.assertEqual(instance.state.A.frozen_layers, [])

    def test_kill_never_auto_resumes_and_requires_full_rebuild(self) -> None:
        instance = active_runtime()
        instance.kill(reason="test", actor=EMITTER, authority_proof=AUTH_PROOF)
        self.assertEqual(instance.state.A.lifecycle, LifecycleStatus.KILLED)
        with self.assertRaises(RuntimeViolation) as caught:
            instance.activate_scope("automatic", membrane="A1")
        self.assertEqual(caught.exception.code, "KILLED")

        rebuild = {layer: f"rebuilt-{layer}" for layer in LAYER_ORDER}
        with self.assertRaises(RuntimeViolation) as no_confirmation:
            instance.resume_after_kill(
                scope="resumed",
                rebuild=rebuild,
                actor=EMITTER,
                authority_proof=AUTH_PROOF,
            )
        self.assertEqual(no_confirmation.exception.code, "RESUME_AUTHORITY")
        instance.resume_after_kill(
            scope="resumed",
            rebuild=rebuild,
            actor=EMITTER,
            membrane="A2",
            explicit_confirmation=True,
            authority_proof=AUTH_PROOF,
        )
        self.assertTrue(instance.state.A.active)
        self.assertEqual(instance.state.A.scope, "resumed")

    def test_mass_revoke_trigger_requires_sensor_attestation_not_actor_string(self) -> None:
        instance = active_runtime()
        with self.assertRaises(RuntimeViolation) as caught:
            instance.kill(
                reason="untrusted monitor",
                actor="capability-monitor",
                mass_revoke=True,
                sensor_proof="wrong-proof",
            )
        self.assertEqual(caught.exception.code, "KILL_AUTHORITY")
        self.assertTrue(instance.state.A.active)
        instance.kill(
            reason="attested monitor",
            actor="capability-monitor",
            mass_revoke=True,
            sensor_proof=SENSOR_PROOF,
        )
        self.assertEqual(instance.state.A.lifecycle, LifecycleStatus.KILLED)


class TrustBoundaryAndAtomicityTests(unittest.TestCase):
    @staticmethod
    def _killed_runtime(*, audit_path: Path | None = None) -> M3C3Runtime:
        instance = active_runtime(audit_path=audit_path)
        instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src="binary",
            layer_dst="forces",
            nonce="resume-rollback-nonce",
            token_id="resume-rollback-token",
            authority_proof=AUTH_PROOF,
        )
        instance.kill(
            reason="resume transaction test",
            actor=EMITTER,
            authority_proof=AUTH_PROOF,
        )
        return instance

    @staticmethod
    def _resume_snapshot(instance: M3C3Runtime) -> dict[str, object]:
        return {
            "state": copy.deepcopy(instance.state.to_dict()),
            "audit_entries": instance.audit.entries(),
            "audit_head": instance.audit.head,
            "audit_length": instance.audit.length,
            "active_tokens": copy.deepcopy(instance.state.A.active_tokens),
            "revoked_token_ids": list(instance.state.A.revoked_token_ids),
            "issued_nonces": list(instance.state.A.issued_nonces),
            "consumed_nonces": list(instance.state.A.consumed_nonces),
        }

    def test_sensor_mutations_are_deny_by_default(self) -> None:
        cases = (
            ("health", lambda item: item.update_health(HealthState(), sensor_proof=SENSOR_PROOF)),
            (
                "evidence",
                lambda item: item.update_evidence(
                    EvidenceState(score=0.8), sensor_proof=SENSOR_PROOF
                ),
            ),
            (
                "regime",
                lambda item: item.update_regime("fuzzy", sensor_proof=SENSOR_PROOF),
            ),
        )
        for label, operation in cases:
            with self.subTest(label=label):
                instance = M3C3Runtime(
                    signing_key=KEY, known_m3c3=True, clock=ManualClock()
                )
                before = copy.deepcopy(instance.state.to_dict())
                with self.assertRaises(RuntimeViolation) as caught:
                    operation(instance)
                self.assertEqual(caught.exception.code, "SENSOR_AUTHORITY")
                # Only the denied audit anchor changes; semantic sensor values do not.
                after = instance.state.to_dict()
                self.assertEqual(after["H"], before["H"])
                self.assertEqual(after["R"], before["R"])
                self.assertEqual(after["E"], before["E"])

    def test_invalid_actor_is_prevalidated_before_activation_mutation(self) -> None:
        instance = runtime()
        before = copy.deepcopy(instance.state.to_dict())
        audit_length = instance.audit.length
        with self.assertRaises(ValueError):
            instance.activate_scope("must-not-activate", actor="")
        self.assertEqual(instance.state.to_dict(), before)
        self.assertEqual(instance.audit.length, audit_length)

    def test_io_failure_rolls_back_state_tokens_and_jsonl_append(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "atomic-audit.jsonl"
            instance = active_runtime(audit_path=audit_path)
            before_state = copy.deepcopy(instance.state.to_dict())
            before_bytes = audit_path.read_bytes()
            before_entries = instance.audit.entries()
            with mock.patch(
                "m3c3_runtime.audit.os.fsync",
                side_effect=[OSError("injected fsync failure"), None],
            ):
                with self.assertRaises(OSError):
                    instance.issue_capability(
                        issuer=EMITTER,
                        subject="agent-a",
                        layer_src="binary",
                        layer_dst="forces",
                        nonce="rollback-nonce",
                        token_id="rollback-token",
                        authority_proof=AUTH_PROOF,
                    )
            self.assertEqual(instance.state.to_dict(), before_state)
            self.assertEqual(instance.audit.entries(), before_entries)
            self.assertEqual(audit_path.read_bytes(), before_bytes)
            self.assertNotIn("rollback-token", instance.state.A.active_tokens)
            self.assertNotIn("rollback-nonce", instance.state.A.issued_nonces)

    def test_resume_preflight_rejections_leave_state_audit_and_tokens_unchanged(self) -> None:
        rebuild = {layer: f"rebuilt-{layer}" for layer in LAYER_ORDER}
        cases = (
            (
                "empty scope",
                {"scope": " "},
                RuntimeViolation,
                "SCOPE",
            ),
            (
                "dormant membrane",
                {"membrane": "A0"},
                RuntimeViolation,
                "SCOPE",
            ),
            (
                "unknown membrane",
                {"membrane": "A9"},
                ValueError,
                None,
            ),
            (
                "empty actor",
                {"actor": ""},
                ValueError,
                None,
            ),
            (
                "unattested authority",
                {"authority_proof": "invalid-proof"},
                RuntimeViolation,
                "RESUME_AUTHORITY",
            ),
        )
        for label, overrides, exception_type, expected_code in cases:
            with self.subTest(label=label):
                instance = self._killed_runtime()
                before = self._resume_snapshot(instance)
                arguments = {
                    "scope": "resumed",
                    "rebuild": rebuild,
                    "actor": EMITTER,
                    "membrane": "A2",
                    "explicit_confirmation": True,
                    "authority_proof": AUTH_PROOF,
                }
                arguments.update(overrides)
                with self.assertRaises(exception_type) as caught:
                    instance.resume_after_kill(**arguments)
                if expected_code is not None:
                    self.assertEqual(caught.exception.code, expected_code)
                self.assertEqual(self._resume_snapshot(instance), before)

    def test_resume_append_failure_rolls_back_state_audit_tokens_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "resume-atomic-audit.jsonl"
            instance = self._killed_runtime(audit_path=audit_path)
            before = self._resume_snapshot(instance)
            before_bytes = audit_path.read_bytes()
            rebuild = {layer: f"rebuilt-{layer}" for layer in LAYER_ORDER}
            with mock.patch(
                "m3c3_runtime.audit.os.fsync",
                side_effect=[OSError("injected resume fsync failure"), None],
            ):
                with self.assertRaises(OSError):
                    instance.resume_after_kill(
                        scope="resumed",
                        rebuild=rebuild,
                        actor=EMITTER,
                        membrane="A2",
                        explicit_confirmation=True,
                        authority_proof=AUTH_PROOF,
                    )
            self.assertEqual(self._resume_snapshot(instance), before)
            self.assertEqual(audit_path.read_bytes(), before_bytes)


class AuditAndReplayTests(unittest.TestCase):
    def test_audit_tampering_is_detected(self) -> None:
        instance = active_runtime()
        instance.execute(
            Action(
                ActionType.PROJECT,
                "agent-a",
                layer_dst=Layer.BINARY,
                payload={"value": 1},
            )
        )
        entries = instance.audit.entries()
        self.assertTrue(verify_entries(entries))
        tampered = copy.deepcopy(entries)
        tampered[-1]["data"]["action"]["payload"]["value"] = 2
        self.assertFalse(verify_entries(tampered, raise_on_error=False))
        with self.assertRaises(AuditIntegrityError):
            verify_entries(tampered)

        extra_field = copy.deepcopy(entries)
        extra_field[-1]["unhashed_extension"] = "must-not-be-ignored"
        self.assertFalse(verify_entries(extra_field, raise_on_error=False))
        with self.assertRaises(AuditIntegrityError):
            verify_entries(extra_field)

        date_only = copy.deepcopy(entries)
        date_only[-1]["timestamp"] = "2026-08-07"
        body = {key: value for key, value in date_only[-1].items() if key != "hash"}
        date_only[-1]["hash"] = entry_hash(body)
        self.assertFalse(verify_entries(date_only, raise_on_error=False))
        with self.assertRaises(AuditIntegrityError):
            verify_entries(date_only)

    def test_bearer_token_never_enters_export_or_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            instance = active_runtime(audit_path=audit_path)
            token = instance.issue_capability(
                issuer=EMITTER,
                subject="agent-a",
                layer_src="binary",
                layer_dst="forces",
                nonce="secret-nonce",
                token_id="secret-token",
                authority_proof=AUTH_PROOF,
            )
            self.assertNotIn(token, instance.export_json())
            self.assertNotIn(token, audit_path.read_text(encoding="utf-8"))
            descriptor = instance.state.A.active_tokens["secret-token"]
            self.assertEqual(set(descriptor), {"fingerprint", "claims"})
            self.assertNotIn("signature", descriptor["claims"])

    def test_deterministic_replay_matches_memory_and_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            instance = active_runtime(audit_path=audit_path)
            instance.execute(
                Action(
                    ActionType.PROJECT,
                    "agent-a",
                    layer_dst=Layer.BINARY,
                    payload={"value": {"fact": True}},
                )
            )
            token = instance.issue_capability(
                issuer=EMITTER,
                subject="agent-a",
                layer_src="binary",
                layer_dst="forces",
                nonce="replay-nonce",
                token_id="replay-token",
                authority_proof=AUTH_PROOF,
            )
            instance.execute(
                Action(
                    ActionType.TRANSITION_UP,
                    "agent-a",
                    layer_src=Layer.BINARY,
                    layer_dst=Layer.FORCES,
                    token=token,
                    payload={"value": {"force": "flow"}},
                    principal_proof=PRINCIPAL_PROOF,
                )
            )
            memory_replay = replay_entries(instance.audit.entries(), signing_key=KEY)
            file_replay = replay_file(audit_path, signing_key=KEY)
            self.assertEqual(memory_replay.state.to_dict(), instance.state.to_dict())
            self.assertEqual(file_replay.state.to_dict(), instance.state.to_dict())
            self.assertEqual(memory_replay.audit_head, instance.audit.head)

    def test_keyed_replay_rejects_a_rechained_forged_token_descriptor(self) -> None:
        instance = active_runtime()
        instance.issue_capability(
            issuer=EMITTER,
            subject="agent-a",
            layer_src="binary",
            layer_dst="forces",
            nonce="keyed-replay-nonce",
            token_id="keyed-replay-token",
            authority_proof=AUTH_PROOF,
        )
        forged = instance.audit.entries()
        last = forged[-1]
        descriptor = last["state_after"]["A"]["active_tokens"]["keyed-replay-token"]
        descriptor["fingerprint"] = "0" * 64
        last["state_digest"] = state_digest(last["state_after"])
        body = {key: value for key, value in last.items() if key != "hash"}
        last["hash"] = entry_hash(body)
        self.assertTrue(verify_entries(forged))
        with self.assertRaises(AuditIntegrityError):
            replay_entries(forged, signing_key=KEY)

    def test_replay_anchor_detects_truncation_and_consistent_rechaining(self) -> None:
        instance = active_runtime()
        entries = instance.audit.entries()
        expected_head = instance.audit.head
        expected_length = instance.audit.length

        with self.assertRaises(AuditIntegrityError):
            replay_entries(
                entries[:-1],
                expected_head=expected_head,
                expected_length=expected_length,
            )

        rechained = copy.deepcopy(entries)
        rechained[-1]["data"]["attacker_note"] = "internally-valid rewrite"
        body = {key: value for key, value in rechained[-1].items() if key != "hash"}
        rechained[-1]["hash"] = entry_hash(body)
        self.assertTrue(verify_entries(rechained))
        unanchored = replay_entries(rechained)
        self.assertFalse(unanchored.externally_anchored)
        with self.assertRaises(AuditIntegrityError):
            replay_entries(rechained, expected_head=expected_head)

    def test_versioned_export_is_bound_to_verified_audit(self) -> None:
        instance = active_runtime()
        exported = instance.export()
        self.assertEqual(exported["schema_version"], "m3c3.state-export/v2")
        self.assertEqual(exported["state_symbol"], "S_t = (H_t, R_t, E_t, A_t, M_t)")
        self.assertTrue(exported["audit"]["verified"])
        self.assertEqual(exported["state"]["M"]["audit_head"], instance.audit.head)

    def test_external_anchor_detects_valid_prefix_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            instance = active_runtime(audit_path=audit_path)
            expected_head = instance.audit.head
            expected_length = instance.audit.length
            lines = audit_path.read_text(encoding="utf-8").splitlines()
            audit_path.write_text(lines[0] + "\n", encoding="utf-8")
            runtime_root = Path(__file__).resolve().parents[1]
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(runtime_root)
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "m3c3_runtime",
                    "verify-audit",
                    str(audit_path),
                    "--expected-head",
                    expected_head,
                    "--expected-length",
                    str(expected_length),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(process.returncode, 1)
            self.assertIn("external anchor", process.stderr)


class ExplorationTests(unittest.TestCase):
    def test_bounded_exploration_covers_guard_denials_without_violation(self) -> None:
        report = explore_transitions(max_depth=6, max_states=512)
        self.assertTrue(report.safe)
        self.assertFalse(report.truncated)
        self.assertGreater(report.states_visited, 50)
        self.assertGreater(report.transitions_checked, 500)
        for code in (
            "S1_HEALTH",
            "S2_CAPABILITY",
            "S3_RUIN",
            "S4_RECOVERY_PATH",
            "S5_UNKNOWN",
        ):
            self.assertGreater(report.denial_counts.get(code, 0), 0)

    def test_explorer_detects_an_unsafe_activation_policy(self) -> None:
        def unsafe_step(state: AbstractState, action: object) -> AbstractTransition:
            if getattr(action, "name") == "activate":
                return AbstractTransition(
                    state, action, replace(state, active=True), True, None
                )
            return canonical_abstract_step(state, action)

        report = explore_transitions(max_depth=1, max_states=64, step=unsafe_step)
        self.assertFalse(report.safe)
        self.assertIn(
            "S5_eligible_known",
            {item["property"] for item in report.safety_violations},
        )


class ArtifactTests(unittest.TestCase):
    def test_json_schemas_are_valid_json_with_unique_ids(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schemas = sorted((root / "schemas").glob("*.schema.json"))
        self.assertGreaterEqual(len(schemas), 5)
        ids = set()
        for schema_path in schemas:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertNotIn(schema["$id"], ids)
            ids.add(schema["$id"])

    def test_targeted_stdlib_validators_enforce_state_event_and_export(self) -> None:
        instance = active_runtime()
        exported = instance.export()
        validate_state(exported["state"], audit_meta=True)
        validate_event(instance.audit.entries()[-1])
        validate_export(exported)
        malformed = copy.deepcopy(exported)
        del malformed["state"]["A"]["known_m3c3"]
        with self.assertRaises(SchemaValidationError):
            validate_export(malformed)

    def test_schema_aliases_and_stdlib_reject_missing_required_fields(self) -> None:
        schema_root = Path(__file__).resolve().parents[1] / "schemas"

        def required_keywords(
            instance: object, schema: dict[str, object] | bool
        ) -> None:
            if schema is True:
                return
            if schema is False:
                raise SchemaValidationError("boolean false schema rejects the value")
            if "$ref" in schema:
                referenced = json.loads(
                    (schema_root / str(schema["$ref"])).read_text(encoding="utf-8")
                )
                required_keywords(instance, referenced)
            for branch in schema.get("allOf", []):
                required_keywords(instance, branch)
            if not isinstance(instance, dict):
                return
            for field in schema.get("required", []):
                if field not in instance:
                    raise SchemaValidationError(f"missing required field: {field}")
            for field, subschema in schema.get("properties", {}).items():
                if field in instance:
                    required_keywords(instance[field], subschema)

        instance = active_runtime()
        exported = instance.export()
        for filename in ("export.schema.json", "export-v2.schema.json"):
            schema = json.loads((schema_root / filename).read_text(encoding="utf-8"))
            required_keywords(exported, schema)
            malformed = copy.deepcopy(exported)
            del malformed["state"]["M"]["audit_head"]
            with self.assertRaises(SchemaValidationError, msg=filename):
                required_keywords(malformed, schema)
            with self.assertRaises(SchemaValidationError, msg=filename):
                validate_export(malformed)

        event = instance.audit.entries()[-1]
        for filename in ("audit-entry.schema.json", "event-v2.schema.json"):
            schema = json.loads((schema_root / filename).read_text(encoding="utf-8"))
            malformed = copy.deepcopy(event)
            del malformed["actor"]
            with self.assertRaises(SchemaValidationError, msg=filename):
                required_keywords(malformed, schema)
            with self.assertRaises(SchemaValidationError, msg=filename):
                validate_event(malformed)

        capability_schema = json.loads(
            (schema_root / "capability-token.schema.json").read_text(encoding="utf-8")
        )
        claims = {
            "schema_version": "m3c3.capability/v2",
            "jti": "schema-token",
            "issuer": EMITTER,
            "subject": "agent-a",
            "scope": "unit-test",
            "layer_src": "binary",
            "layer_dst": "forces",
            "action": "transition_up",
            "issued_at": 1,
            "expires_at": 2,
            "nonce": "schema-nonce",
        }
        required_keywords(claims, capability_schema)
        del claims["expires_at"]
        with self.assertRaises(SchemaValidationError):
            required_keywords(claims, capability_schema)

    def test_cli_exploration(self) -> None:
        runtime_root = Path(__file__).resolve().parents[1]
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(runtime_root)
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "m3c3_runtime",
                "explore",
                "--max-depth",
                "2",
                "--max-states",
                "64",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(json.loads(process.stdout)["safe"])


if __name__ == "__main__":
    unittest.main()
