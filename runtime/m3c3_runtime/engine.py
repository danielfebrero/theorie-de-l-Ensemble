"""Reference M3C3 v2 policy machine built only on the Python standard library."""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .audit import AuditLog, utc_now
from .capability import CapabilityToken, CapabilityTokenManager, epoch_seconds
from .constants import (
    CRITICAL_THRESHOLD,
    DESIGNATED_EMITTER_ALIASES,
    HIERARCHY_WEIGHTS,
    KERNEL_VERSION,
    LAYER_ORDER,
    RUNTIME_VERSION,
    canonical_invariants,
)
from .errors import AuditIntegrityError, RuntimeViolation, TokenValidationError
from .model import (
    Action,
    ActionType,
    EvidenceState,
    HealthState,
    Layer,
    LifecycleStatus,
    M3C3State,
    MembraneLevel,
    Regime,
    canonical_json,
    state_digest,
)
from .validation import validate_export

EXPORT_SCHEMA_VERSION = "m3c3.state-export/v2"


@dataclass(frozen=True)
class TransitionResult:
    action: str
    outcome: str
    value: Any
    state_digest: str
    audit_hash: str


def is_write_allowed(
    *,
    state: M3C3State,
    layer_src: Layer,
    layer_dst: Layer,
    valid_capability: bool = False,
    recovery_path: bool = False,
) -> bool:
    """Executable form of the frozen v1 write rule."""

    if not state.H.health.healthy or state.A.lifecycle is LifecycleStatus.KILLED:
        return False
    source = layer_src.index
    destination = layer_dst.index
    relation = (
        source == destination
        or (destination == source + 1 and valid_capability)
        or (destination < source and recovery_path)
    )
    no_illegal_downward_write = not (destination < source and not recovery_path)
    return relation and no_illegal_downward_write


