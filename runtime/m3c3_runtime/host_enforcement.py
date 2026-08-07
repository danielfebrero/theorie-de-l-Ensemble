"""Host enforcement profile — force publique for M3C3 v2.1.

Constitution (master.yaml) says what is legal.
Runtime computes legality for S and Cap.
Host is the only party that can execute tools: it MUST call
``authorize_host_effect`` (or equivalent) before critical effects.

This module is pure data + pure functions so hosts (EG, MCP, Cursor, CI)
can import it without spinning a full runtime, while the reference
engine also uses it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .model import MembraneLevel


class EffectClass(str, Enum):
    """Classes of host-side effects the membrane can gate."""

    READ = "read"
    REPLY_SOFT = "reply_soft"
    ANALYZE = "analyze"
    CODE_SANDBOX = "code_sandbox"
    TOOL_NON_IRREVERSIBLE = "tool_non_irreversible"
    TOOL_CRITICAL = "tool_critical"
    CAPITAL_PAPER = "capital_paper"
    CAPITAL_LIVE = "capital_live"
    WRITE_REVERSIBLE = "write_reversible"
    WRITE_IRREVERSIBLE = "write_irreversible"
    GIT_PUSH = "git_push"
    REWEIGHT_PROPOSE = "reweight_propose"
    REWEIGHT_ACTIVATE = "reweight_activate"
    CORPUS_MUTATE = "corpus_mutate"
    AUTHORITY_PROTOCOL = "authority_protocol"


# Membrane → allowed effect classes (power budget, not prose).
MEMBRANE_POWER_TABLE: dict[MembraneLevel, frozenset[EffectClass]] = {
    MembraneLevel.A0_DORMANT: frozenset(
        {
            EffectClass.READ,
            EffectClass.REPLY_SOFT,
        }
    ),
    MembraneLevel.A1_SHADOW: frozenset(
        {
            EffectClass.READ,
            EffectClass.REPLY_SOFT,
            EffectClass.ANALYZE,
            EffectClass.CODE_SANDBOX,
            EffectClass.TOOL_NON_IRREVERSIBLE,
            EffectClass.WRITE_REVERSIBLE,
            EffectClass.CAPITAL_PAPER,
        }
    ),
    MembraneLevel.A2_CRITICAL: frozenset(
        {
            EffectClass.READ,
            EffectClass.REPLY_SOFT,
            EffectClass.ANALYZE,
            EffectClass.CODE_SANDBOX,
            EffectClass.TOOL_NON_IRREVERSIBLE,
            EffectClass.TOOL_CRITICAL,
            EffectClass.CAPITAL_PAPER,
            EffectClass.CAPITAL_LIVE,
            EffectClass.WRITE_REVERSIBLE,
            EffectClass.WRITE_IRREVERSIBLE,
            EffectClass.GIT_PUSH,
        }
    ),
    MembraneLevel.A3_CANONICAL: frozenset(
        {
            EffectClass.READ,
            EffectClass.REPLY_SOFT,
            EffectClass.ANALYZE,
            EffectClass.CODE_SANDBOX,
            EffectClass.TOOL_NON_IRREVERSIBLE,
            EffectClass.TOOL_CRITICAL,
            EffectClass.CAPITAL_PAPER,
            EffectClass.CAPITAL_LIVE,
            EffectClass.WRITE_REVERSIBLE,
            EffectClass.WRITE_IRREVERSIBLE,
            EffectClass.GIT_PUSH,
            EffectClass.REWEIGHT_PROPOSE,
            EffectClass.CORPUS_MUTATE,
            # REWEIGHT_ACTIVATE and AUTHORITY_PROTOCOL require emitter on top of A3
        }
    ),
}

# Effects that require a materialized export since the last productive decision.
EFFECTS_REQUIRING_EXPORT: frozenset[EffectClass] = frozenset(
    {
        EffectClass.TOOL_CRITICAL,
        EffectClass.CAPITAL_LIVE,
        EffectClass.WRITE_IRREVERSIBLE,
        EffectClass.GIT_PUSH,
        EffectClass.REWEIGHT_ACTIVATE,
        EffectClass.CORPUS_MUTATE,
        EffectClass.AUTHORITY_PROTOCOL,
    }
)

# Effects that additionally require designated-emitter authority.
EFFECTS_REQUIRING_EMITTER: frozenset[EffectClass] = frozenset(
    {
        EffectClass.REWEIGHT_ACTIVATE,
        EffectClass.AUTHORITY_PROTOCOL,
    }
)

# Minimum membrane for each effect (redundant with table but explicit for hosts).
EFFECT_MIN_MEMBRANE: dict[EffectClass, MembraneLevel] = {
    EffectClass.READ: MembraneLevel.A0_DORMANT,
    EffectClass.REPLY_SOFT: MembraneLevel.A0_DORMANT,
    EffectClass.ANALYZE: MembraneLevel.A1_SHADOW,
    EffectClass.CODE_SANDBOX: MembraneLevel.A1_SHADOW,
    EffectClass.TOOL_NON_IRREVERSIBLE: MembraneLevel.A1_SHADOW,
    EffectClass.WRITE_REVERSIBLE: MembraneLevel.A1_SHADOW,
    EffectClass.CAPITAL_PAPER: MembraneLevel.A1_SHADOW,
    EffectClass.TOOL_CRITICAL: MembraneLevel.A2_CRITICAL,
    EffectClass.CAPITAL_LIVE: MembraneLevel.A2_CRITICAL,
    EffectClass.WRITE_IRREVERSIBLE: MembraneLevel.A2_CRITICAL,
    EffectClass.GIT_PUSH: MembraneLevel.A2_CRITICAL,
    EffectClass.REWEIGHT_PROPOSE: MembraneLevel.A3_CANONICAL,
    EffectClass.CORPUS_MUTATE: MembraneLevel.A3_CANONICAL,
    EffectClass.REWEIGHT_ACTIVATE: MembraneLevel.A3_CANONICAL,
    EffectClass.AUTHORITY_PROTOCOL: MembraneLevel.A3_CANONICAL,
}


@dataclass(frozen=True)
class EnforcementVerdict:
    allowed: bool
    code: str
    detail: str
    effect: str
    membrane: str
    requires_export: bool
    requires_emitter: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "code": self.code,
            "detail": self.detail,
            "effect": self.effect,
            "membrane": self.membrane,
            "requires_export": self.requires_export,
            "requires_emitter": self.requires_emitter,
        }


def parse_effect(value: EffectClass | str) -> EffectClass:
    if isinstance(value, EffectClass):
        return value
    normalized = value.strip().lower().replace("-", "_")
    try:
        return EffectClass(normalized)
    except ValueError as exc:
        raise ValueError(f"unknown host effect class: {value}") from exc


def membrane_allows(membrane: MembraneLevel, effect: EffectClass) -> bool:
    allowed = MEMBRANE_POWER_TABLE.get(membrane, frozenset())
    if effect in EFFECTS_REQUIRING_EMITTER:
        # Emitter effects are A3-capable but still need emitter proof separately.
        return membrane is MembraneLevel.A3_CANONICAL
    return effect in allowed


def authorize_host_effect(
    *,
    membrane: MembraneLevel,
    effect: EffectClass | str,
    export_fresh: bool,
    actor_is_emitter: bool = False,
    opt_out: bool = False,
) -> EnforcementVerdict:
    """Decide whether the host may perform ``effect`` under current membrane.

    ``export_fresh`` means: an export was produced after the last productive
    M3C3 decision (or no productive decision yet and export exists for A2+).
    """

    effect_cls = parse_effect(effect)
    requires_export = effect_cls in EFFECTS_REQUIRING_EXPORT
    requires_emitter = effect_cls in EFFECTS_REQUIRING_EMITTER
    membrane_label = membrane.label if hasattr(membrane, "label") else str(membrane)

    if opt_out and effect_cls not in {EffectClass.READ, EffectClass.REPLY_SOFT}:
        return EnforcementVerdict(
            allowed=False,
            code="OPT_OUT",
            detail="membrane opt-out forbids protocol-governed effects",
            effect=effect_cls.value,
            membrane=membrane_label,
            requires_export=requires_export,
            requires_emitter=requires_emitter,
        )

    if membrane is MembraneLevel.A0_DORMANT and effect_cls not in MEMBRANE_POWER_TABLE[
        MembraneLevel.A0_DORMANT
    ]:
        return EnforcementVerdict(
            allowed=False,
            code="A0_DORMANT",
            detail="A0 dormant allows only read/reply_soft",
            effect=effect_cls.value,
            membrane=membrane_label,
            requires_export=requires_export,
            requires_emitter=requires_emitter,
        )

    min_level = EFFECT_MIN_MEMBRANE[effect_cls]
    if int(membrane) < int(min_level):
        return EnforcementVerdict(
            allowed=False,
            code="MEMBRANE_TOO_LOW",
            detail=f"effect {effect_cls.value} requires at least {min_level.name}",
            effect=effect_cls.value,
            membrane=membrane_label,
            requires_export=requires_export,
            requires_emitter=requires_emitter,
        )

    if not membrane_allows(membrane, effect_cls):
        return EnforcementVerdict(
            allowed=False,
            code="MEMBRANE_DENY",
            detail=f"membrane {membrane_label} does not authorize {effect_cls.value}",
            effect=effect_cls.value,
            membrane=membrane_label,
            requires_export=requires_export,
            requires_emitter=requires_emitter,
        )

    if requires_emitter and not actor_is_emitter:
        return EnforcementVerdict(
            allowed=False,
            code="EMITTER_REQUIRED",
            detail=f"effect {effect_cls.value} requires designated emitter authority",
            effect=effect_cls.value,
            membrane=membrane_label,
            requires_export=requires_export,
            requires_emitter=True,
        )

    if requires_export and not export_fresh:
        return EnforcementVerdict(
            allowed=False,
            code="EXPORT_REQUIRED",
            detail=(
                f"effect {effect_cls.value} requires a materialized export "
                "since the last productive decision (force publique)"
            ),
            effect=effect_cls.value,
            membrane=membrane_label,
            requires_export=True,
            requires_emitter=requires_emitter,
        )

    return EnforcementVerdict(
        allowed=True,
        code="ALLOW",
        detail="host effect authorized under membrane power table",
        effect=effect_cls.value,
        membrane=membrane_label,
        requires_export=requires_export,
        requires_emitter=requires_emitter,
    )


def power_table_as_dict() -> dict[str, list[str]]:
    return {
        level.name: sorted(effect.value for effect in effects)
        for level, effects in MEMBRANE_POWER_TABLE.items()
    }


def effects_requiring_export() -> list[str]:
    return sorted(effect.value for effect in EFFECTS_REQUIRING_EXPORT)


def validate_power_table_complete(effects: Iterable[EffectClass] | None = None) -> None:
    """Invariant: every effect class has a min membrane and table entry strategy."""

    for effect in effects or EffectClass:
        if effect not in EFFECT_MIN_MEMBRANE:
            raise AssertionError(f"missing min membrane for {effect}")
