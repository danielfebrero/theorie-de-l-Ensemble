"""Typed failures returned by the M3C3 policy machine."""

from __future__ import annotations


class M3C3Error(Exception):
    """Base class for runtime errors."""


class RuntimeViolation(M3C3Error):
    """A transition was rejected by a named invariant or runtime guard."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"code": self.code, "message": self.message}
        if self.details:
            result["details"] = self.details
        return result


class AuditIntegrityError(M3C3Error):
    """An audit chain, entry hash, or protected state digest is invalid."""


class SchemaValidationError(M3C3Error):
    """A state, event, or export violates its versioned JSON contract."""


class TokenValidationError(RuntimeViolation):
    """A capability token is malformed, invalid, expired, or out of scope."""
