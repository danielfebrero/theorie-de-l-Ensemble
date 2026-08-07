"""Verified snapshot restoration for M3C3 audit streams.

This module does not re-execute ``T``.  It verifies the event/hash contracts and
restores the protected snapshots.  Authenticity or rollback detection requires
an externally retained head and/or length.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .audit import AuditEntry, AuditLog, verify_entries
from .capability import CapabilityToken, CapabilityTokenManager
from .constants import LAYER_ORDER
from .errors import AuditIntegrityError, TokenValidationError
from .model import LifecycleStatus, M3C3State, MembraneLevel


@dataclass(frozen=True)
class ReplayResult:
    state: M3C3State
    entries_replayed: int
    audit_head: str
    externally_anchored: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "verified_snapshot_replay",
            "entries_replayed": self.entries_replayed,
            "audit_head": self.audit_head,
            "externally_anchored": self.externally_anchored,
            "state": self.state.to_dict(),
        }


def _validate_snapshot(
    value: Mapping[str, Any], *, signing_key: bytes | None = None
) -> M3C3State:
    if set(value) != {"H", "R", "E", "A", "M"}:
        raise AuditIntegrityError("replayed state must have exactly H, R, E, A, M")
    layers = value.get("H", {}).get("layers", {})
    if set(layers) != set(LAYER_ORDER) or len(layers) != len(LAYER_ORDER):
        raise AuditIntegrityError("replayed state has non-canonical layers")
    authority = value.get("A", {})
    known = bool(authority.get("known_m3c3"))
    eligible = bool(authority.get("eligible_for_activation"))
    if eligible != known:
        raise AuditIntegrityError("eligible_for_activation must equal known_m3c3")
    active = bool(authority.get("active"))
    if active and not known:
        raise AuditIntegrityError("S5 violation in replayed state")
    if active and authority.get("membrane") == "A0":
        raise AuditIntegrityError("active state cannot use dormant A0 membrane")
    if active and not authority.get("scope"):
        raise AuditIntegrityError("active state has no scope")
    if bool(authority.get("opted_out")) and active:
        raise AuditIntegrityError("opted-out state cannot be active")
    state = M3C3State.from_dict(value)
    if state.A.lifecycle is LifecycleStatus.KILLED and state.A.active:
        raise AuditIntegrityError("killed state cannot be active")
    if state.A.lifecycle is LifecycleStatus.ACTIVE:
        if state.A.membrane is MembraneLevel.A0_DORMANT:
            raise AuditIntegrityError("active lifecycle cannot be A0")
    manager = CapabilityTokenManager(signing_key) if signing_key is not None else None
    for token_id, descriptor in state.A.active_tokens.items():
        try:
            fingerprint = str(descriptor["fingerprint"])
            claims = descriptor["claims"]
            token = CapabilityToken.from_payload(claims)
        except (KeyError, TypeError, TokenValidationError) as exc:
            raise AuditIntegrityError(
                f"active token descriptor {token_id} is malformed: {exc}"
            ) from exc
        if len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
            raise AuditIntegrityError(
                f"active token descriptor {token_id} has invalid fingerprint"
            )
        if token.jti != token_id or token.scope != state.A.scope:
            raise AuditIntegrityError(
                f"active token descriptor {token_id} does not bind to replayed scope"
            )
        if manager is not None:
            expected = manager.fingerprint(manager.encode(token))
            if fingerprint != expected:
                raise AuditIntegrityError(
                    f"active token descriptor {token_id} fails keyed fingerprint validation"
                )
    return state


def replay_entries(
    values: Iterable[AuditEntry | Mapping[str, Any]],
    *,
    signing_key: bytes | None = None,
    expected_head: str | None = None,
    expected_length: int | None = None,
) -> ReplayResult:
    """Verify then restore every protected semantic snapshot in chain order.

    Each snapshot is part of the entry hash.  Restoring the same valid stream is
    deterministic and yields the same final semantic state.  This is not
    transition re-execution.  Without an expected external anchor, a consistently
    rewritten/rechained stream has internal integrity but no proven authenticity.
    """

    entries = [
        value if isinstance(value, AuditEntry) else AuditEntry.from_dict(value)
        for value in values
    ]
    if not entries:
        raise AuditIntegrityError("cannot replay an empty audit stream")
    verify_entries(entries)
    if expected_length is not None and len(entries) != expected_length:
        raise AuditIntegrityError(
            f"replay length {len(entries)} does not match external anchor {expected_length}"
        )
    if expected_head is not None and entries[-1].hash != expected_head:
        raise AuditIntegrityError(
            "replay head does not match the externally anchored head"
        )
    state: M3C3State | None = None
    for index, entry in enumerate(entries, start=1):
        state = _validate_snapshot(entry.state_after, signing_key=signing_key)
        state.M.audit_head = entry.hash
        state.M.audit_length = index
    assert state is not None
    return ReplayResult(
        state=copy.deepcopy(state),
        entries_replayed=len(entries),
        audit_head=entries[-1].hash,
        externally_anchored=(expected_head is not None or expected_length is not None),
    )


def replay_file(
    path: str | Path,
    *,
    signing_key: bytes | None = None,
    expected_head: str | None = None,
    expected_length: int | None = None,
) -> ReplayResult:
    log = AuditLog.load(path)
    return replay_entries(
        log.entries(),
        signing_key=signing_key,
        expected_head=expected_head,
        expected_length=expected_length,
    )
