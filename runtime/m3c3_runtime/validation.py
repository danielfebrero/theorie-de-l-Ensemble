"""Dependency-free enforcement for the three runtime JSON contracts.

The JSON Schema files remain the portable contracts.  These targeted validators
enforce the same closed structures at runtime without requiring ``jsonschema``.
"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime
from typing import Any, Mapping

from .capability import CapabilityToken
from .constants import (
    KERNEL_VERSION,
    LAYER_ORDER,
    RUNTIME_VERSION,
    WARNING_THRESHOLD,
    canonical_invariants,
)
from .errors import SchemaValidationError, TokenValidationError
from .model import canonical_json, state_digest


def _fail(path: str, message: str) -> None:
    raise SchemaValidationError(f"{path}: {message}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        _fail(
            path,
            f"fields mismatch (missing={sorted(expected-actual)}, "
            f"unexpected={sorted(actual-expected)})",
        )


def _string(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        _fail(path, "must be a string")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, "must be a boolean")
    return value


def _integer(value: Any, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(path, f"must be an integer >= {minimum}")
    return value


def _number(value: Any, path: str, minimum: float, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < minimum:
        _fail(path, f"must be finite and >= {minimum}")
    if maximum is not None and numeric > maximum:
        _fail(path, f"must be <= {maximum}")
    return numeric


def _hex64(value: Any, path: str) -> str:
    text = _string(value, path)
    assert text is not None
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        _fail(path, "must be 64 lowercase hexadecimal characters")
    return text


def _string_list(value: Any, path: str, *, allowed: set[str] | None = None) -> list[str]:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    if any(not isinstance(item, str) for item in value):
        _fail(path, "must contain only strings")
    if len(value) != len(set(value)):
        _fail(path, "must contain unique values")
    if allowed is not None and not set(value) <= allowed:
        _fail(path, "contains a value outside the allowed domain")
    return value


def validate_state(value: Any, *, audit_meta: bool | None = None) -> None:
    """Validate a full export state or a semantic audit snapshot."""

    try:
        canonical_json(value)
    except (TypeError, ValueError) as exc:
        _fail("$", f"not canonical-JSON serializable: {exc}")
    state = _mapping(value, "$")
    _exact_keys(state, {"H", "R", "E", "A", "M"}, "$")

    hierarchy = _mapping(state["H"], "$.H")
    _exact_keys(hierarchy, {"layers", "health"}, "$.H")
    layers = _mapping(hierarchy["layers"], "$.H.layers")
    _exact_keys(layers, set(LAYER_ORDER), "$.H.layers")
    health = _mapping(hierarchy["health"], "$.H.health")
    _exact_keys(
        health,
        {"integrity_score", "stability_index", "anomaly_rate", "forme4_score", "healthy"},
        "$.H.health",
    )
    integrity = _number(health["integrity_score"], "$.H.health.integrity_score", 0, 1)
    stability = _number(health["stability_index"], "$.H.health.stability_index", 0, 1)
    anomaly = _number(health["anomaly_rate"], "$.H.health.anomaly_rate", 0, 1)
    forme4 = _number(health["forme4_score"], "$.H.health.forme4_score", 0, 1)
    expected_forme4 = min(integrity, stability, 1.0 - anomaly)
    if abs(forme4 - expected_forme4) > 1e-12:
        _fail("$.H.health.forme4_score", "does not match canonical health function")
    if _bool(health["healthy"], "$.H.health.healthy") != (
        forme4 >= WARNING_THRESHOLD
    ):
        _fail("$.H.health.healthy", "does not match warning threshold")

    if state["R"] not in {"quantifiable", "fuzzy", "mixed"}:
        _fail("$.R", "outside regime domain")

    evidence = _mapping(state["E"], "$.E")
    _exact_keys(
        evidence,
        {"score", "tau", "regret_asymmetry", "falsifier", "sufficient"},
        "$.E",
    )
    score = _number(evidence["score"], "$.E.score", 0, 1)
    tau = _number(evidence["tau"], "$.E.tau", 0, 1)
    _number(evidence["regret_asymmetry"], "$.E.regret_asymmetry", 0)
    _string(evidence["falsifier"], "$.E.falsifier", nullable=True)
    if _bool(evidence["sufficient"], "$.E.sufficient") != (score >= tau):
        _fail("$.E.sufficient", "does not match score >= tau")

    authority = _mapping(state["A"], "$.A")
    authority_fields = {
        "known_m3c3",
        "eligible_for_activation",
        "scope",
        "membrane",
        "lifecycle",
        "active",
        "opted_out",
        "emitter",
        "active_tokens",
        "issued_nonces",
        "consumed_nonces",
        "revoked_token_ids",
        "frozen_layers",
    }
    _exact_keys(authority, authority_fields, "$.A")
    known = _bool(authority["known_m3c3"], "$.A.known_m3c3")
    eligible = _bool(authority["eligible_for_activation"], "$.A.eligible_for_activation")
    if eligible != known:
        _fail("$.A.eligible_for_activation", "must equal known_m3c3")
    scope = _string(authority["scope"], "$.A.scope", nullable=True)
    if authority["membrane"] not in {"A0", "A1", "A2", "A3"}:
        _fail("$.A.membrane", "outside membrane domain")
    if authority["lifecycle"] not in {"dormant", "active", "inactive", "killed"}:
        _fail("$.A.lifecycle", "outside lifecycle domain")
    active = _bool(authority["active"], "$.A.active")
    if active != (authority["lifecycle"] == "active"):
        _fail("$.A.active", "must match lifecycle")
    opted_out = _bool(authority["opted_out"], "$.A.opted_out")
    if active and (not known or opted_out or not scope or authority["membrane"] == "A0"):
        _fail("$.A", "active state violates lifecycle/S5/opt-out constraints")
    if authority["lifecycle"] != "active" and (
        scope is not None or authority["membrane"] != "A0"
    ):
        _fail("$.A", "non-active lifecycle must have no scope and dormant membrane")
    if opted_out and (scope is not None or authority["membrane"] != "A0"):
        _fail("$.A", "opt-out must have no scope and dormant membrane")
    if authority["emitter"] != "Dani Bengal":
        _fail("$.A.emitter", "authorship authority changed")
    active_tokens = _mapping(authority["active_tokens"], "$.A.active_tokens")
    for token_id, raw_descriptor in active_tokens.items():
        _string(token_id, "$.A.active_tokens.<id>")
        descriptor = _mapping(raw_descriptor, f"$.A.active_tokens.{token_id}")
        _exact_keys(descriptor, {"fingerprint", "claims"}, f"$.A.active_tokens.{token_id}")
        _hex64(descriptor["fingerprint"], f"$.A.active_tokens.{token_id}.fingerprint")
        try:
            token = CapabilityToken.from_payload(
                _mapping(descriptor["claims"], f"$.A.active_tokens.{token_id}.claims")
            )
        except TokenValidationError as exc:
            _fail(f"$.A.active_tokens.{token_id}.claims", exc.message)
        if token.jti != token_id or token.scope != scope:
            _fail(f"$.A.active_tokens.{token_id}", "claims do not bind to id/scope")
    issued_nonces = _string_list(authority["issued_nonces"], "$.A.issued_nonces")
    consumed_nonces = _string_list(
        authority["consumed_nonces"], "$.A.consumed_nonces"
    )
    revoked_token_ids = _string_list(
        authority["revoked_token_ids"], "$.A.revoked_token_ids"
    )
    if not set(consumed_nonces) <= set(issued_nonces):
        _fail("$.A.consumed_nonces", "must be a subset of issued_nonces")
    if set(active_tokens) & set(revoked_token_ids):
        _fail("$.A.active_tokens", "an active token cannot also be revoked")
    for token_id, descriptor in active_tokens.items():
        nonce = descriptor["claims"]["nonce"]
        if nonce not in issued_nonces or nonce in consumed_nonces:
            _fail(
                f"$.A.active_tokens.{token_id}",
                "active nonce must be issued and not consumed",
            )
    _string_list(
        authority["frozen_layers"], "$.A.frozen_layers", allowed=set(LAYER_ORDER)
    )

    memory = _mapping(state["M"], "$.M")
    semantic_fields = {"last_resolution", "recovery_generation"}
    full_fields = semantic_fields | {"audit_head", "audit_length"}
    if audit_meta is True:
        _exact_keys(memory, full_fields, "$.M")
    elif audit_meta is False:
        _exact_keys(memory, semantic_fields, "$.M")
    elif set(memory) not in (semantic_fields, full_fields):
        _fail("$.M", "must be either semantic or full memory state")
    if memory["last_resolution"] is not None and not isinstance(
        memory["last_resolution"], dict
    ):
        _fail("$.M.last_resolution", "must be object or null")
    _integer(memory["recovery_generation"], "$.M.recovery_generation")
    if "audit_head" in memory:
        _hex64(memory["audit_head"], "$.M.audit_head")
        _integer(memory["audit_length"], "$.M.audit_length")


def validate_event(value: Any) -> None:
    event = _mapping(value, "$")
    expected = {
        "schema_version",
        "sequence",
        "timestamp",
        "event",
        "actor",
        "outcome",
        "data",
        "state_after",
        "state_digest",
        "prev_hash",
        "hash",
    }
    _exact_keys(event, expected, "$")
    if event["schema_version"] != "m3c3.audit-entry/v2":
        _fail("$.schema_version", "unsupported version")
    _integer(event["sequence"], "$.sequence", 1)
    timestamp = _string(event["timestamp"], "$.timestamp")
    assert timestamp is not None
    if "T" not in timestamp or not (
        timestamp.endswith("Z") or re.search(r"[+-]\d{2}:\d{2}$", timestamp)
    ):
        _fail("$.timestamp", "must be RFC3339 date-time with an explicit timezone")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        _fail("$.timestamp", "must be an ISO-8601 date-time")
    if parsed_timestamp.tzinfo is None:
        _fail("$.timestamp", "timezone is required")
    if not _string(event["event"], "$.event"):
        _fail("$.event", "cannot be empty")
    if not _string(event["actor"], "$.actor"):
        _fail("$.actor", "cannot be empty")
    if event["outcome"] not in {"applied", "denied"}:
        _fail("$.outcome", "outside outcome domain")
    _mapping(event["data"], "$.data")
    validate_state(event["state_after"], audit_meta=False)
    digest = _hex64(event["state_digest"], "$.state_digest")
    if digest != state_digest(event["state_after"]):
        _fail("$.state_digest", "does not bind state_after")
    _hex64(event["prev_hash"], "$.prev_hash")
    claimed_hash = _hex64(event["hash"], "$.hash")
    body = {key: item for key, item in event.items() if key != "hash"}
    calculated = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    if claimed_hash != calculated:
        _fail("$.hash", "does not bind the event body")


def validate_export(value: Any) -> None:
    exported = _mapping(value, "$")
    expected = {
        "schema_version",
        "runtime_version",
        "kernel_version",
        "state_symbol",
        "state",
        "kernel_invariants_digest",
        "audit",
    }
    _exact_keys(exported, expected, "$")
    if exported["schema_version"] != "m3c3.state-export/v2":
        _fail("$.schema_version", "unsupported version")
    if exported["runtime_version"] != RUNTIME_VERSION:
        _fail("$.runtime_version", "does not match runtime")
    if exported["kernel_version"] != KERNEL_VERSION:
        _fail("$.kernel_version", "does not match frozen kernel")
    if exported["state_symbol"] != "S_t = (H_t, R_t, E_t, A_t, M_t)":
        _fail("$.state_symbol", "canonical state tuple changed")
    validate_state(exported["state"], audit_meta=True)
    invariant_digest = _hex64(
        exported["kernel_invariants_digest"], "$.kernel_invariants_digest"
    )
    if invariant_digest != state_digest(canonical_invariants()):
        _fail("$.kernel_invariants_digest", "frozen invariant digest mismatch")
    audit = _mapping(exported["audit"], "$.audit")
    _exact_keys(audit, {"head", "length", "verified"}, "$.audit")
    head = _hex64(audit["head"], "$.audit.head")
    length = _integer(audit["length"], "$.audit.length", 1)
    if _bool(audit["verified"], "$.audit.verified") is not True:
        _fail("$.audit.verified", "must be true")
    memory = exported["state"]["M"]
    if memory["audit_head"] != head or memory["audit_length"] != length:
        _fail("$.audit", "does not match state.M audit anchor")
