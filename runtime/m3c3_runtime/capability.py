"""Signed, scoped, expirable, revocable, single-use capability tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .constants import (
    DEFAULT_TOKEN_TTL_SECONDS,
    DESIGNATED_EMITTER_ALIASES,
    MAX_TOKEN_TTL_SECONDS,
)
from .errors import TokenValidationError
from .model import ActionType, AuthorityState, Layer, M3C3State, canonical_json

TOKEN_SCHEMA_VERSION = "m3c3.capability/v2"


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise TokenValidationError("CAP_MALFORMED", "malformed base64url token") from exc


def epoch_seconds(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.astimezone(timezone.utc).timestamp())


@dataclass(frozen=True)
class CapabilityToken:
    schema_version: str
    jti: str
    issuer: str
    subject: str
    scope: str
    layer_src: str
    layer_dst: str
    action: str
    issued_at: int
    expires_at: int
    nonce: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "jti": self.jti,
            "issuer": self.issuer,
            "subject": self.subject,
            "scope": self.scope,
            "layer_src": self.layer_src,
            "layer_dst": self.layer_dst,
            "action": self.action,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> "CapabilityToken":
        required = {
            "schema_version",
            "jti",
            "issuer",
            "subject",
            "scope",
            "layer_src",
            "layer_dst",
            "action",
            "issued_at",
            "expires_at",
            "nonce",
        }
        actual = set(value)
        missing = required - actual
        unexpected = actual - required
        if missing or unexpected:
            raise TokenValidationError(
                "CAP_MALFORMED",
                "capability payload fields do not match the schema",
                missing=sorted(missing),
                unexpected=sorted(unexpected),
            )
        string_fields = (
            "schema_version",
            "jti",
            "issuer",
            "subject",
            "scope",
            "layer_src",
            "layer_dst",
            "action",
            "nonce",
        )
        if any(not isinstance(value[field], str) for field in string_fields):
            raise TokenValidationError(
                "CAP_MALFORMED", "capability string claims must be strings"
            )
        if any(not value[field] for field in ("jti", "subject", "scope", "nonce")):
            raise TokenValidationError(
                "CAP_MALFORMED", "capability identity claims cannot be empty"
            )
        for field in ("issued_at", "expires_at"):
            if isinstance(value[field], bool) or not isinstance(value[field], int):
                raise TokenValidationError(
                    "CAP_MALFORMED", "capability time claims must be integers"
                )
        try:
            token = cls(
                schema_version=value["schema_version"],
                jti=value["jti"],
                issuer=value["issuer"],
                subject=value["subject"],
                scope=value["scope"],
                layer_src=value["layer_src"],
                layer_dst=value["layer_dst"],
                action=value["action"],
                issued_at=value["issued_at"],
                expires_at=value["expires_at"],
                nonce=value["nonce"],
            )
            Layer(token.layer_src)
            Layer(token.layer_dst)
            ActionType(token.action)
        except (TypeError, ValueError) as exc:
            raise TokenValidationError(
                "CAP_MALFORMED", "capability payload contains invalid values"
            ) from exc
        if token.schema_version != TOKEN_SCHEMA_VERSION:
            raise TokenValidationError(
                "CAP_VERSION", "unsupported capability schema version"
            )
        if token.issuer not in DESIGNATED_EMITTER_ALIASES:
            raise TokenValidationError("CAP_ISSUER", "issuer is not designated")
        if token.action != ActionType.TRANSITION_UP.value:
            raise TokenValidationError("CAP_ACTION", "unsupported capability action")
        if Layer(token.layer_dst).index != Layer(token.layer_src).index + 1:
            raise TokenValidationError("CAP_PATH", "capability path is not adjacent upward")
        ttl = token.expires_at - token.issued_at
        if token.issued_at < 0 or not 1 <= ttl <= MAX_TOKEN_TTL_SECONDS:
            raise TokenValidationError("CAP_TIME", "invalid capability validity window")
        return token


class CapabilityTokenManager:
    def __init__(self, signing_key: bytes) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("signing_key must contain at least 32 bytes")
        self._key = signing_key

    def _signature(self, encoded_payload: str) -> str:
        digest = hmac.new(
            self._key, encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        return _b64url_encode(digest)

    def encode(self, token: CapabilityToken) -> str:
        payload = _b64url_encode(canonical_json(token.to_payload()).encode("utf-8"))
        return f"{payload}.{self._signature(payload)}"

    @staticmethod
    def fingerprint(encoded: str) -> str:
        return hashlib.sha256(encoded.encode("ascii")).hexdigest()

    def decode(self, encoded: str, *, verify_signature: bool = True) -> CapabilityToken:
        if not isinstance(encoded, str) or encoded.count(".") != 1:
            raise TokenValidationError("CAP_MALFORMED", "malformed capability token")
        payload_part, signature = encoded.split(".", 1)
        if verify_signature and not hmac.compare_digest(
            signature, self._signature(payload_part)
        ):
            raise TokenValidationError("CAP_SIGNATURE", "invalid capability signature")
        try:
            payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TokenValidationError(
                "CAP_MALFORMED", "capability payload is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise TokenValidationError(
                "CAP_MALFORMED", "capability payload must be an object"
            )
        return CapabilityToken.from_payload(payload)

    def issue(
        self,
        state: M3C3State,
        *,
        issuer: str,
        subject: str,
        layer_src: Layer,
        layer_dst: Layer,
        action: ActionType = ActionType.TRANSITION_UP,
        ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
        now: datetime,
        nonce: str | None = None,
        token_id: str | None = None,
    ) -> tuple[str, CapabilityToken]:
        if issuer not in DESIGNATED_EMITTER_ALIASES:
            raise TokenValidationError(
                "CAP_ISSUER", "only the designated emitter may issue capabilities"
            )
        if not isinstance(subject, str) or not subject:
            raise TokenValidationError(
                "CAP_SUBJECT", "capability subject must be a non-empty string"
            )
        if not state.A.active or not state.A.scope:
            raise TokenValidationError(
                "CAP_SCOPE", "a capability requires an active scope"
            )
        if not state.H.health.healthy:
            raise TokenValidationError(
                "S1_HEALTH", "forme4 health gate rejected capability issuance"
            )
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
            raise TokenValidationError("CAP_TTL", "ttl_seconds must be an integer")
        if not 1 <= ttl_seconds <= MAX_TOKEN_TTL_SECONDS:
            raise TokenValidationError(
                "CAP_TTL",
                f"ttl_seconds must be in [1, {MAX_TOKEN_TTL_SECONDS}]",
            )
        if layer_dst.index != layer_src.index + 1:
            raise TokenValidationError(
                "CAP_PATH", "capabilities only authorize one adjacent upward step"
            )
        if action is not ActionType.TRANSITION_UP:
            raise TokenValidationError(
                "CAP_ACTION", "cross-layer capabilities are bound to transition_up"
            )
        nonce = nonce or secrets.token_urlsafe(18)
        token_id = token_id or secrets.token_urlsafe(18)
        if not isinstance(nonce, str) or not nonce or nonce in state.A.issued_nonces:
            raise TokenValidationError("CAP_NONCE", "nonce is empty or already issued")
        if (
            not isinstance(token_id, str)
            or not token_id
            or token_id in state.A.active_tokens
        ):
            raise TokenValidationError("CAP_ID", "token id is empty or already active")
        issued_at = epoch_seconds(now)
        token = CapabilityToken(
            schema_version=TOKEN_SCHEMA_VERSION,
            jti=token_id,
            issuer=issuer,
            subject=subject,
            scope=state.A.scope,
            layer_src=layer_src.value,
            layer_dst=layer_dst.value,
            action=action.value,
            issued_at=issued_at,
            expires_at=issued_at + ttl_seconds,
            nonce=nonce,
        )
        encoded = self.encode(token)
        state.A.active_tokens[token.jti] = {
            "fingerprint": self.fingerprint(encoded),
            "claims": token.to_payload(),
        }
        state.A.issued_nonces.append(token.nonce)
        return encoded, token

    def validate(
        self,
        state: M3C3State,
        encoded: str,
        *,
        subject: str,
        layer_src: Layer,
        layer_dst: Layer,
        action: ActionType,
        now: datetime,
    ) -> CapabilityToken:
        token = self.decode(encoded)
        current = epoch_seconds(now)
        descriptor = state.A.active_tokens.get(token.jti)
        descriptor_matches = bool(
            isinstance(descriptor, dict)
            and descriptor.get("fingerprint") == self.fingerprint(encoded)
            and descriptor.get("claims") == token.to_payload()
        )
        checks: tuple[tuple[bool, str, str], ...] = (
            (token.jti not in state.A.revoked_token_ids, "CAP_REVOKED", "token revoked"),
            (
                descriptor_matches,
                "CAP_INACTIVE",
                "token is not active or its descriptor does not match",
            ),
            (token.nonce not in state.A.consumed_nonces, "CAP_REPLAY", "nonce reused"),
            (token.issued_at <= current, "CAP_IAT", "token is not valid yet"),
            (current < token.expires_at, "CAP_EXPIRED", "token expired"),
            (token.scope == state.A.scope, "CAP_SCOPE", "token scope mismatch"),
            (token.subject == subject, "CAP_SUBJECT", "token subject mismatch"),
            (
                token.layer_src == layer_src.value,
                "CAP_SOURCE",
                "token source layer mismatch",
            ),
            (
                token.layer_dst == layer_dst.value,
                "CAP_DESTINATION",
                "token destination layer mismatch",
            ),
            (token.action == action.value, "CAP_ACTION", "token action mismatch"),
            (state.H.health.healthy, "S1_HEALTH", "forme4 health gate failed"),
        )
        for passed, code, message in checks:
            if not passed:
                raise TokenValidationError(code, message, token_id=token.jti)
        return token

    @staticmethod
    def consume(state: M3C3State, token: CapabilityToken) -> None:
        state.A.active_tokens.pop(token.jti, None)
        if token.nonce not in state.A.consumed_nonces:
            state.A.consumed_nonces.append(token.nonce)

    @staticmethod
    def revoke(state: M3C3State, token_id: str) -> bool:
        existed = token_id in state.A.active_tokens
        state.A.active_tokens.pop(token_id, None)
        if token_id not in state.A.revoked_token_ids:
            state.A.revoked_token_ids.append(token_id)
        return existed

    @staticmethod
    def revoke_all(state: M3C3State) -> list[str]:
        token_ids = sorted(state.A.active_tokens)
        for token_id in token_ids:
            CapabilityTokenManager.revoke(state, token_id)
        return token_ids

    def token_id_without_trust(self, encoded: str) -> str | None:
        """Extract a jti only to quarantine an invalid token; never authorizes it."""

        try:
            return self.decode(encoded, verify_signature=False).jti
        except TokenValidationError:
            return None
