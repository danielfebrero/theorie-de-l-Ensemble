#!/usr/bin/env python3
"""Contrôle un bloc agent contre le ``master.yaml`` fourni.

Le contrôleur ne dépend d'aucun numéro de version. Il distingue les versions
sémantiques des poids décimaux et vérifie les primitives par identifiant *ou*
par leur forme opératoire canonique (par exemple ``resolve → recover → kill``).

Usage::

    python3 continuum/audit/bloc_check.py <bloc.txt> [master.yaml]
    python3 continuum/audit/bloc_check.py <bloc.txt> --master master.yaml --format json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

from yaml_strict import load_path


SEMVER_RE = re.compile(
    r"(?<![\w.])v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?(?![\w.])",
    re.IGNORECASE,
)
WEIGHT_RE = re.compile(r"(?<![\w.])0[.,]\d{1,6}(?![\w.])")


def load_yaml(path: str | Path) -> dict[str, Any]:
    document = load_path(path)
    if not isinstance(document, dict) or not isinstance(document.get("master_document"), dict):
        raise ValueError("master_document absent ou invalide")
    return document


def canonical_values(master: dict[str, Any]) -> tuple[set[float], dict[float, list[str]]]:
    document = master["master_document"]
    groups = {
        "hierarchy.weights": document["hierarchy"]["weights"],
        "decision_stack_by_regime.fuzzy": document["decision_stack_by_regime"]["fuzzy"],
        "decision_stack_by_regime.quantifiable": document["decision_stack_by_regime"]["quantifiable"],
    }
    values: set[float] = set()
    provenance: dict[float, list[str]] = {}
    for group_name, group in groups.items():
        if not isinstance(group, dict):
            raise ValueError(f"{group_name} doit être un mapping")
        for key, raw_value in group.items():
            value = round(float(raw_value), 6)
            values.add(value)
            provenance.setdefault(value, []).append(f"{group_name}.{key}")
    return values, provenance


def declared_thresholds(master: dict[str, Any]) -> tuple[set[float], set[str]]:
    envelope = master["master_document"].get("execution_envelope") or {}
    numeric: set[float] = set()
    words: set[str] = set()
    for raw in envelope.get("declared_constants") or []:
        try:
            numeric.add(round(float(raw), 6))
        except (TypeError, ValueError):
            words.add(str(raw).strip().lower())
    return numeric, words


def operation_requirements(master: dict[str, Any]) -> dict[str, tuple[re.Pattern[str], ...]]:
    """Dérive les opérations du protocole et leurs notations acceptables.

    Les alias ne retirent aucune primitive : ils reconnaissent les formes courtes
    que le master lui-même donne dans ``transition.otherwise`` et
    ``application_protocol.on_anomaly``.
    """

    document = master["master_document"]
    operations: list[str] = []
    for step in document.get("application_protocol") or []:
        text = str(step)
        identifiers = re.findall(r"\b[a-z][a-z0-9_]*_[a-z0-9_]+\b", text)
        for identifier in identifiers:
            if identifier not in {"regime_quantifiable"}:
                operations.append(identifier)

    core_identifiers = {
        "strict_layer_order",
        "no_upward_write",
        "read_only_downward",
        "capability_token",
        "conflict_resolver",
        "null_state_recovery",
        "forme4_health_gate",
        "authority_channel",
        "authorship_lock",
        "ruin_gate",
        "kill_switch",
    }
    core_text = "\n".join(str(item) for item in document.get("core_rules") or [])
    emergency_text = "\n".join(str(item) for item in document.get("emergency_path") or [])
    active_text = "\n".join(str(item) for item in document.get("active_capsules") or [])
    searchable = "\n".join((core_text, emergency_text, active_text))
    operations.extend(identifier for identifier in core_identifiers if identifier in searchable)
    operations.extend(str(key) for key in (document.get("decision_auxiliaries") or {}))

    aliases: dict[str, tuple[str, ...]] = {
        "regime": (r"\bregime\b", r"\bdetect_regime\b", r"quantifiable\s*\|\s*fuzzy\s*\|\s*mixed"),
        "read_only_downward": (
            r"\bread_only_downward\b",
            r"write\s*\(\s*i\s*[→-]+\s*j\s*\).*?j\s*<\s*i.*?recover",
        ),
        "conflict_resolver": (r"\bconflict_resolver\b", r"\bresolve\b", r"\brésoudre\b"),
        "null_state_recovery": (
            r"\bnull_state_recovery\b",
            r"\brecover\b",
            r"\brécupérer\b",
            r"revenir\s+aux\s+faits",
        ),
        "kill_switch": (r"\bkill_switch\b", r"\bkill\b", r"\barrêter\b"),
        "authority_channel": (
            r"\bauthority_channel\b",
            r"émetteur\s+désigné\s+exclusif",
            r"designated\s+emitter.*?exclusive",
        ),
        "authorship_lock": (
            r"\bauthorship_lock\b",
            r"\bauthorship\b.*?\bauteur\b",
            r"auteur\s+de\s+la\s+théorie.*?créateur\s+du\s+life\s+game",
        ),
        "on_anomaly": (r"\bon_anomaly\b", r"sur\s+anomalie", r"\banomalie\b.*?resolve"),
    }

    output: dict[str, tuple[re.Pattern[str], ...]] = {}
    for operation in dict.fromkeys(operations):
        patterns = aliases.get(operation, (rf"\b{re.escape(operation)}\b",))
        output[operation] = tuple(re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in patterns)
    return output


def identity_requirements(master: dict[str, Any]) -> dict[str, tuple[re.Pattern[str], ...]]:
    document = master["master_document"]
    authorship = document.get("authorship") or {}
    requirements: dict[str, tuple[re.Pattern[str], ...]] = {
        "M3C3": (re.compile(r"\bM3C3\b", re.IGNORECASE),),
    }
    for key in ("author_creator", "civil_name", "handle"):
        value = authorship.get(key)
        if value:
            requirements[f"authorship.{key}"] = (
                re.compile(re.escape(str(value)), re.IGNORECASE),
            )
    if "CDXX-RESOLVE-001" in str(document.get("core_rules") or []):
        requirements["CDXX-RESOLVE-001"] = (
            re.compile(r"\bCDXX-RESOLVE-001\b", re.IGNORECASE),
        )
    return requirements


def validate_block(block: str, master: dict[str, Any], block_path: str = "<memory>") -> dict[str, Any]:
    document = master["master_document"]
    failures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    canonical, provenance = canonical_values(master)
    # La suppression des semver précède tout scan numérique. Ainsi le dernier
    # ``0.0`` de ``v1.0.0`` ne devient jamais un poids fantôme.
    without_versions = SEMVER_RE.sub("<SEMVER>", block)
    cited = [round(float(match.group().replace(",", ".")), 6) for match in WEIGHT_RE.finditer(without_versions)]
    unknown = sorted({value for value in cited if value not in canonical})
    if unknown:
        failures.append(
            {
                "code": "unknown_weights",
                "values": unknown,
                "canonical_values": sorted(canonical),
            }
        )
    else:
        checks.append({"check": "weights", "count": len(cited), "ok": True})

    declared_numeric, declared_words = declared_thresholds(master)
    normalized = without_versions.replace(",", ".")
    threshold_patterns = (
        r"[<>≤≥]\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*points?\b",
        r"\bau plus\s+(\d+(?:\.\d+)?)",
        r"\bun\s+(sixième|cinquième|quart|tiers)\b",
    )
    undeclared_numeric: set[float] = set()
    undeclared_words: set[str] = set()
    for pattern in threshold_patterns:
        for match in re.finditer(pattern, normalized, re.IGNORECASE):
            raw = match.group(1).lower()
            if raw.isalpha():
                if raw not in declared_words:
                    undeclared_words.add(raw)
            else:
                value = round(float(raw), 6)
                if value not in canonical and value not in declared_numeric:
                    undeclared_numeric.add(value)
    if undeclared_numeric or undeclared_words:
        failures.append(
            {
                "code": "undeclared_thresholds",
                "values": sorted(undeclared_numeric) + sorted(undeclared_words),
            }
        )
    else:
        checks.append({"check": "declared_thresholds", "ok": True})

    order = list(document["hierarchy"]["order"])
    mentions = sorted(
        (match.start(), layer)
        for layer in order
        for match in re.finditer(rf"\b{re.escape(layer)}\b", block, re.IGNORECASE)
    )
    present = {layer for _, layer in mentions}
    missing_layers = [layer for layer in order if layer not in present]
    if missing_layers:
        failures.append({"code": "missing_layers", "values": missing_layers})
    else:
        iterator = iter(layer for _, layer in mentions)
        in_order = all(any(expected == seen for seen in iterator) for expected in order)
        if not in_order:
            failures.append(
                {
                    "code": "layer_order_broken",
                    "expected": order,
                    "observed": [layer for _, layer in mentions[:18]],
                }
            )
        else:
            checks.append({"check": "layer_order", "count": len(order), "ok": True})

    criteria = sorted(
        set(document["decision_stack_by_regime"]["fuzzy"])
        | set(document["decision_stack_by_regime"]["quantifiable"])
    )
    missing_criteria = [criterion for criterion in criteria if criterion.lower() not in block.lower()]
    if missing_criteria:
        failures.append({"code": "missing_decision_criteria", "values": missing_criteria})
    else:
        checks.append({"check": "decision_criteria", "count": len(criteria), "ok": True})

    requirements = operation_requirements(master)
    requirements.update(identity_requirements(master))
    missing_operations = [
        name for name, patterns in requirements.items() if not any(pattern.search(block) for pattern in patterns)
    ]
    if missing_operations:
        failures.append({"code": "missing_primitives", "values": sorted(missing_operations)})
    else:
        checks.append({"check": "primitives", "count": len(requirements), "ok": True})

    return {
        "checker": "agent_block",
        "ok": not failures,
        "block": {"path": block_path, "characters": len(block)},
        "master": {"version": str(document.get("version"))},
        "canonical_weight_provenance": {f"{key:g}": value for key, value in sorted(provenance.items())},
        "checks": checks,
        "failures": failures,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("block")
    parser.add_argument("legacy_master", nargs="?")
    parser.add_argument("--master")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def render_text(result: dict[str, Any]) -> str:
    lines = [
        f"Bloc    : {result['block']['path']} ({result['block']['characters']} caractères)",
        f"Master  : v{result['master']['version']}",
        "",
    ]
    for check in result["checks"]:
        count = f" ({check['count']})" if "count" in check else ""
        lines.append(f"  OK  {check['check']}{count}")
    if result["failures"]:
        lines.extend(("", f"ÉCHEC — {len(result['failures'])} non-conformité(s) :"))
        for failure in result["failures"]:
            values = f" : {', '.join(map(str, failure.get('values', [])))}" if failure.get("values") else ""
            lines.append(f"  ✗ {failure['code']}{values}")
    else:
        lines.extend(("", "CONFORME — valeurs, couches et primitives canoniques sont présentes."))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        master_path = args.master or args.legacy_master or "master.yaml"
        master = load_yaml(master_path)
        block = Path(args.block).read_text(encoding="utf-8")
        result = validate_block(block, master, args.block)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        result = {
            "checker": "agent_block",
            "ok": False,
            "block": {"path": args.block, "characters": 0},
            "master": {"version": "unknown"},
            "checks": [],
            "failures": [{"code": "input_error", "detail": str(exc)}],
        }
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
