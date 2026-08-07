"""Append-only, hash-chained audit records for the M3C3 runtime."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .constants import ZERO_HASH
from .errors import AuditIntegrityError, SchemaValidationError
from .model import M3C3State, canonical_json, state_digest
from .validation import validate_event

AUDIT_SCHEMA_VERSION = "m3c3.audit-entry/v2"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class AuditEntry:
    schema_version: str
    sequence: int
    timestamp: str
    event: str
    actor: str
    outcome: str
    data: dict[str, Any]
    state_after: dict[str, Any]
    state_digest: str
    prev_hash: str
    hash: str

    def body(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event": self.event,
            "actor": self.actor,
            "outcome": self.outcome,
            "data": copy.deepcopy(self.data),
            "state_after": copy.deepcopy(self.state_after),
            "state_digest": self.state_digest,
            "prev_hash": self.prev_hash,
        }

    def to_dict(self) -> dict[str, object]:
        result = self.body()
        result["hash"] = self.hash
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AuditEntry":
        required = {
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
        actual = set(value)
        missing = required - actual
        unexpected = actual - required
        if missing or unexpected:
            raise AuditIntegrityError(
                "audit entry fields do not match schema: "
                f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
            )
        return cls(
            schema_version=str(value["schema_version"]),
            sequence=int(value["sequence"]),
            timestamp=str(value["timestamp"]),
            event=str(value["event"]),
            actor=str(value["actor"]),
            outcome=str(value["outcome"]),
            data=copy.deepcopy(dict(value["data"])),
            state_after=copy.deepcopy(dict(value["state_after"])),
            state_digest=str(value["state_digest"]),
            prev_hash=str(value["prev_hash"]),
            hash=str(value["hash"]),
        )


def entry_hash(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def verify_entries(
    values: Iterable[AuditEntry | Mapping[str, Any]], *, raise_on_error: bool = True
) -> bool:
    """Validate ordering, chain links, entry hashes and protected state digests."""

    previous = ZERO_HASH
    try:
        for expected_sequence, raw in enumerate(values, start=1):
            if isinstance(raw, AuditEntry):
                entry = raw
                validate_event(entry.to_dict())
            else:
                validate_event(raw)
                entry = AuditEntry.from_dict(raw)
            if entry.schema_version != AUDIT_SCHEMA_VERSION:
                raise AuditIntegrityError(
                    f"entry {expected_sequence}: unsupported schema {entry.schema_version}"
                )
            if entry.sequence != expected_sequence:
                raise AuditIntegrityError(
                    f"entry {expected_sequence}: sequence is {entry.sequence}"
                )
            if entry.prev_hash != previous:
                raise AuditIntegrityError(
                    f"entry {expected_sequence}: prev_hash does not match chain head"
                )
            calculated_state = state_digest(entry.state_after)
            if calculated_state != entry.state_digest:
                raise AuditIntegrityError(
                    f"entry {expected_sequence}: protected state digest mismatch"
                )
            calculated_entry = entry_hash(entry.body())
            if calculated_entry != entry.hash:
                raise AuditIntegrityError(
                    f"entry {expected_sequence}: audit hash mismatch"
                )
            previous = entry.hash
    except (
        AuditIntegrityError,
        SchemaValidationError,
        TypeError,
        ValueError,
        KeyError,
    ) as exc:
        if raise_on_error:
            if isinstance(exc, AuditIntegrityError):
                raise
            raise AuditIntegrityError(f"malformed audit chain: {exc}") from exc
        return False
    return True


class AuditLog:
    """In-memory chain with optional durable JSONL append sink.

    The class exposes no mutation primitive for existing entries.  When a path is
    supplied, writes use append mode plus fsync.  Integrity remains cryptographic;
    filesystem immutability is a deployment responsibility.
    """

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
        require_empty: bool = True,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self.clock = clock
        self._entries: list[AuditEntry] = []
        self._lock = threading.RLock()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size:
                if require_empty:
                    raise AuditIntegrityError(
                        f"refusing to append a new runtime to non-empty log: {self.path}"
                    )
                self._entries = self._read_path(self.path)
                verify_entries(self._entries)

    @staticmethod
    def _read_path(path: Path) -> list[AuditEntry]:
        entries: list[AuditEntry] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                    validate_event(parsed)
                    entries.append(AuditEntry.from_dict(parsed))
                except (json.JSONDecodeError, AuditIntegrityError, SchemaValidationError) as exc:
                    raise AuditIntegrityError(
                        f"invalid JSONL audit entry at line {line_number}: {exc}"
                    ) from exc
        return entries

    @property
    def head(self) -> str:
        with self._lock:
            return self._entries[-1].hash if self._entries else ZERO_HASH

    @property
    def length(self) -> int:
        with self._lock:
            return len(self._entries)

    def append(
        self,
        *,
        event: str,
        actor: str,
        outcome: str,
        data: Mapping[str, Any],
        state: M3C3State,
        timestamp: datetime | None = None,
    ) -> AuditEntry:
        with self._lock:
            protected_state = state.semantic_dict()
            body: dict[str, object] = {
                "schema_version": AUDIT_SCHEMA_VERSION,
                "sequence": self.length + 1,
                "timestamp": format_timestamp(timestamp or self.clock()),
                "event": event,
                "actor": actor,
                "outcome": outcome,
                "data": copy.deepcopy(dict(data)),
                "state_after": protected_state,
                "state_digest": state_digest(protected_state),
                "prev_hash": self.head,
            }
            entry = AuditEntry.from_dict({**body, "hash": entry_hash(body)})
            validate_event(entry.to_dict())
            original_length = len(self._entries)
            original_exists = self.path.exists() if self.path is not None else False
            original_size = (
                self.path.stat().st_size
                if self.path is not None and original_exists
                else 0
            )
            try:
                if self.path is not None:
                    line = (canonical_json(entry.to_dict()) + "\n").encode("utf-8")
                    with self.path.open("ab") as handle:
                        handle.write(line)
                        handle.flush()
                        os.fsync(handle.fileno())
                self._entries.append(entry)
            except BaseException as exc:
                del self._entries[original_length:]
                if self.path is not None:
                    try:
                        if original_exists:
                            with self.path.open("r+b") as handle:
                                handle.truncate(original_size)
                                handle.flush()
                                os.fsync(handle.fileno())
                        elif self.path.exists():
                            self.path.unlink()
                    except OSError as rollback_exc:
                        raise AuditIntegrityError(
                            "audit append failed and filesystem rollback also failed"
                        ) from rollback_exc
                raise exc
            return entry

    def entries(self) -> list[dict[str, object]]:
        with self._lock:
            return [copy.deepcopy(entry.to_dict()) for entry in self._entries]

    def verify(
        self,
        *,
        expected_head: str | None = None,
        expected_length: int | None = None,
    ) -> bool:
        with self._lock:
            verify_entries(self._entries)
            if expected_length is not None and self.length != expected_length:
                raise AuditIntegrityError(
                    f"audit length {self.length} does not match external anchor {expected_length}"
                )
            if expected_head is not None and self.head != expected_head:
                raise AuditIntegrityError(
                    "audit head does not match the externally anchored head"
                )
            return True

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "AuditLog":
        source = Path(path)
        if not source.is_file() or source.stat().st_size == 0:
            raise AuditIntegrityError(f"audit log is missing or empty: {source}")
        return cls(source, require_empty=False)
