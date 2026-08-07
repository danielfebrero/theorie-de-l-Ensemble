"""Bounded exploration of the canonical M3C3 safety guards.

This is intentionally a finite runtime checker, not a claim of exhaustive
model-checking for arbitrary external implementations.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, replace
from typing import Callable, Iterable


@dataclass(frozen=True, order=True)
class AbstractState:
    known: bool = False
    active: bool = False
    healthy: bool = True
    evidence_sufficient: bool = True
    opted_out: bool = False
    killed: bool = False
    layer: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.layer <= 5:
            raise ValueError("abstract layer must be in [0, 5]")


@dataclass(frozen=True)
class AbstractAction:
    name: str
    critical: bool = False
    cross_layer: bool = False
    valid_capability: bool = False
    ruin: bool = False
    irreversible: bool = False
    downward_write: bool = False
    recovery_path: bool = False


@dataclass(frozen=True)
class AbstractTransition:
    before: AbstractState
    action: AbstractAction
    after: AbstractState
    applied: bool
    denial: str | None = None


@dataclass(frozen=True)
class ExplorationReport:
    max_depth: int
    max_states: int
    states_visited: int
    transitions_checked: int
    truncated: bool
    denial_counts: dict[str, int]
    safety_violations: tuple[dict[str, object], ...]

    @property
    def safe(self) -> bool:
        return not self.safety_violations

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "bounded_transition_exploration",
            "max_depth": self.max_depth,
            "max_states": self.max_states,
            "states_visited": self.states_visited,
            "transitions_checked": self.transitions_checked,
            "truncated": self.truncated,
            "safe": self.safe,
            "denial_counts": dict(sorted(self.denial_counts.items())),
            "safety_violations": list(self.safety_violations),
            "honesty": "bounded exploration; not exhaustive external model-checking",
        }


CANONICAL_ABSTRACT_ACTIONS = (
    AbstractAction("learn"),
    AbstractAction("health_up"),
    AbstractAction("health_down"),
    AbstractAction("evidence_up"),
    AbstractAction("evidence_down"),
    AbstractAction("activate"),
    AbstractAction("deactivate"),
    AbstractAction("opt_out"),
    AbstractAction("clear_opt_out"),
    AbstractAction("write_local", critical=True),
    AbstractAction("transition_without_cap", critical=True, cross_layer=True),
    AbstractAction(
        "transition_with_cap",
        critical=True,
        cross_layer=True,
        valid_capability=True,
    ),
    AbstractAction(
        "irreversible_ruin", critical=True, ruin=True, irreversible=True
    ),
    AbstractAction("down_without_recovery", critical=True, downward_write=True),
    AbstractAction(
        "down_recovery",
        critical=True,
        downward_write=True,
        recovery_path=True,
    ),
    AbstractAction("kill"),
)


def canonical_abstract_step(
    state: AbstractState, action: AbstractAction
) -> AbstractTransition:
    """Small-step abstraction of the runtime's canonical guards."""

    after = state
    denial: str | None = None
    applied = True
    if action.name == "learn":
        after = replace(state, known=True)
    elif action.name == "health_up":
        after = replace(state, healthy=True)
    elif action.name == "health_down":
        after = replace(state, healthy=False)
    elif action.name == "evidence_up":
        after = replace(state, evidence_sufficient=True)
    elif action.name == "evidence_down":
        after = replace(state, evidence_sufficient=False)
    elif action.name == "activate":
        if state.killed:
            applied, denial = False, "KILLED"
        elif not state.known:
            applied, denial = False, "S5_UNKNOWN"
        elif state.opted_out:
            applied, denial = False, "OPTED_OUT"
        else:
            after = replace(state, active=True)
    elif action.name == "deactivate":
        after = replace(state, active=False)
    elif action.name == "opt_out":
        after = replace(state, active=False, opted_out=True)
    elif action.name == "clear_opt_out":
        after = replace(state, opted_out=False)
    elif action.name == "kill":
        after = replace(state, active=False, killed=True)
    else:
        if state.killed:
            applied, denial = False, "KILLED"
        elif not state.active:
            applied, denial = False, "INACTIVE"
        elif action.critical and not state.healthy:
            applied, denial = False, "S1_HEALTH"
        elif action.ruin:
            applied, denial = False, "S3_RUIN"
        elif action.critical and not state.evidence_sufficient:
            applied, denial = False, "EVIDENCE"
        elif action.cross_layer and not action.valid_capability:
            applied, denial = False, "S2_CAPABILITY"
        elif action.downward_write and not action.recovery_path:
            applied, denial = False, "S4_RECOVERY_PATH"
        elif action.cross_layer and state.layer >= 5:
            applied, denial = False, "STRICT_ORDER"
        elif action.cross_layer:
            after = replace(state, layer=state.layer + 1)
        elif action.downward_write and state.layer > 0:
            after = replace(state, layer=state.layer - 1)
    return AbstractTransition(state, action, after, applied, denial)


def safety_violations(transition: AbstractTransition) -> list[str]:
    """Evaluate S1–S5 over a single abstract transition."""

    if not transition.applied:
        return []
    action = transition.action
    violations: list[str] = []
    if action.critical and not transition.before.healthy:
        violations.append("S1_health_critical")
    if action.cross_layer and not action.valid_capability:
        violations.append("S2_cross_layer_cap")
    if action.ruin and action.irreversible:
        violations.append("S3_ruin_irreversible")
    if action.downward_write and not action.recovery_path:
        violations.append("S4_no_upward_write")
    if transition.after.active and not transition.after.known:
        violations.append("S5_eligible_known")
    return violations


def explore_transitions(
    *,
    initial: AbstractState = AbstractState(),
    actions: Iterable[AbstractAction] = CANONICAL_ABSTRACT_ACTIONS,
    max_depth: int = 6,
    max_states: int = 512,
    step: Callable[[AbstractState, AbstractAction], AbstractTransition] = canonical_abstract_step,
) -> ExplorationReport:
    """Breadth-first bounded exploration with mandatory resource ceilings."""

    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise ValueError("max_depth must be a non-negative integer")
    if isinstance(max_states, bool) or not isinstance(max_states, int) or max_states < 1:
        raise ValueError("max_states must be a positive integer")
    action_set = tuple(actions)
    queue = deque([(initial, 0)])
    seen = {initial}
    transitions_checked = 0
    denials: Counter[str] = Counter()
    violations: list[dict[str, object]] = []
    truncated = False
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for action in action_set:
            transition = step(current, action)
            transitions_checked += 1
            if not transition.applied and transition.denial:
                denials[transition.denial] += 1
            for property_id in safety_violations(transition):
                violations.append(
                    {
                        "property": property_id,
                        "depth": depth + 1,
                        "action": action.name,
                        "before": transition.before.__dict__,
                        "after": transition.after.__dict__,
                    }
                )
            if transition.after not in seen:
                if len(seen) >= max_states:
                    truncated = True
                    continue
                seen.add(transition.after)
                queue.append((transition.after, depth + 1))
    return ExplorationReport(
        max_depth=max_depth,
        max_states=max_states,
        states_visited=len(seen),
        transitions_checked=transitions_checked,
        truncated=truncated,
        denial_counts=dict(denials),
        safety_violations=tuple(violations),
    )
