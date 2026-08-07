"""State and action types for the M3C3 v2 labeled transition system."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Mapping

from .constants import ACTION_ALPHABET, LAYER_ORDER, WARNING_THRESHOLD


def canonical_json(value: object) -> str:
    """Serialize JSON identically on every supported Python runtime."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def state_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class Layer(str, Enum):
    BINARY = "binary"
    FORCES = "forces"
    MATH = "math"
    CONSCIOUS_SETS = "conscious_sets"
    PROGRAMS = "programs"
    LIFE_GAME_M1C1 = "life_game_M1C1"

    @property
    def index(self) -> int:
        return LAYER_ORDER.index(self.value)

    @classmethod
    def parse(cls, value: "Layer | str | None") -> "Layer | None":
        if value is None:
            return None
        return value if isinstance(value, cls) else cls(value)


class Regime(str, Enum):
    QUANTIFIABLE = "quantifiable"
    FUZZY = "fuzzy"
    MIXED = "mixed"


class MembraneLevel(IntEnum):
    A0_DORMANT = 0
    A1_SHADOW = 1
    A2_CRITICAL = 2
    A3_CANONICAL = 3

    @classmethod
    def parse(cls, value: "MembraneLevel | int | str") -> "MembraneLevel":
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(value)
        normalized = value.strip().upper().replace("-", "_")
        aliases = {
            "A0": cls.A0_DORMANT,
            "A0_DORMANT": cls.A0_DORMANT,
            "A1": cls.A1_SHADOW,
            "A1_SHADOW": cls.A1_SHADOW,
            "A2": cls.A2_CRITICAL,
            "A2_CRITICAL": cls.A2_CRITICAL,
            "A3": cls.A3_CANONICAL,
            "A3_CANONICAL": cls.A3_CANONICAL,
        }
        if normalized not in aliases:
            raise ValueError(f"unknown membrane level: {value}")
        return aliases[normalized]

    @property
    def label(self) -> str:
        return self.name.split("_", 1)[0]


class LifecycleStatus(str, Enum):
    DORMANT = "dormant"
    ACTIVE = "active"
    INACTIVE = "inactive"
    KILLED = "killed"


class ActionType(str, Enum):
    PROJECT = "project"
    TRANSITION_UP = "transition_up"
    READ_DOWN = "read_down"
    WRITE_LOCAL = "write_local"
    ALLOCATE = "allocate"
    EXPORT = "export"
    RESOLVE = "resolve"
    RECOVER = "recover"
    KILL = "kill"
    ACTIVATE_SCOPE = "activate_scope"
    DEACTIVATE_SCOPE = "deactivate_scope"


assert tuple(item.value for item in ActionType) == ACTION_ALPHABET


