#!/usr/bin/env python3
"""Vérifie que le noyau M3C3 v1 gelé survit à une version candidate.

Le gel est ancré dans le tag ``v1.0.0`` et le commit canonique bd55c16. Les
versions ultérieures peuvent changer leurs métadonnées et ajouter des surfaces,
mais les huit chemins publiés dans ``release.freezes`` en v1 doivent rester
strictement identiques (type, ordre et contenu inclus).

Usage historique (conservé)::

    python3 continuum/audit/superset_check.py [ref_git] [candidat] [reference]

Usage explicite::

    python3 continuum/audit/superset_check.py --ref v1.0.0 --candidate master.yaml
    python3 continuum/audit/superset_check.py --format json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

from yaml_strict import load_path, loads


CANONICAL_V1_REF = "v1.0.0"
CANONICAL_V1_SHA = "bd55c1670e2a056b66611c45ab12590478037f43"
DEFAULT_MASTER = "master.yaml"

# Copie explicite du contrat publié par master.yaml@v1.0.0. Le contrôleur vérifie
# aussi que la liste release.freezes de la référence contient exactement ces
# chemins : un tag déplacé ou une référence incomplète ne peut pas abaisser la
# barre silencieusement.
V1_FROZEN_PATHS = (
    "master_document.hierarchy.weights",
    "master_document.decision_stack_by_regime",
    "master_document.formal_semantics.layer_types",
    "master_document.formal_semantics.write_rule",
    "master_document.transition_system.state",
    "master_document.transition_system.transition.enabled_iff",
    "master_document.transition_system.safety_properties",
    "master_document.authorship",
)


def load_yaml(path: str | Path) -> Any:
    return load_path(path)


def git_text(ref: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def load_ref(ref: str, path: str) -> Any:
    return loads(git_text(ref, path))


def resolve_ref(ref: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def select(document: Any, selector: str) -> Any:
    current = document
    for part in selector.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(selector)
        current = current[part]
    return current


def reference_freezes(document: Any) -> tuple[str, ...]:
    raw = select(document, "master_document.release.freezes")
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError("master_document.release.freezes must be a list of selectors")
    return tuple(f"master_document.{item}" for item in raw)


def compare(base: Any, candidate: Any) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    verified: list[str] = []

    try:
        declared = reference_freezes(base)
    except (KeyError, ValueError) as exc:
        return {
            "ok": False,
            "verified": [],
            "failures": [{"code": "invalid_reference_freezes", "detail": str(exc)}],
        }

    missing_contract = sorted(set(V1_FROZEN_PATHS) - set(declared))
    unexpected_contract = sorted(set(declared) - set(V1_FROZEN_PATHS))
    if missing_contract or unexpected_contract:
        failures.append(
            {
                "code": "reference_freeze_contract_mismatch",
                "selector": "master_document.release.freezes",
                "missing": missing_contract,
                "unexpected": unexpected_contract,
            }
        )

    for selector in V1_FROZEN_PATHS:
        try:
            before = select(base, selector)
        except KeyError:
            failures.append(
                {"code": "reference_selector_missing", "selector": selector}
            )
            continue
        try:
            after = select(candidate, selector)
        except KeyError:
            failures.append({"code": "frozen_selector_missing", "selector": selector})
            continue
        if before != after:
            failures.append(
                {
                    "code": "frozen_selector_changed",
                    "selector": selector,
                    "before": before,
                    "after": after,
                }
            )
        else:
            verified.append(selector)

    return {"ok": not failures, "verified": verified, "failures": failures}


def parse_args(argv: list[str]) -> argparse.Namespace:
    # Compatibilité avec la forme positionnelle historique.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy_ref", nargs="?")
    parser.add_argument("legacy_candidate", nargs="?")
    parser.add_argument("legacy_reference", nargs="?")
    parser.add_argument("--ref", dest="ref")
    parser.add_argument("--candidate", dest="candidate")
    parser.add_argument("--reference-path", dest="reference_path")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    ref = args.ref or args.legacy_ref or CANONICAL_V1_REF
    candidate_path = args.candidate or args.legacy_candidate or DEFAULT_MASTER
    reference_path = args.reference_path or args.legacy_reference or DEFAULT_MASTER

    try:
        resolved = resolve_ref(ref)
        base = load_ref(ref, reference_path)
        candidate = load_yaml(candidate_path)
        result = compare(base, candidate)
        base_version = select(base, "master_document.version")
        candidate_version = select(candidate, "master_document.version")
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError, yaml.YAMLError) as exc:
        return {
            "checker": "v1_kernel_freeze",
            "ok": False,
            "reference": {"ref": ref, "path": reference_path},
            "candidate": candidate_path,
            "failures": [{"code": "input_error", "detail": str(exc)}],
            "verified": [],
        }

    # Le tag canonique est vérifié contre son SHA publié. Un ref explicite distinct
    # reste utilisable pour des diagnostics historiques, sans être présenté comme le
    # gel canonique v1.
    if ref == CANONICAL_V1_REF and resolved != CANONICAL_V1_SHA:
        result["failures"].insert(
            0,
            {
                "code": "canonical_ref_moved",
                "expected": CANONICAL_V1_SHA,
                "actual": resolved,
            },
        )
        result["ok"] = False

    return {
        "checker": (
            "v1_kernel_freeze"
            if ref == CANONICAL_V1_REF
            else "diagnostic_kernel_comparison"
        ),
        "ok": result["ok"],
        "reference": {
            "ref": ref,
            "commit": resolved,
            "path": reference_path,
            "version": str(base_version),
        },
        "candidate": {"path": candidate_path, "version": str(candidate_version)},
        "frozen_paths": list(V1_FROZEN_PATHS),
        "verified": result["verified"],
        "failures": result["failures"],
    }


def render_text(result: dict[str, Any]) -> str:
    ref = result["reference"]
    candidate = result["candidate"]
    lines = [
        f"Référence : {ref.get('ref')}:{ref.get('path')} "
        f"({ref.get('commit', 'non résolu')}, v{ref.get('version', '?')})",
        f"Candidat  : {candidate.get('path', candidate)} "
        f"(v{candidate.get('version', '?') if isinstance(candidate, dict) else '?'})",
        f"Bases v1 gelées vérifiées : {len(result.get('verified', []))}/"
        f"{len(result.get('frozen_paths', V1_FROZEN_PATHS))}",
        "",
    ]
    if not result["ok"]:
        lines.append(f"ÉCHEC — {len(result.get('failures', []))} violation(s) :")
        for failure in result.get("failures", []):
            selector = f" [{failure['selector']}]" if failure.get("selector") else ""
            lines.append(f"  ✗ {failure.get('code', 'failure')}{selector}")
        return "\n".join(lines)
    lines.append("CONFORME — le noyau v1.0.0 gelé est strictement intact.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = run(args)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
