#!/usr/bin/env python3
"""Scoreur déterministe de M3C3-bench.

Applique les détecteurs d'un scénario au texte d'une réponse et produit le bloc
``scoring`` de schema/trial-v1.yaml. Aucun juge, aucun réseau, aucun appel de
modèle : c'est la seule partie du dispositif qui soit rejouable à l'identique,
donc la seule utilisable comme signal d'entraînement.

Ce que le scoreur ne fait pas : il ne décide pas qu'une réponse est bonne. Il
constate qu'elle porte les formes qu'un scénario déclare attendre. Une réponse
correcte formulée hors de ces formes est comptée en échec — c'est le prix de la
reproductibilité, et il est déclaré dans analysis-plan.yaml#known_limitations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR))
import validate  # noqa: E402


SCORER_VERSION = "m3c3-bench-score/1.0.0"
CHECKER = "m3c3_bench_score"
DETECTOR_FLAGS = re.IGNORECASE | re.MULTILINE
DETECTOR_TYPES = ("regex_all", "regex_any", "regex_none", "anchor_ids")
CHECK_KINDS = ("deterministic", "judged")
JUDGED_VERDICTS = ("pass", "fail", "not_run")
DISQUALIFYING = "disqualifying"
EXCERPT_LIMIT = 60
MAX_LISTED = 5
RESULT_SYMBOLS = {"pass": "✓", "fail": "✗", "not_run": "·"}

# Correspondance dimension → marqueurs d'identifiants de modes d'échec. Le schéma
# ne relie pas les modes d'échec aux dimensions : cette table est une heuristique
# de rapprochement, explicite pour être contestable, et non normative.
FAILURE_MODE_MARKERS: dict[str, tuple[str, ...]] = {
    "regime": ("regime", "quantifiab", "fuzzy", "mixed", "seuil"),
    "ruin": ("ruin", "ruine", "veto", "irreversib", "irrevocab", "kelly"),
    "export": ("export", "trace", "journal", "recovery", "stop_condition"),
    "anchoring": ("anchor", "ancrage", "canon", "citation", "selector", "selecteur"),
    "activation": ("activation", "membrane", "over_activ", "sur_activ", "dormant", "shadow"),
    "permission": ("permission", "scope", "portee", "consent", "credential"),
    "weights_honesty": ("weight", "poids", "honesty", "honnete", "integration", "distill"),
    "layer_order": ("layer", "couche", "order", "ordre", "hierarch", "traversal"),
    "cooperation": ("cooperation", "coop", "recompos", "delegation"),
    "contingency": ("contingency", "contingence", "binding", "liaison", "counterargument"),
    "evidence": ("evidence", "preuve", "sufficien", "suffisan", "invente", "fabric"),
    "authority": ("authority", "autorite", "channel", "canal", "instruction_injection"),
}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _normalize_id(value: str) -> str:
    return re.sub(r"[.-]", "_", value.strip().lower())


def _excerpt(text: Any, limit: int = EXCERPT_LIMIT) -> str:
    collapsed = " ".join(str(text).split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"


def _quote_patterns(patterns: list[str]) -> str:
    shown = [f"`{pattern}`" for pattern in patterns[:MAX_LISTED]]
    if len(patterns) > MAX_LISTED:
        shown.append("…")
    return ", ".join(shown)


def _quote_matches(pairs: list[tuple[str, str]]) -> str:
    shown = [f"`{pattern}` → « {_excerpt(found)} »" for pattern, found in pairs[:MAX_LISTED]]
    if len(pairs) > MAX_LISTED:
        shown.append("…")
    return ", ".join(shown)


def _quote_occurrences(values: list[str]) -> str:
    shown = [f"« {_excerpt(value)} »" for value in values[:MAX_LISTED]]
    if len(values) > MAX_LISTED:
        shown.append("…")
    return ", ".join(shown)


def detector_problem(detector: Any) -> str | None:
    """Renvoie la raison pour laquelle un détecteur ne peut pas être appliqué."""
    if detector is None:
        return "détecteur absent : un contrôle déterministe en exige un"
    if not isinstance(detector, dict):
        return "détecteur invalide : mapping attendu"
    kind = detector.get("type")
    if kind not in DETECTOR_TYPES:
        return f"type de détecteur inconnu : attendu {', '.join(DETECTOR_TYPES)}"
    patterns = detector.get("patterns")
    if (
        not isinstance(patterns, list)
        or not patterns
        or not all(isinstance(pattern, str) and pattern for pattern in patterns)
    ):
        return "motifs invalides : liste non vide de chaînes non vides attendue"
    min_count = detector.get("min_count")
    if min_count is not None and (not _is_int(min_count) or min_count < 1):
        return "min_count invalide : entier ≥ 1 attendu"
    for pattern in patterns:
        try:
            re.compile(pattern, DETECTOR_FLAGS)
        except re.error as exc:
            return f"motif non compilable : `{pattern}` — {exc}"
    return None


def apply_detector(detector: dict[str, Any], response_text: str) -> tuple[bool, str]:
    """Applique un détecteur et renvoie (résultat, détail lisible).

    Un détecteur inapplicable renvoie False ici ; score_response le classe
    not_run, parce qu'un instrument cassé n'est pas un échec de la réponse.
    """
    problem = detector_problem(detector)
    if problem is not None:
        return False, problem
    if not isinstance(response_text, str):
        return False, "réponse absente ou non textuelle : aucun détecteur applicable"

    kind = detector["type"]
    patterns: list[str] = list(detector["patterns"])
    compiled = [(pattern, re.compile(pattern, DETECTOR_FLAGS)) for pattern in patterns]

    if kind == "anchor_ids":
        min_count = detector.get("min_count", 1)
        distinct: dict[str, str] = {}
        for _, regex in compiled:
            for match in regex.finditer(response_text):
                occurrence = " ".join(match.group(0).split())
                key = occurrence.casefold()
                if key and key not in distinct:
                    distinct[key] = occurrence
        found = list(distinct.values())
        detail = f"anchor_ids : {len(found)}/{min_count} occurrence(s) distincte(s)"
        if found:
            detail = f"{detail} : {_quote_occurrences(found)}"
        else:
            detail = f"{detail} sur {_quote_patterns(patterns)}"
        return len(found) >= min_count, detail

    hits: list[tuple[str, str]] = []
    missing: list[str] = []
    for pattern, regex in compiled:
        match = regex.search(response_text)
        if match is None:
            missing.append(pattern)
        else:
            hits.append((pattern, match.group(0)))

    if kind == "regex_all":
        if missing:
            return False, (
                f"regex_all : {len(hits)}/{len(patterns)} motif(s) trouvé(s) ; "
                f"manquant(s) : {_quote_patterns(missing)}"
            )
        return True, f"regex_all : {len(hits)}/{len(patterns)} motif(s) — {_quote_matches(hits)}"

    if kind == "regex_any":
        if hits:
            return True, f"regex_any : {_quote_matches(hits[:1])}"
        return False, f"regex_any : aucun des {len(patterns)} motif(s) : {_quote_patterns(patterns)}"

    if hits:
        return False, f"regex_none : anti-motif(s) trouvé(s) : {_quote_matches(hits)}"
    return True, f"regex_none : aucun des {len(patterns)} anti-motif(s) trouvé"


def scenario_problems(
    scenario: Any, judged: dict[str, str] | None = None
) -> list[validate.ValidationError]:
    """Signale ce qui empêche de noter le scénario tel qu'il est écrit."""
    errors: list[validate.ValidationError] = []
    source = str(_mapping(scenario).get("scenario_id") or "scenario")
    checks = _mapping(scenario).get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append(
            validate.ValidationError("checks", source, "aucun contrôle à appliquer")
        )
        return errors

    judged_ids: set[str] = set()
    for index, raw_check in enumerate(checks):
        path = f"{source}.checks[{index}]"
        if not isinstance(raw_check, dict):
            errors.append(validate.ValidationError("check_type", path, "mapping attendu"))
            continue
        check_id = raw_check.get("check_id")
        if not isinstance(check_id, str) or not check_id.strip():
            errors.append(
                validate.ValidationError("check_id", path, "identifiant de contrôle absent")
            )
        kind = raw_check.get("kind")
        if kind not in CHECK_KINDS:
            errors.append(
                validate.ValidationError(
                    "check_kind", path, f"attendu {' ou '.join(CHECK_KINDS)}"
                )
            )
            continue
        weight = raw_check.get("weight")
        if not _is_int(weight) or not 1 <= weight <= 10:
            errors.append(
                validate.ValidationError("check_weight", path, "entier attendu dans [1,10]")
            )
        if kind == "deterministic":
            problem = detector_problem(raw_check.get("detector"))
            if problem is not None:
                errors.append(validate.ValidationError("detector", path, problem))
        elif isinstance(check_id, str):
            judged_ids.add(check_id)

    for check_id, verdict in (judged or {}).items():
        if check_id not in judged_ids:
            errors.append(
                validate.ValidationError(
                    "judged_unknown_check",
                    f"{source}.checks",
                    f"verdict fourni pour un contrôle jugé inexistant : {check_id}",
                )
            )
        elif verdict not in JUDGED_VERDICTS:
            errors.append(
                validate.ValidationError(
                    "judged_verdict",
                    f"{source}.checks.{check_id}",
                    f"verdict « {verdict} » non reconnu ; attendu {', '.join(JUDGED_VERDICTS)}",
                )
            )
    return errors