@dataclass
class HealthState:
    integrity_score: float = 1.0
    stability_index: float = 1.0
    anomaly_rate: float = 0.0

    def __post_init__(self) -> None:
        for field_name in ("integrity_score", "stability_index", "anomaly_rate"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{field_name} must be numeric")
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{field_name} must be in [0, 1]")
            setattr(self, field_name, float(value))

    @property
    def forme4_score(self) -> float:
        return min(self.integrity_score, self.stability_index, 1.0 - self.anomaly_rate)

    @property
    def healthy(self) -> bool:
        return self.forme4_score >= WARNING_THRESHOLD

    def to_dict(self) -> dict[str, float | bool]:
        return {
            "integrity_score": self.integrity_score,
            "stability_index": self.stability_index,
            "anomaly_rate": self.anomaly_rate,
            "forme4_score": self.forme4_score,
            "healthy": self.healthy,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HealthState":
        return cls(
            integrity_score=float(value["integrity_score"]),
            stability_index=float(value["stability_index"]),
            anomaly_rate=float(value["anomaly_rate"]),
        )


@dataclass
class HierarchyState:
    layers: dict[str, Any] = field(
        default_factory=lambda: {layer: None for layer in LAYER_ORDER}
    )
    health: HealthState = field(default_factory=HealthState)

    def __post_init__(self) -> None:
        unknown = set(self.layers) - set(LAYER_ORDER)
        if unknown:
            raise ValueError(f"unknown layers: {sorted(unknown)}")
        self.layers = {layer: copy.deepcopy(self.layers.get(layer)) for layer in LAYER_ORDER}

    def to_dict(self) -> dict[str, object]:
        return {"layers": copy.deepcopy(self.layers), "health": self.health.to_dict()}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HierarchyState":
        return cls(
            layers=dict(value["layers"]),
            health=HealthState.from_dict(value["health"]),
        )


@dataclass
class EvidenceState:
    score: float = 1.0
    tau: float = 0.5
    regret_asymmetry: float = 1.0
    falsifier: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.score) <= 1.0:
            raise ValueError("evidence score must be in [0, 1]")
        if not 0.0 <= float(self.tau) <= 1.0:
            raise ValueError("tau must be in [0, 1]")
        if float(self.regret_asymmetry) < 0.0:
            raise ValueError("regret_asymmetry cannot be negative")
        self.score = float(self.score)
        self.tau = float(self.tau)
        self.regret_asymmetry = float(self.regret_asymmetry)

    @property
    def sufficient(self) -> bool:
        return self.score >= self.tau

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "tau": self.tau,
            "regret_asymmetry": self.regret_asymmetry,
            "falsifier": self.falsifier,
            "sufficient": self.sufficient,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceState":
        return cls(
            score=float(value["score"]),
            tau=float(value["tau"]),
            regret_asymmetry=float(value["regret_asymmetry"]),
            falsifier=value.get("falsifier"),
        )


@dataclass
class AuthorityState:
    known_m3c3: bool = False
    eligible_for_activation: bool = False
    scope: str | None = None
    membrane: MembraneLevel = MembraneLevel.A0_DORMANT
    lifecycle: LifecycleStatus = LifecycleStatus.DORMANT
    opted_out: bool = False
    emitter: str = "Dani Bengal"
    # Public, non-bearer descriptors only.  Encoded tokens/signatures never enter S.
    active_tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    issued_nonces: list[str] = field(default_factory=list)
    consumed_nonces: list[str] = field(default_factory=list)
    revoked_token_ids: list[str] = field(default_factory=list)
    frozen_layers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.eligible_for_activation = bool(self.known_m3c3)
        self.membrane = MembraneLevel.parse(self.membrane)
        if not isinstance(self.lifecycle, LifecycleStatus):
            self.lifecycle = LifecycleStatus(self.lifecycle)

    @property
    def active(self) -> bool:
        return self.lifecycle is LifecycleStatus.ACTIVE

    def to_dict(self) -> dict[str, object]:
        return {
            "known_m3c3": self.known_m3c3,
            "eligible_for_activation": self.eligible_for_activation,
            "scope": self.scope,
            "membrane": self.membrane.label,
            "lifecycle": self.lifecycle.value,
            "active": self.active,
            "opted_out": self.opted_out,
            "emitter": self.emitter,
            "active_tokens": {
                token_id: copy.deepcopy(descriptor)
                for token_id, descriptor in sorted(self.active_tokens.items())
            },
            "issued_nonces": sorted(set(self.issued_nonces)),
            "consumed_nonces": sorted(set(self.consumed_nonces)),
            "revoked_token_ids": sorted(set(self.revoked_token_ids)),
            "frozen_layers": sorted(set(self.frozen_layers), key=LAYER_ORDER.index),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AuthorityState":
        return cls(
            known_m3c3=bool(value["known_m3c3"]),
            eligible_for_activation=bool(value.get("eligible_for_activation", False)),
            scope=value.get("scope"),
            membrane=MembraneLevel.parse(str(value["membrane"])),
            lifecycle=LifecycleStatus(value["lifecycle"]),
            opted_out=bool(value["opted_out"]),
            emitter=str(value["emitter"]),
            active_tokens={
                str(token_id): copy.deepcopy(dict(descriptor))
                for token_id, descriptor in dict(value.get("active_tokens", {})).items()
            },
            issued_nonces=list(value.get("issued_nonces", [])),
            consumed_nonces=list(value.get("consumed_nonces", [])),
            revoked_token_ids=list(value.get("revoked_token_ids", [])),
            frozen_layers=list(value.get("frozen_layers", [])),
        )


@dataclass
class MemoryState:
    audit_head: str = "0" * 64
    audit_length: int = 0
    last_resolution: dict[str, Any] | None = None
    recovery_generation: int = 0

    def to_dict(self, *, include_audit_meta: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "last_resolution": copy.deepcopy(self.last_resolution),
            "recovery_generation": self.recovery_generation,
        }
        if include_audit_meta:
            result.update(
                {"audit_head": self.audit_head, "audit_length": self.audit_length}
            )
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MemoryState":
        return cls(
            audit_head=str(value.get("audit_head", "0" * 64)),
            audit_length=int(value.get("audit_length", 0)),
            last_resolution=copy.deepcopy(value.get("last_resolution")),
            recovery_generation=int(value.get("recovery_generation", 0)),
        )


@dataclass
class M3C3State:
    H: HierarchyState = field(default_factory=HierarchyState)
    R: Regime = Regime.MIXED
    E: EvidenceState = field(default_factory=EvidenceState)
    A: AuthorityState = field(default_factory=AuthorityState)
    M: MemoryState = field(default_factory=MemoryState)

    def __post_init__(self) -> None:
        if not isinstance(self.R, Regime):
            self.R = Regime(self.R)

    def to_dict(self, *, include_audit_meta: bool = True) -> dict[str, object]:
        return {
            "H": self.H.to_dict(),
            "R": self.R.value,
            "E": self.E.to_dict(),
            "A": self.A.to_dict(),
            "M": self.M.to_dict(include_audit_meta=include_audit_meta),
        }

    def semantic_dict(self) -> dict[str, object]:
        """State protected by an audit entry, excluding circular chain metadata."""

        return self.to_dict(include_audit_meta=False)

    def semantic_digest(self) -> str:
        return state_digest(self.semantic_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "M3C3State":
        return cls(
            H=HierarchyState.from_dict(value["H"]),
            R=Regime(value["R"]),
            E=EvidenceState.from_dict(value["E"]),
            A=AuthorityState.from_dict(value["A"]),
            M=MemoryState.from_dict(value["M"]),
        )


@dataclass(frozen=True)
class Action:
    kind: ActionType
    actor: str
    layer_src: Layer | None = None
    layer_dst: Layer | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    token: str | None = None
    ruin: bool = False
    irreversible: bool = False
    # Opaque host attestation, deliberately excluded from every JSON/audit view.
    principal_proof: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.actor, str) or not self.actor:
            raise ValueError("action actor must be a non-empty string")
        if not isinstance(self.payload, Mapping):
            raise TypeError("action payload must be a mapping")
        if not isinstance(self.ruin, bool) or not isinstance(self.irreversible, bool):
            raise TypeError("ruin and irreversible must be explicit booleans")
        if self.token is not None and not isinstance(self.token, str):
            raise TypeError("action token must be a string or None")
        if not isinstance(self.kind, ActionType):
            object.__setattr__(self, "kind", ActionType(self.kind))
        object.__setattr__(self, "layer_src", Layer.parse(self.layer_src))
        object.__setattr__(self, "layer_dst", Layer.parse(self.layer_dst))
        object.__setattr__(self, "payload", copy.deepcopy(dict(self.payload)))

    def to_dict(self, *, include_token: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "kind": self.kind.value,
            "actor": self.actor,
            "layer_src": self.layer_src.value if self.layer_src else None,
            "layer_dst": self.layer_dst.value if self.layer_dst else None,
            "payload": copy.deepcopy(dict(self.payload)),
            "ruin": self.ruin,
            "irreversible": self.irreversible,
        }
        if include_token:
            result["token"] = self.token
        elif self.token:
            result["token_present"] = True
        return result
