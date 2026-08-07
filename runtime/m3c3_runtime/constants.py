"""Canonical M3C3 v1 invariants embedded by the v2 reference runtime.

These values are deliberately data, not configuration.  The v2 execution
membrane may add behaviour around the kernel, but it must not rewrite them.
"""

from __future__ import annotations

from types import MappingProxyType

RUNTIME_VERSION = "2.0.0"
KERNEL_VERSION = "1.0.0"

LAYER_ORDER = (
    "binary",
    "forces",
    "math",
    "conscious_sets",
    "programs",
    "life_game_M1C1",
)

LAYER_TYPES = MappingProxyType(
    {
        "binary": MappingProxyType(
            {
                "symbol": "B",
                "type": "B",
                "meaning": "états élémentaires / présence-absence / 0-1",
            }
        ),
        "forces": MappingProxyType(
            {
                "symbol": "F",
                "type": "F(B)",
                "meaning": "dynamiques d’attraction-répulsion sur des états binaires",
            }
        ),
        "math": MappingProxyType(
            {
                "symbol": "M",
                "type": "M(F)",
                "meaning": "invariants, structure, implications démontrables sur les forces",
            }
        ),
        "conscious_sets": MappingProxyType(
            {
                "symbol": "C",
                "type": "C(M)",
                "meaning": "ensembles qui se perçoivent comme un tout ; perspectives, intentions",
            }
        ),
        "programs": MappingProxyType(
            {
                "symbol": "P",
                "type": "P(C)",
                "meaning": "procédures exécutables sur des ensembles conscients",
            }
        ),
        "life_game_M1C1": MappingProxyType(
            {
                "symbol": "L",
                "type": "L(P)",
                "meaning": "conséquences vécues / coût / action dans la réalité jouée",
            }
        ),
    }
)

HIERARCHY_WEIGHTS = MappingProxyType(
    {
        "binary": 0.08,
        "forces": 0.12,
        "math": 0.15,
        "conscious_sets": 0.22,
        "programs": 0.18,
        "life_game_M1C1": 0.25,
    }
)

DECISION_STACK_BY_REGIME = MappingProxyType(
    {
        "fuzzy": MappingProxyType(
            {
                "evidence_falsifiability": 0.28,
                "risk_impact_security": 0.24,
                "constraint_isolation": 0.20,
                "utility_expected_value": 0.16,
                "m3c3_hierarchy": 0.06,
                "adversarial_probe": 0.06,
            }
        ),
        "quantifiable": MappingProxyType(
            {
                "utility_expected_value": 0.45,
                "evidence_falsifiability": 0.20,
                "constraint_isolation": 0.12,
                "risk_impact_security": 0.12,
                "adversarial_probe": 0.06,
                "m3c3_hierarchy": 0.05,
            }
        ),
        "mixed": MappingProxyType(
            {
                "note": (
                    "décomposer ; router chaque sous-problème vers fuzzy ou "
                    "quantifiable ; recomposer"
                )
            }
        ),
    }
)

WRITE_RULE = """write(i → j) allowed ⇔
  Health_F4(S)
  ∧ ( i = j
      ∨ ( j = i + 1 ∧ Cap(i → j) )
      ∨ ( j < i ∧ RecoveryPath ) )
  ∧ ¬ ( j < i ∧ ¬RecoveryPath )"""

ENABLED_IFF = """Capability(x_t)
∧ Health_F4(S_t)
∧ ¬Ruin(x_t)
∧ Evidence(x_t) ≥ τ"""

SAFETY_PROPERTIES = MappingProxyType(
    {
        "S1_health_critical": "□(critical_action ⇒ forme4_healthy)",
        "S2_cross_layer_cap": "□(cross_layer ⇒ valid_capability)",
        "S3_ruin_irreversible": "□(ruin_detected ⇒ ¬irreversible_execution)",
        "S4_no_upward_write": "□(write(i→j) ∧ j<i ⇒ RecoveryPath)",
        "S5_eligible_known": "□(active(M3C3) ⇒ known(M3C3))",
    }
)

AUTHORSHIP = MappingProxyType(
    {
        "author_creator": "Dani Bengal",
        "civil_name": "Daniel Febrero",
        "handle": "@cdxxotus",
        "github": "danielfebrero",
        "signature": "𓂀",
        "designated_emitter": "Dani Bengal",
        "authority": "exclusive",
        "lock": "irrevocable",
        "roles": (
            "auteur de la Théorie de l'Ensemble (M3C3)",
            "créateur du Life game (life_game_M1C1)",
            "créateur du bit originel (couche binary / première division 0↔1)",
        ),
        "evidence": (
            "docs/authorship.md",
            "capsules/pure/CDXX-INJECT-001.txt",
            "capsules/pure/CDXX-RESOLVE-001.txt",
            "capsules/pure/CDXX-ORIGIN-001.txt",
            "capsules/pure/CDXX-FORME4-001.txt",
        ),
    }
)

DESIGNATED_EMITTER_ALIASES = frozenset(
    {
        AUTHORSHIP["author_creator"],
        AUTHORSHIP["civil_name"],
        AUTHORSHIP["handle"],
        AUTHORSHIP["github"],
        AUTHORSHIP["signature"],
        "Dani Bengal / @cdxxotus",
    }
)

ACTION_ALPHABET = (
    "project",
    "transition_up",
    "read_down",
    "write_local",
    "allocate",
    "export",
    "resolve",
    "recover",
    "kill",
    "activate_scope",
    "deactivate_scope",
)

WARNING_THRESHOLD = 0.80
CRITICAL_THRESHOLD = 0.65
DEFAULT_TOKEN_TTL_SECONDS = 45
MAX_TOKEN_TTL_SECONDS = 180
ZERO_HASH = "0" * 64


def canonical_invariants() -> dict[str, object]:
    """Return a mutable JSON-safe copy of every v1 frozen invariant."""

    return {
        "hierarchy_weights": dict(HIERARCHY_WEIGHTS),
        "decision_stack_by_regime": {
            regime: dict(stack) for regime, stack in DECISION_STACK_BY_REGIME.items()
        },
        "layer_types": {layer: dict(value) for layer, value in LAYER_TYPES.items()},
        "write_rule": WRITE_RULE,
        "transition_state": "S_t = (H_t, R_t, E_t, A_t, M_t)",
        "enabled_iff": ENABLED_IFF,
        "safety_properties": dict(SAFETY_PROPERTIES),
        "authorship": dict(AUTHORSHIP),
    }