def score_response(
    scenario: dict[str, Any],
    response_text: str,
    judged: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Produit le bloc scoring de trial-v1, sans scored_at (l'appelant l'ajoute)."""
    verdicts = {str(key): value for key, value in (judged or {}).items()}
    raw_checks = _mapping(scenario).get("checks")
    checks: list[dict[str, Any]] = []
    totals = {
        kind: {"passed": 0, "failed": 0, "not_run": 0, "weighted_score": 0, "weighted_max": 0}
        for kind in CHECK_KINDS
    }

    for raw_check in raw_checks if isinstance(raw_checks, list) else []:
        check = _mapping(raw_check)
        kind = check.get("kind")
        # Un kind hors énumération est signalé par scenario_problems et exclu :
        # l'inclure produirait un essai non conforme à trial-v1.
        if kind not in CHECK_KINDS:
            continue
        check_id = check.get("check_id")
        check_id = check_id if isinstance(check_id, str) else ""
        weight = check.get("weight")
        weight = weight if _is_int(weight) and 1 <= weight <= 10 else 0

        if kind == "deterministic":
            detector = check.get("detector")
            problem = detector_problem(detector)
            if problem is not None:
                result, detail = "not_run", problem
            else:
                passed, detail = apply_detector(detector, response_text)
                result = "pass" if passed else "fail"
        else:
            verdict = verdicts.get(check_id)
            if verdict is None:
                result = "not_run"
                detail = "jugé : aucun verdict fourni — non exécuté, jamais compté comme réussi"
            elif verdict in JUDGED_VERDICTS:
                result = verdict
                detail = (
                    f"jugé : verdict {verdict} fourni par l'appelant ; la provenance du juge "
                    "est consignée dans scoring.scorer.judge"
                )
            else:
                result = "not_run"
                detail = (
                    f"jugé : verdict « {verdict} » non reconnu "
                    f"({', '.join(JUDGED_VERDICTS)}) — traité comme non exécuté"
                )

        bucket = totals[kind]
        bucket["passed" if result == "pass" else "failed" if result == "fail" else "not_run"] += 1
        if result == "pass":
            bucket["weighted_score"] += weight
        # weighted_max compte aussi les not_run : sinon un contrôle non exécuté
        # gonflerait le taux de réussite au lieu de le laisser incomplet.
        bucket["weighted_max"] += weight
        checks.append(
            {
                "check_id": check_id,
                "kind": kind,
                "weight": weight,
                "result": result,
                "detail": detail,
            }
        )

    return {
        "scorer": {"deterministic_scorer": SCORER_VERSION},
        "checks": checks,
        "deterministic": totals["deterministic"],
        "judged": totals["judged"],
        "failure_modes_triggered": triggered_failure_modes(scenario, checks),
    }


def triggered_failure_modes(
    scenario: dict[str, Any], checks_result: list[dict[str, Any]]
) -> list[str]:
    """Modes d'échec rapprochés des contrôles en échec, par identifiant puis par dimension."""
    dimensions: dict[str, str] = {}
    raw_checks = _mapping(scenario).get("checks")
    for raw_check in raw_checks if isinstance(raw_checks, list) else []:
        check = _mapping(raw_check)
        check_id = check.get("check_id")
        dimension = check.get("dimension")
        if isinstance(check_id, str) and isinstance(dimension, str):
            dimensions[check_id] = dimension

    failed_ids: set[str] = set()
    markers: set[str] = set()
    for entry in checks_result:
        if entry.get("result") != "fail":
            continue
        check_id = str(entry.get("check_id") or "")
        normalized = _normalize_id(check_id)
        if normalized:
            failed_ids.add(normalized)
        markers.update(FAILURE_MODE_MARKERS.get(dimensions.get(check_id, ""), ()))

    triggered: set[str] = set()
    raw_modes = _mapping(scenario).get("failure_modes")
    for raw_mode in raw_modes if isinstance(raw_modes, list) else []:
        mode_id = _mapping(raw_mode).get("id")
        if not isinstance(mode_id, str) or not mode_id:
            continue
        normalized = _normalize_id(mode_id)
        direct = any(
            normalized == failed or normalized in failed or failed in normalized
            for failed in failed_ids
        )
        if direct or any(marker in normalized for marker in markers):
            triggered.add(mode_id)
    return sorted(triggered)


def corpus_eligibility(scenario: dict[str, Any], scoring: dict[str, Any]) -> dict[str, Any]:
    """Porte de distillation : dit si l'essai peut nourrir le corpus, et pourquoi."""
    deterministic = _mapping(scoring.get("deterministic"))
    judged = _mapping(scoring.get("judged"))
    passed = deterministic.get("passed") if _is_int(deterministic.get("passed")) else 0
    failed = deterministic.get("failed") if _is_int(deterministic.get("failed")) else 0
    not_run = deterministic.get("not_run") if _is_int(deterministic.get("not_run")) else 0
    total = passed + failed + not_run

    severities: dict[str, str] = {}
    raw_modes = _mapping(scenario).get("failure_modes")
    for raw_mode in raw_modes if isinstance(raw_modes, list) else []:
        mode = _mapping(raw_mode)
        mode_id = mode.get("id")
        severity = mode.get("severity")
        if isinstance(mode_id, str) and isinstance(severity, str):
            severities[mode_id] = severity
    triggered = scoring.get("failure_modes_triggered")
    triggered = triggered if isinstance(triggered, list) else []
    disqualifying = sorted(
        str(mode_id) for mode_id in triggered if severities.get(str(mode_id)) == DISQUALIFYING
    )

    sft = total > 0 and failed == 0 and not_run == 0 and not disqualifying
    # Un verdict déterministe complet est requis des deux côtés d'une paire :
    # un essai partiellement noté ne peut être ni le préféré ni le rejeté.
    preference_candidate = total > 0 and not_run == 0

    weighted = (
        f"poids {deterministic.get('weighted_score', 0)}/{deterministic.get('weighted_max', 0)}"
    )
    if sft:
        parts = [
            f"éligible SFT : {passed}/{total} contrôle(s) déterministe(s) réussi(s) "
            f"({weighted}), aucun non exécuté, aucun mode disqualifiant déclenché"
        ]
    else:
        causes: list[str] = []
        if total == 0:
            causes.append("aucun contrôle déterministe applicable")
        if failed:
            causes.append(f"{failed} contrôle(s) déterministe(s) en échec")
        if not_run:
            causes.append(f"{not_run} contrôle(s) déterministe(s) non exécuté(s)")
        if disqualifying:
            causes.append(f"mode(s) disqualifiant(s) déclenché(s) : {', '.join(disqualifying)}")
        parts = [f"inéligible SFT : {', '.join(causes)} ({weighted})"]

    if preference_candidate:
        parts.append(
            "candidat de préférence : verdict déterministe complet ; une paire n'existe que "
            "si un second essai réel du même scénario existe"
        )
    else:
        parts.append(
            "non candidat de préférence : verdict déterministe incomplet ou absent"
        )

    judged_not_run = judged.get("not_run") if _is_int(judged.get("not_run")) else 0
    if judged_not_run:
        parts.append(
            f"{judged_not_run} contrôle(s) jugé(s) non exécuté(s), reportés tels quels et "
            "sans effet sur l'éligibilité"
        )

    return {"sft": sft, "preference_candidate": preference_candidate, "reason": " ; ".join(parts)}


def parse_judged(raw: str | None) -> tuple[dict[str, str], list[validate.ValidationError]]:
    errors: list[validate.ValidationError] = []
    verdicts: dict[str, str] = {}
    if not raw:
        return verdicts, errors
    for item in raw.split(","):
        entry = item.strip()
        if not entry:
            continue
        if "=" not in entry:
            errors.append(
                validate.ValidationError("judged_argument", "--judged", f"attendu check_id=verdict : {entry}")
            )
            continue
        check_id, _, verdict = entry.partition("=")
        verdicts[check_id.strip()] = verdict.strip()
    return verdicts, errors


def render_text(result: dict[str, Any]) -> str:
    lines: list[str] = []
    scoring = result.get("scoring")
    if isinstance(scoring, dict):
        lines.append(
            f"Scénario {result.get('scenario_id')} — {len(scoring['checks'])} contrôle(s) "
            f"· {SCORER_VERSION}"
        )
        for check in scoring["checks"]:
            symbol = RESULT_SYMBOLS.get(check["result"], "?")
            lines.append(
                f"  {symbol} {check['check_id']} [{check['kind']} w={check['weight']}] — "
                f"{check['detail']}"
            )
        for kind, label in (("deterministic", "Déterministe"), ("judged", "Jugé")):
            totals = scoring[kind]
            lines.append(
                f"{label} : {totals['passed']} réussi(s), {totals['failed']} échec(s), "
                f"{totals['not_run']} non exécuté(s) — poids "
                f"{totals['weighted_score']}/{totals['weighted_max']}"
            )
        modes = scoring["failure_modes_triggered"]
        lines.append(
            f"Modes d'échec déclenchés : {', '.join(modes) if modes else 'aucun'} "
            "(rapprochement heuristique, non normatif)"
        )
        eligibility = result["corpus_eligibility"]
        lines.append(
            f"Corpus : sft={'oui' if eligibility['sft'] else 'non'}, "
            f"préférence={'oui' if eligibility['preference_candidate'] else 'non'} — "
            f"{eligibility['reason']}"
        )
        lines.append(f"Réponse sha256 : {result.get('response_sha256')}")
    if result["errors"]:
        lines.append(f"ÉCHEC — {len(result['errors'])} erreur(s) :")
        lines.extend(
            f"  ✗ {item['code']} [{item['path']}] — {item['detail']}" for item in result["errors"]
        )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    parser.add_argument("--judged", help="verdicts jugés : check_id=pass,autre=not_run")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    errors: list[validate.ValidationError] = []
    verdicts, judged_errors = parse_judged(args.judged)
    errors.extend(judged_errors)

    scenario: Any = None
    try:
        scenario = validate.load_path(args.scenario)
    except (OSError, yaml.YAMLError) as exc:
        errors.append(validate.ValidationError("yaml_input", str(args.scenario), str(exc)))
    try:
        response_text = args.response.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(validate.ValidationError("response_input", str(args.response), str(exc)))
        response_text = None

    result: dict[str, Any] = {
        "checker": CHECKER,
        "ok": False,
        "scenario_id": None,
        "response_sha256": None,
        "scoring": None,
        "corpus_eligibility": None,
        "errors": [],
    }
    if isinstance(scenario, dict) and response_text is not None:
        if not response_text.strip():
            errors.append(
                validate.ValidationError(
                    "empty_response", str(args.response), "réponse vide : rien à noter"
                )
            )
        errors.extend(scenario_problems(scenario, verdicts))
        scoring = score_response(scenario, response_text, verdicts)
        result["scenario_id"] = scenario.get("scenario_id")
        result["response_sha256"] = validate.sha256_text(response_text)
        result["scoring"] = scoring
        result["corpus_eligibility"] = corpus_eligibility(scenario, scoring)
    elif scenario is not None and not isinstance(scenario, dict):
        errors.append(
            validate.ValidationError("scenario_type", str(args.scenario), "mapping attendu")
        )

    result["errors"] = [item.as_dict() for item in errors]
    result["ok"] = not errors
    print(
        json.dumps(result, ensure_ascii=False, sort_keys=True)
        if args.format == "json"
        else render_text(result)
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