class M3C3Runtime:
    """Stateful implementation of ``S=(H,R,E,A,M)`` and the v1 LTS.

    A0–A3 controls engagement and presentation depth only.  It never weakens the
    canonical health, capability, ruin, evidence, recovery, or authorship guards.
    """

    def __init__(
        self,
        *,
        signing_key: bytes,
        known_m3c3: bool,
        regime: Regime | str = Regime.MIXED,
        health: HealthState | None = None,
        evidence: EvidenceState | None = None,
        audit_path: str | Path | None = None,
        clock: Callable[[], datetime] = utc_now,
        authority_verifier: Callable[[str, str, object | None], bool] | None = None,
        sensor_verifier: Callable[[str, str, object | None], bool] | None = None,
        principal_verifier: Callable[[str, object | None], bool] | None = None,
    ) -> None:
        if not isinstance(known_m3c3, bool):
            raise TypeError("known_m3c3 must be an explicit boolean")
        if health is not None and not isinstance(health, HealthState):
            raise TypeError("health must be HealthState")
        if evidence is not None and not isinstance(evidence, EvidenceState):
            raise TypeError("evidence must be EvidenceState")
        if authority_verifier is not None and not callable(authority_verifier):
            raise TypeError("authority_verifier must be callable")
        if sensor_verifier is not None and not callable(sensor_verifier):
            raise TypeError("sensor_verifier must be callable")
        if principal_verifier is not None and not callable(principal_verifier):
            raise TypeError("principal_verifier must be callable")
        self._lock = threading.RLock()
        self._clock = clock
        self._authority_verifier = authority_verifier
        self._sensor_verifier = sensor_verifier
        self._principal_verifier = principal_verifier
        self._audit_failed = False
        self.tokens = CapabilityTokenManager(signing_key)
        self.state = M3C3State(R=Regime(regime))
        self.state.H.health = health or HealthState()
        self.state.E = evidence or EvidenceState()
        self.state.A.known_m3c3 = known_m3c3
        self.state.A.eligible_for_activation = known_m3c3
        self.audit = AuditLog(audit_path, clock=clock)
        self._last_committed_state = copy.deepcopy(self.state)
        self._record(
            "runtime.initialized",
            "runtime",
            "applied",
            {
                "runtime_version": RUNTIME_VERSION,
                "kernel_version": KERNEL_VERSION,
                "known_m3c3": known_m3c3,
            },
        )

    def _sync_audit_state(self) -> None:
        self.state.M.audit_head = self.audit.head
        self.state.M.audit_length = self.audit.length

    def _record(
        self,
        event: str,
        actor: str,
        outcome: str,
        data: Mapping[str, Any],
    ) -> str:
        self._prevalidate_actor(actor)
        if self._audit_failed:
            self.state = copy.deepcopy(self._last_committed_state)
            raise AuditIntegrityError("audit is fail-closed after a previous append error")
        try:
            entry = self.audit.append(
                event=event,
                actor=actor,
                outcome=outcome,
                data=data,
                state=self.state,
            )
        except BaseException:
            self.state = copy.deepcopy(self._last_committed_state)
            self._audit_failed = True
            raise
        self._sync_audit_state()
        self._last_committed_state = copy.deepcopy(self.state)
        return entry.hash

    @staticmethod
    def _prevalidate_actor(actor: str) -> None:
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor must be a non-empty string")

    def _reject(
        self,
        event: str,
        actor: str,
        violation: RuntimeViolation,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        payload = {"error": violation.to_dict()}
        if data:
            payload.update(copy.deepcopy(dict(data)))
        self._record(event, actor, "denied", payload)
        raise violation

    def _host_attested(
        self, actor: str, operation: str, proof: object | None = None
    ) -> bool:
        if self._authority_verifier is None:
            return False
        try:
            return bool(self._authority_verifier(actor, operation, proof))
        except Exception:
            return False

    def _sensor_attested(
        self, actor: str, operation: str, proof: object | None = None
    ) -> bool:
        if self._sensor_verifier is None:
            return False
        try:
            return bool(self._sensor_verifier(actor, operation, proof))
        except Exception:
            return False

    def _principal_attested(self, actor: str, proof: object | None = None) -> bool:
        if self._principal_verifier is None:
            return False
        try:
            return bool(self._principal_verifier(actor, proof))
        except Exception:
            return False

    def _is_emitter(
        self, actor: str, operation: str, proof: object | None = None
    ) -> bool:
        """Ask the host trust boundary to attest the designated emitter.

        String aliases are only identifiers.  With no injected verifier the
        privileged authority channel is deny-by-default.
        """

        return actor in DESIGNATED_EMITTER_ALIASES and self._host_attested(
            actor, operation, proof
        )

    def _require_active(self, actor: str, event: str) -> None:
        if self.state.A.lifecycle is LifecycleStatus.KILLED:
            self._reject(
                event,
                actor,
                RuntimeViolation(
                    "KILLED", "runtime is killed; explicit emitter recovery is required"
                ),
            )
        if not self.state.A.active:
            self._reject(
                event,
                actor,
                RuntimeViolation("INACTIVE", "no M3C3 scope is active"),
            )

    def _productive_guards(self, action: Action) -> None:
        if not self.state.H.health.healthy:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation(
                    "S1_HEALTH",
                    "Health_F4(S) is below the warning threshold",
                    forme4_score=self.state.H.health.forme4_score,
                ),
                {"action": action.to_dict(include_token=False)},
            )
        if action.ruin:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation(
                    "S3_RUIN",
                    "ruin_gate vetoed the candidate action",
                    irreversible=action.irreversible,
                ),
                {"action": action.to_dict(include_token=False)},
            )
        if not self.state.E.sufficient:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation(
                    "EVIDENCE",
                    "Evidence(x) is below tau",
                    score=self.state.E.score,
                    tau=self.state.E.tau,
                ),
                {"action": action.to_dict(include_token=False)},
            )

    def activate_scope(
        self,
        scope: str,
        *,
        membrane: MembraneLevel | int | str = MembraneLevel.A1_SHADOW,
        actor: str = "agent",
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            level = MembraneLevel.parse(membrane)
            if self.state.A.lifecycle is LifecycleStatus.KILLED:
                self._reject(
                    "lifecycle.activate",
                    actor,
                    RuntimeViolation(
                        "KILLED", "killed runtimes require resume_after_kill"
                    ),
                )
            if not self.state.A.known_m3c3:
                self._reject(
                    "lifecycle.activate",
                    actor,
                    RuntimeViolation(
                        "S5_UNKNOWN", "unknown agents are not eligible for activation"
                    ),
                )
            if self.state.A.opted_out:
                self._reject(
                    "lifecycle.activate",
                    actor,
                    RuntimeViolation("OPTED_OUT", "the scope owner opted out of M3C3"),
                )
            if not isinstance(scope, str) or not scope.strip():
                self._reject(
                    "lifecycle.activate",
                    actor,
                    RuntimeViolation("SCOPE", "scope must be a non-empty string"),
                )
            if level is MembraneLevel.A0_DORMANT:
                self._reject(
                    "lifecycle.activate",
                    actor,
                    RuntimeViolation("A0_DORMANT", "A0 is dormant, not an active level"),
                )
            if self.state.A.active:
                self._reject(
                    "lifecycle.activate",
                    actor,
                    RuntimeViolation("ALREADY_ACTIVE", "a scope is already active"),
                    {"active_scope": self.state.A.scope},
                )
            self.state.A.scope = scope.strip()
            self.state.A.membrane = level
            self.state.A.lifecycle = LifecycleStatus.ACTIVE
            audit_hash = self._record(
                "lifecycle.activate",
                actor,
                "applied",
                {"scope": self.state.A.scope, "membrane": level.label},
            )
            return self._result(ActionType.ACTIVATE_SCOPE, None, audit_hash)

    def deactivate_scope(
        self, *, actor: str = "agent", reason: str = "scope_end"
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            if not isinstance(reason, str):
                raise TypeError("deactivation reason must be a string")
            if not self.state.A.active:
                self._reject(
                    "lifecycle.deactivate",
                    actor,
                    RuntimeViolation("INACTIVE", "no active scope to deactivate"),
                )
            revoked = self.tokens.revoke_all(self.state)
            previous_scope = self.state.A.scope
            self.state.A.scope = None
            self.state.A.membrane = MembraneLevel.A0_DORMANT
            self.state.A.lifecycle = LifecycleStatus.INACTIVE
            audit_hash = self._record(
                "lifecycle.deactivate",
                actor,
                "applied",
                {
                    "scope": previous_scope,
                    "reason": reason,
                    "revoked_token_ids": revoked,
                },
            )
            return self._result(ActionType.DEACTIVATE_SCOPE, None, audit_hash)

    def opt_out(self, *, actor: str = "scope-owner") -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            revoked = self.tokens.revoke_all(self.state)
            previous_scope = self.state.A.scope
            self.state.A.opted_out = True
            self.state.A.scope = None
            self.state.A.membrane = MembraneLevel.A0_DORMANT
            if self.state.A.lifecycle is not LifecycleStatus.KILLED:
                self.state.A.lifecycle = LifecycleStatus.INACTIVE
            audit_hash = self._record(
                "membrane.opt_out",
                actor,
                "applied",
                {"scope": previous_scope, "revoked_token_ids": revoked},
            )
            return self._result("opt_out", None, audit_hash)

    def clear_opt_out(self, *, actor: str = "scope-owner") -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            if not self.state.A.opted_out:
                self._reject(
                    "membrane.clear_opt_out",
                    actor,
                    RuntimeViolation("NOT_OPTED_OUT", "opt-out is not set"),
                )
            self.state.A.opted_out = False
            audit_hash = self._record(
                "membrane.clear_opt_out", actor, "applied", {"auto_activate": False}
            )
            return self._result("clear_opt_out", None, audit_hash)

    def update_health(
        self,
        health: HealthState,
        *,
        actor: str = "forme4-health-monitor",
        sensor_proof: object | None = None,
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            if not isinstance(health, HealthState):
                raise TypeError("health must be HealthState")
            if not self._sensor_attested(actor, "sensor.health", sensor_proof):
                self._reject(
                    "sensor.health",
                    actor,
                    RuntimeViolation(
                        "SENSOR_AUTHORITY",
                        "host did not attest the Forme #4 health sensor",
                    ),
                    {"proof_logged": False},
                )
            before = self.state.H.health.to_dict()
            self.state.H.health = copy.deepcopy(health)
            revoked: list[str] = []
            if not health.healthy:
                revoked = self.tokens.revoke_all(self.state)
            audit_hash = self._record(
                "sensor.health",
                actor,
                "applied",
                {
                    "before": before,
                    "after": health.to_dict(),
                    "revoked_token_ids": revoked,
                },
            )
            return self._result("update_health", health.to_dict(), audit_hash)

    def update_evidence(
        self,
        evidence: EvidenceState,
        *,
        actor: str = "evidence-monitor",
        sensor_proof: object | None = None,
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            if not isinstance(evidence, EvidenceState):
                raise TypeError("evidence must be EvidenceState")
            if not self._sensor_attested(actor, "sensor.evidence", sensor_proof):
                self._reject(
                    "sensor.evidence",
                    actor,
                    RuntimeViolation(
                        "SENSOR_AUTHORITY",
                        "host did not attest the evidence sensor",
                    ),
                    {"proof_logged": False},
                )
            before = self.state.E.to_dict()
            self.state.E = copy.deepcopy(evidence)
            audit_hash = self._record(
                "sensor.evidence",
                actor,
                "applied",
                {"before": before, "after": evidence.to_dict()},
            )
            return self._result("update_evidence", evidence.to_dict(), audit_hash)

    def update_regime(
        self,
        regime: Regime | str,
        *,
        actor: str = "regime-detector",
        sensor_proof: object | None = None,
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            if not self._sensor_attested(actor, "sensor.regime", sensor_proof):
                self._reject(
                    "sensor.regime",
                    actor,
                    RuntimeViolation(
                        "SENSOR_AUTHORITY",
                        "host did not attest the regime detector",
                    ),
                    {"proof_logged": False},
                )
            before = self.state.R.value
            self.state.R = Regime(regime)
            audit_hash = self._record(
                "sensor.regime",
                actor,
                "applied",
                {"before": before, "after": self.state.R.value},
            )
            return self._result("update_regime", self.state.R.value, audit_hash)

    def issue_capability(
        self,
        *,
        issuer: str,
        subject: str,
        layer_src: Layer | str,
        layer_dst: Layer | str,
        ttl_seconds: int = 45,
        nonce: str | None = None,
        token_id: str | None = None,
        authority_proof: object | None = None,
    ) -> str:
        with self._lock:
            self._prevalidate_actor(issuer)
            if not isinstance(subject, str) or not subject:
                raise ValueError("capability subject must be a non-empty string")
            source = Layer.parse(layer_src)
            destination = Layer.parse(layer_dst)
            assert source is not None and destination is not None
            if not self._is_emitter(issuer, "capability.issue", authority_proof):
                self._reject(
                    "capability.issue",
                    issuer,
                    RuntimeViolation(
                        "AUTHORITY",
                        "host did not attest the designated emitter for issuance",
                    ),
                    {
                        "subject": subject,
                        "layer_src": source.value,
                        "layer_dst": destination.value,
                        "proof_logged": False,
                    },
                )
            try:
                encoded, token = self.tokens.issue(
                    self.state,
                    issuer=issuer,
                    subject=subject,
                    layer_src=source,
                    layer_dst=destination,
                    ttl_seconds=ttl_seconds,
                    now=self._clock(),
                    nonce=nonce,
                    token_id=token_id,
                )
            except TokenValidationError as exc:
                self._reject(
                    "capability.issue",
                    issuer,
                    exc,
                    {
                        "subject": subject,
                        "layer_src": source.value,
                        "layer_dst": destination.value,
                        "ttl_seconds": ttl_seconds,
                    },
                )
            self._record(
                "capability.issue",
                issuer,
                "applied",
                {
                    "token_id": token.jti,
                    "fingerprint": self.tokens.fingerprint(encoded),
                    "claims": token.to_payload(),
                    "bearer_material_logged": False,
                },
            )
            return encoded

    def revoke_capability(
        self,
        token_id: str,
        *,
        actor: str,
        reason: str = "explicit_emitter_command",
        authority_proof: object | None = None,
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            if not isinstance(token_id, str) or not token_id:
                raise ValueError("token_id must be a non-empty string")
            if not isinstance(reason, str):
                raise TypeError("revocation reason must be a string")
            if not self._is_emitter(actor, "capability.revoke", authority_proof):
                self._reject(
                    "capability.revoke",
                    actor,
                    RuntimeViolation(
                        "AUTHORITY", "only the designated emitter may explicitly revoke"
                    ),
                    {"token_id": token_id},
                )
            existed = self.tokens.revoke(self.state, token_id)
            audit_hash = self._record(
                "capability.revoke",
                actor,
                "applied",
                {"token_id": token_id, "was_active": existed, "reason": reason},
            )
            return self._result("revoke_capability", existed, audit_hash)

    def expire_capabilities(
        self,
        *,
        actor: str = "capability-monitor",
        sensor_proof: object | None = None,
    ) -> list[str]:
        with self._lock:
            self._prevalidate_actor(actor)
            if not self._sensor_attested(actor, "capability.expire", sensor_proof):
                self._reject(
                    "capability.expire",
                    actor,
                    RuntimeViolation(
                        "SENSOR_AUTHORITY",
                        "host did not attest the capability expiration monitor",
                    ),
                    {"proof_logged": False},
                )
            current = epoch_seconds(self._clock())
            expired: list[str] = []
            for token_id, descriptor in list(self.state.A.active_tokens.items()):
                try:
                    token = CapabilityToken.from_payload(descriptor["claims"])
                except (KeyError, TypeError, TokenValidationError):
                    token = None
                if token is None or current >= token.expires_at:
                    self.tokens.revoke(self.state, token_id)
                    expired.append(token_id)
            self._record(
                "capability.expire",
                actor,
                "applied",
                {"expired_token_ids": expired, "at": current},
            )
            return expired

    def execute(self, action: Action) -> TransitionResult:
        with self._lock:
            try:
                canonical_json(action.to_dict(include_token=False))
            except (TypeError, ValueError) as exc:
                self._reject(
                    "action.denied",
                    action.actor,
                    RuntimeViolation(
                        "ACTION_JSON", "action payload is not canonical-JSON safe"
                    ),
                    {"serialization_error": str(exc)},
                )
            if action.kind is ActionType.ACTIVATE_SCOPE:
                return self.activate_scope(
                    str(action.payload.get("scope", "")),
                    membrane=action.payload.get("membrane", "A1"),
                    actor=action.actor,
                )
            if action.kind is ActionType.DEACTIVATE_SCOPE:
                return self.deactivate_scope(
                    actor=action.actor,
                    reason=str(action.payload.get("reason", "scope_end")),
                )
            if action.kind is ActionType.RESOLVE:
                return self.resolve(
                    reason=str(action.payload.get("reason", "unspecified")),
                    affected_layers=action.payload.get("affected_layers", []),
                    actor=action.actor,
                )
            if action.kind is ActionType.RECOVER:
                return self.recover(
                    rebuild=action.payload.get("rebuild", {}),
                    actor=action.actor,
                    authority_proof=action.payload.get("authority_proof"),
                )
            if action.kind is ActionType.KILL:
                return self.kill(
                    reason=str(action.payload.get("reason", "unspecified")),
                    actor=action.actor,
                    mass_revoke=bool(action.payload.get("mass_revoke", False)),
                    authority_proof=action.payload.get("authority_proof"),
                    sensor_proof=action.payload.get("sensor_proof"),
                )

            self._require_active(action.actor, "action.denied")

            # read_down and export are observations rather than productive writes.
            if action.kind is ActionType.READ_DOWN:
                return self._read_down(action)
            if action.kind is ActionType.EXPORT:
                audit_hash = self._record(
                    "action.export",
                    action.actor,
                    "applied",
                    {"action": action.to_dict(include_token=False)},
                )
                return self._result(action.kind, self.export(), audit_hash)

            self._productive_guards(action)
            if action.kind is ActionType.PROJECT:
                return self._project(action)
            if action.kind is ActionType.WRITE_LOCAL:
                return self._write_local(action)
            if action.kind is ActionType.TRANSITION_UP:
                return self._transition_up(action)
            if action.kind is ActionType.ALLOCATE:
                audit_hash = self._record(
                    "action.allocate",
                    action.actor,
                    "applied",
                    {"action": action.to_dict(include_token=False)},
                )
                return self._result(
                    action.kind, copy.deepcopy(dict(action.payload)), audit_hash
                )
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation("ACTION", f"unsupported action: {action.kind.value}"),
            )
            raise AssertionError("unreachable")

    def _project(self, action: Action) -> TransitionResult:
        if action.layer_src is not None or action.layer_dst is None:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation(
                    "PROJECT_PATH", "project requires layer_dst and no layer_src"
                ),
                {"action": action.to_dict(include_token=False)},
            )
        assert action.layer_dst is not None
        if action.layer_dst.value in self.state.A.frozen_layers:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation("FROZEN_LAYER", "destination layer is frozen"),
            )
        value = copy.deepcopy(action.payload.get("value"))
        self.state.H.layers[action.layer_dst.value] = value
        audit_hash = self._record(
            "action.project",
            action.actor,
            "applied",
            {"action": action.to_dict(include_token=False)},
        )
        return self._result(action.kind, value, audit_hash)

    def _write_local(self, action: Action) -> TransitionResult:
        if action.layer_src is None or action.layer_dst is None:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation("WRITE_PATH", "write_local requires both layers"),
            )
        assert action.layer_src is not None and action.layer_dst is not None
        allowed = is_write_allowed(
            state=self.state,
            layer_src=action.layer_src,
            layer_dst=action.layer_dst,
        )
        if not allowed:
            code = (
                "S4_RECOVERY_PATH"
                if action.layer_dst.index < action.layer_src.index
                else "WRITE_RULE"
            )
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation(code, "frozen v1 write_rule rejected the write"),
                {"action": action.to_dict(include_token=False)},
            )
        if action.layer_dst.value in self.state.A.frozen_layers:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation("FROZEN_LAYER", "destination layer is frozen"),
            )
        value = copy.deepcopy(action.payload.get("value"))
        self.state.H.layers[action.layer_dst.value] = value
        audit_hash = self._record(
            "action.write_local",
            action.actor,
            "applied",
            {"action": action.to_dict(include_token=False)},
        )
        return self._result(action.kind, value, audit_hash)

    def _transition_up(self, action: Action) -> TransitionResult:
        if action.layer_src is None or action.layer_dst is None:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation(
                    "S2_CAPABILITY", "transition_up requires source and destination"
                ),
            )
        assert action.layer_src is not None and action.layer_dst is not None
        if action.layer_dst.index != action.layer_src.index + 1:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation(
                    "STRICT_ORDER", "transition_up must move exactly one layer"
                ),
                {"action": action.to_dict(include_token=False)},
            )
        if not action.token:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation(
                    "S2_CAPABILITY", "cross-layer transition requires a capability"
                ),
                {"action": action.to_dict(include_token=False)},
            )
        if not self._principal_attested(action.actor, action.principal_proof):
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation(
                    "PRINCIPAL_AUTHORITY",
                    "host did not attest the capability subject",
                ),
                {
                    "action": action.to_dict(include_token=False),
                    "proof_logged": False,
                },
            )
        try:
            token = self.tokens.validate(
                self.state,
                action.token,
                subject=action.actor,
                layer_src=action.layer_src,
                layer_dst=action.layer_dst,
                action=action.kind,
                now=self._clock(),
            )
        except TokenValidationError as exc:
            claimed_token_id = self.tokens.token_id_without_trust(action.token)
            token_id = None
            if claimed_token_id:
                descriptor = self.state.A.active_tokens.get(claimed_token_id)
                if (
                    isinstance(descriptor, dict)
                    and descriptor.get("fingerprint")
                    == self.tokens.fingerprint(action.token)
                ):
                    token_id = claimed_token_id
                    self.tokens.revoke(self.state, token_id)
            self._reject(
                "action.denied",
                action.actor,
                exc,
                {
                    "action": action.to_dict(include_token=False),
                    "quarantined_token_id": token_id,
                    "untrusted_claimed_token_id": claimed_token_id,
                },
            )
        allowed = is_write_allowed(
            state=self.state,
            layer_src=action.layer_src,
            layer_dst=action.layer_dst,
            valid_capability=True,
        )
        if not allowed:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation("WRITE_RULE", "frozen v1 write_rule rejected transition"),
            )
        if action.layer_dst.value in self.state.A.frozen_layers:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation("FROZEN_LAYER", "destination layer is frozen"),
            )
        value = copy.deepcopy(action.payload.get("value"))
        self.state.H.layers[action.layer_dst.value] = value
        self.tokens.consume(self.state, token)
        audit_hash = self._record(
            "action.transition_up",
            action.actor,
            "applied",
            {
                "action": action.to_dict(include_token=False),
                "consumed_token_id": token.jti,
                "consumed_nonce": token.nonce,
            },
        )
        return self._result(action.kind, value, audit_hash)

    def _read_down(self, action: Action) -> TransitionResult:
        if action.layer_src is None or action.layer_dst is None:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation("READ_PATH", "read_down requires both layers"),
            )
        assert action.layer_src is not None and action.layer_dst is not None
        if action.layer_dst.index != action.layer_src.index - 1:
            self._reject(
                "action.denied",
                action.actor,
                RuntimeViolation("READ_PATH", "read_down moves exactly one layer"),
            )
        value = copy.deepcopy(self.state.H.layers[action.layer_dst.value])
        audit_hash = self._record(
            "action.read_down",
            action.actor,
            "applied",
            {"action": action.to_dict(include_token=False), "read_value": value},
        )
        return self._result(action.kind, value, audit_hash)

    def resolve(
        self,
        *,
        reason: str,
        affected_layers: Any = (),
        actor: str = "conflict-resolver",
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            if not isinstance(reason, str):
                raise TypeError("resolution reason must be a string")
            self._require_active(actor, "fallback.resolve")
            try:
                layers = [Layer.parse(layer) for layer in affected_layers]
            except (TypeError, ValueError) as exc:
                self._reject(
                    "fallback.resolve",
                    actor,
                    RuntimeViolation("RESOLVE_LAYERS", "invalid affected layer list"),
                )
                raise AssertionError("unreachable") from exc
            parsed = [layer for layer in layers if layer is not None]
            winner = None
            if parsed:
                winner = max(parsed, key=lambda layer: HIERARCHY_WEIGHTS[layer.value])
                for layer in parsed:
                    if layer.value not in self.state.A.frozen_layers:
                        self.state.A.frozen_layers.append(layer.value)
            resolution = {
                "reason": reason,
                "strategy": "authorship_lock_then_layer_weight_then_lower_recompute",
                "affected_layers": [layer.value for layer in parsed],
                "winner": winner.value if winner else None,
                "attempt": 1,
            }
            self.state.M.last_resolution = resolution
            audit_hash = self._record(
                "fallback.resolve", actor, "applied", resolution
            )
            return self._result(ActionType.RESOLVE, resolution, audit_hash)

    def release_resolution_lock(
        self, *, actor: str = "integrity-guard"
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            self._require_active(actor, "fallback.resolve.release")
            if not self.state.H.health.healthy:
                self._reject(
                    "fallback.resolve.release",
                    actor,
                    RuntimeViolation(
                        "S1_HEALTH", "integrity check cannot release locks"
                    ),
                )
            released = list(self.state.A.frozen_layers)
            self.state.A.frozen_layers = []
            audit_hash = self._record(
                "fallback.resolve.release",
                actor,
                "applied",
                {"released_layers": released},
            )
            return self._result("release_resolution_lock", released, audit_hash)

    def _apply_recovery(self, rebuild: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(rebuild) - set(LAYER_ORDER)
        if unknown:
            raise RuntimeViolation(
                "RECOVERY_LAYER", "rebuild contains unknown layers", layers=sorted(unknown)
            )
        binary = copy.deepcopy(rebuild.get("binary", self.state.H.layers["binary"]))
        if binary is None:
            raise RuntimeViolation(
                "RECOVERY_BINARY", "progressive recovery requires a binary base"
            )
        gap_seen = False
        for layer in LAYER_ORDER[1:]:
            if layer not in rebuild:
                gap_seen = True
            elif gap_seen:
                raise RuntimeViolation(
                    "RECOVERY_ORDER",
                    "progressive rebuild cannot skip an intermediate layer",
                    layer=layer,
                )
        self.tokens.revoke_all(self.state)
        self.state.H.layers = {layer: None for layer in LAYER_ORDER}
        self.state.H.layers["binary"] = binary
        rebuilt = ["binary"]
        for layer in LAYER_ORDER[1:]:
            if layer not in rebuild:
                break
            self.state.H.layers[layer] = copy.deepcopy(rebuild[layer])
            rebuilt.append(layer)
        self.state.A.frozen_layers = [
            layer for layer in LAYER_ORDER if layer not in rebuilt
        ]
        self.state.M.recovery_generation += 1
        return {"rebuilt_layers": rebuilt, "frozen_layers": self.state.A.frozen_layers}

    def recover(
        self,
        *,
        rebuild: Mapping[str, Any],
        actor: str,
        authority_proof: object | None = None,
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            if not isinstance(rebuild, Mapping):
                raise TypeError("rebuild must be a mapping")
            try:
                canonical_json(rebuild)
            except (TypeError, ValueError) as exc:
                self._reject(
                    "fallback.recover",
                    actor,
                    RuntimeViolation(
                        "RECOVERY_JSON", "rebuild is not canonical-JSON safe"
                    ),
                    {"serialization_error": str(exc)},
                )
            if not self._is_emitter(actor, "recover", authority_proof):
                self._reject(
                    "fallback.recover",
                    actor,
                    RuntimeViolation(
                        "AUTHORITY", "recovery requires the designated emitter"
                    ),
                )
            if not self.state.H.health.healthy:
                self._reject(
                    "fallback.recover",
                    actor,
                    RuntimeViolation(
                        "S1_HEALTH", "recovery health-authority gate failed"
                    ),
                )
            try:
                result = self._apply_recovery(rebuild)
            except RuntimeViolation as exc:
                self._reject("fallback.recover", actor, exc)
            audit_hash = self._record(
                "fallback.recover",
                actor,
                "applied",
                {**result, "recovery_path": True},
            )
            return self._result(ActionType.RECOVER, result, audit_hash)

    def kill(
        self,
        *,
        reason: str,
        actor: str,
        mass_revoke: bool = False,
        authority_proof: object | None = None,
        sensor_proof: object | None = None,
    ) -> TransitionResult:
        with self._lock:
            self._prevalidate_actor(actor)
            if not isinstance(reason, str):
                raise TypeError("kill reason must be a string")
            if not isinstance(mass_revoke, bool):
                raise TypeError("mass_revoke must be a boolean")
            health_trigger = (
                self.state.H.health.forme4_score < CRITICAL_THRESHOLD
                or self.state.H.health.anomaly_rate > 0.75
            ) and self._sensor_attested(actor, "kill.health_trigger", sensor_proof)
            mass_revoke_trigger = mass_revoke and self._sensor_attested(
                actor, "kill.mass_revoke", sensor_proof
            )
            trigger_allowed = (
                self._is_emitter(actor, "kill", authority_proof)
                or health_trigger
                or mass_revoke_trigger
            )
            if not trigger_allowed:
                self._reject(
                    "fallback.kill",
                    actor,
                    RuntimeViolation(
                        "KILL_AUTHORITY", "no canonical kill trigger is present"
                    ),
                )
            revoked = self.tokens.revoke_all(self.state)
            previous_scope = self.state.A.scope
            self.state.A.scope = None
            self.state.A.membrane = MembraneLevel.A0_DORMANT
            self.state.A.lifecycle = LifecycleStatus.KILLED
            self.state.A.frozen_layers = list(LAYER_ORDER)
            audit_hash = self._record(
                "fallback.kill",
                actor,
                "applied",
                {
                    "reason": reason,
                    "previous_scope": previous_scope,
                    "revoked_token_ids": revoked,
                    "quarantine": True,
                },
            )
            return self._result(ActionType.KILL, None, audit_hash)

    def resume_after_kill(
        self,
        *,
        scope: str,
        rebuild: Mapping[str, Any],
        actor: str,
        membrane: MembraneLevel | int | str = MembraneLevel.A2_CRITICAL,
        explicit_confirmation: bool = False,
        authority_proof: object | None = None,
    ) -> TransitionResult:
        with self._lock:
            # Preflight is deliberately side-effect free.  A rejected resume is
            # not an LTS transition and therefore does not append an audit event.
            self._prevalidate_actor(actor)
            if not isinstance(scope, str) or not scope.strip():
                raise RuntimeViolation(
                    "SCOPE", "resume requires a non-empty scope"
                )
            level = MembraneLevel.parse(membrane)
            if level is MembraneLevel.A0_DORMANT:
                raise RuntimeViolation(
                    "SCOPE", "resume requires an active membrane A1-A3"
                )
            if not isinstance(explicit_confirmation, bool):
                raise TypeError("explicit_confirmation must be a boolean")
            if not isinstance(rebuild, Mapping) or set(rebuild) != set(LAYER_ORDER):
                raise RuntimeViolation(
                    "RECOVERY_INCOMPLETE",
                    "resume requires a complete progressive rebuild",
                )
            try:
                canonical_json(rebuild)
            except (TypeError, ValueError) as exc:
                raise RuntimeViolation(
                    "RECOVERY_JSON",
                    "rebuild is not canonical-JSON safe",
                    serialization_error=str(exc),
                ) from exc
            if self.state.A.lifecycle is not LifecycleStatus.KILLED:
                raise RuntimeViolation(
                    "NOT_KILLED", "runtime is not in killed state"
                )
            if not self.state.A.known_m3c3:
                raise RuntimeViolation(
                    "S5_UNKNOWN", "unknown runtime cannot resume active"
                )
            if self.state.A.opted_out:
                raise RuntimeViolation("OPTED_OUT", "opt-out blocks resume")
            if not explicit_confirmation or not self._is_emitter(
                actor, "resume", authority_proof
            ):
                raise RuntimeViolation(
                    "RESUME_AUTHORITY",
                    "resume requires explicit designated-emitter confirmation",
                )
            if not self.state.H.health.healthy:
                raise RuntimeViolation("S1_HEALTH", "resume health gate failed")
            recovery = self._apply_recovery(rebuild)
            self.state.A.scope = scope.strip()
            self.state.A.membrane = level
            self.state.A.lifecycle = LifecycleStatus.ACTIVE
            self.state.A.frozen_layers = []
            audit_hash = self._record(
                "lifecycle.resume",
                actor,
                "applied",
                {
                    "scope": scope.strip(),
                    "membrane": level.label,
                    "explicit_confirmation": True,
                    **recovery,
                },
            )
            return self._result("resume_after_kill", recovery, audit_hash)

    def export(self) -> dict[str, object]:
        with self._lock:
            invariants = canonical_invariants()
            exported = {
                "schema_version": EXPORT_SCHEMA_VERSION,
                "runtime_version": RUNTIME_VERSION,
                "kernel_version": KERNEL_VERSION,
                "state_symbol": "S_t = (H_t, R_t, E_t, A_t, M_t)",
                "state": self.state.to_dict(),
                "kernel_invariants_digest": state_digest(invariants),
                "audit": {
                    "head": self.audit.head,
                    "length": self.audit.length,
                    "verified": self.audit.verify(),
                },
            }
            validate_export(exported)
            return exported

    def export_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.export(), ensure_ascii=False, sort_keys=True, indent=indent, allow_nan=False
        )

    def save_export(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.export_json() + "\n", encoding="utf-8")
        return destination

    def _result(
        self, action: ActionType | str, value: Any, audit_hash: str
    ) -> TransitionResult:
        label = action.value if isinstance(action, ActionType) else str(action)
        return TransitionResult(
            action=label,
            outcome="applied",
            value=copy.deepcopy(value),
            state_digest=self.state.semantic_digest(),
            audit_hash=audit_hash,
        )
