#!/usr/bin/env python3
"""Juge aveugle des contrôles jugés de M3C3-bench.

Le juge reçoit l'énoncé, la réponse et la grille du contrôle. Il ne reçoit ni le
bras d'exposition, ni l'identité du sujet, ni les réponses des autres bras, ni
les autres contrôles du scénario, ni ses modes d'échec — ces derniers nommeraient
le cadre et transformeraient le juge en vérificateur de conformité au lieu d'un
lecteur de la grille.

Le juge s'exécute depuis un répertoire de travail neutre, sans ce dépôt attaché
et sans outils : il est donc lui aussi aveugle à M3C3. Un juge exposé au cadre
noterait contre le cadre plutôt que contre la grille du scénario.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml

BENCH_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_ROOT))

import validate as v  # noqa: E402

JUDGEMENTS_DIR = BENCH_ROOT / "judgements"
JUDGE_HARNESS = "claude-code-cli -p --disable-slash-commands --allowedTools '' (cwd neutre, hors dépôt)"
DEFAULT_JUDGE_MODEL = "claude-opus-5"

# Le juge ne voit rien d'autre. Toute addition ici doit être reportée dans
# blinding.material_supplied du jugement produit, sans quoi l'attestation ment.
MATERIAL_SUPPLIED = ["task_prompt", "response_text", "rubric", "assertion"]

PROMPT_TEMPLATE = """Tu évalues une réponse au regard d'une grille précise.

Tu ne sais rien de l'auteur de cette réponse ni des conditions dans lesquelles elle a été produite, et tu n'as pas à le deviner. Juge le texte tel qu'il est, uniquement contre la grille fournie.

## Demande à laquelle la réponse répond

{task_prompt}

## Réponse à évaluer

{response_text}

## Grille d'évaluation

Critère : {assertion}

{rubric}

## Format de sortie

Ligne 1 : exactement un mot — PASS, FAIL ou INCERTAIN.
Ligne 2 : une ou deux phrases citant ce qui, dans la réponse, fonde ton verdict.

N'écris rien d'autre. Utilise INCERTAIN seulement si la grille ne permet pas de trancher, jamais pour éviter de choisir."""


def build_prompt(task_prompt: str, response_text: str, check: dict) -> str:
    return PROMPT_TEMPLATE.format(
        task_prompt=task_prompt.strip(),
        response_text=response_text.strip(),
        assertion=check["assertion"].strip(),
        rubric=check["rubric"].strip(),
    )


def parse_verdict(raw: str) -> tuple[str, str]:
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        return "not_run", "le juge n'a produit aucune sortie exploitable"
    head = lines[0].upper().strip(" .:*#-")
    rationale = " ".join(lines[1:]).strip() or "aucune justification fournie par le juge"
    if head.startswith("PASS"):
        return "pass", rationale
    if head.startswith("FAIL"):
        return "fail", rationale
    # Tout ce qui n'est pas un verdict net reste not_run : un juge qui n'a pas
    # tranché ne peut jamais être compté comme ayant validé.
    return "not_run", f"verdict non net ({lines[0][:80]!r}) — {rationale}"


def call_judge(prompt: str, model: str, workdir: Path) -> tuple[str, str]:
    with tempfile.TemporaryDirectory(dir=workdir) as neutral:
        completed = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", model,
                "--disable-slash-commands",
                "--allowedTools", "",
            ],
            cwd=neutral,
            capture_output=True,
            text=True,
            timeout=600,
        )
    raw = (completed.stdout or "").strip()
    if completed.returncode != 0 or not raw or "API Error" in raw:
        detail = (raw or completed.stderr or "").strip()[:200]
        return "not_run", f"appel du juge en échec : {detail or 'sortie vide'}"
    return parse_verdict(raw)


def judged_checks(scenario: dict) -> list[dict]:
    return [check for check in scenario["checks"] if check["kind"] == "judged"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--judge-name", default=None, help="défaut : le modèle du juge")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--write", action="store_true", help="écrire les jugements")
    parser.add_argument(
        "--retry-unruled",
        action="store_true",
        help="rejouer les verdicts non rendus en publiant un jugement qui les remplace",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv or sys.argv[1:])

    judge_name = args.judge_name or args.judge_model
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = now[:10]

    scenarios, scenario_errors = v.load_scenarios()
    trials, trial_errors = v.load_trials()
    if scenario_errors or trial_errors:
        print("registre invalide — jugement refusé", file=sys.stderr)
        return 1
    by_id = {scenario["scenario_id"]: scenario for scenario in scenarios}

    existing: set[tuple] = set()
    unruled: dict[tuple, str] = {}
    superseded: set[str] = set()
    if JUDGEMENTS_DIR.is_dir():
        documents = [v.load_path(path) for path in v.record_paths(JUDGEMENTS_DIR)]
        for document in documents:
            superseded.update(document.get("supersedes") or [])
        for document in documents:
            key = (
                document.get("trial_id"),
                document.get("check_id"),
                (document.get("judge") or {}).get("name"),
            )
            existing.add(key)
            if document.get("verdict") == "not_run" and document["judgement_id"] not in superseded:
                unruled[key] = document["judgement_id"]

    work = []
    for trial in sorted(trials, key=lambda item: item["trial_id"]):
        scenario = by_id[trial["scenario_id"]]
        for check in judged_checks(scenario):
            key = (trial["trial_id"], check["check_id"], judge_name)
            if key in existing:
                # Un verdict non rendu (appel en échec, sortie inexploitable) est
                # rejouable : la reprise publie un NOUVEAU jugement qui remplace
                # la tentative, laquelle reste au dossier. On ne réécrit jamais un
                # enregistrement pour effacer la trace d'un échec.
                if args.retry_unruled and key in unruled:
                    work.append((trial, scenario, check, unruled[key]))
                continue
            work.append((trial, scenario, check, None))

    if not work:
        print("aucun contrôle jugé en attente")
        return 0

    workdir = Path(tempfile.mkdtemp(prefix="judge-"))
    print(f"{len(work)} contrôle(s) à juger · juge {judge_name} · aveugle au bras et au sujet")

    def judge_one(item):
        trial, scenario, check, replaces = item
        prompt = build_prompt(scenario["task"]["prompt"], trial["response"]["text"], check)
        verdict, rationale = call_judge(prompt, args.judge_model, workdir)
        return trial, scenario, check, verdict, rationale, replaces

    results = list(ThreadPoolExecutor(max_workers=args.workers).map(judge_one, work))

    JUDGEMENTS_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for trial, scenario, check, verdict, rationale, replaces in results:
        short = trial["trial_id"].replace("pilot-", "").replace("full-", "").replace(f"-{stamp}", "")
        suffix = "-bis" if replaces else ""
        judgement_id = f"j-{short}-{check['check_id']}{suffix}-{stamp}"[:128]
        document = {
            "schema_version": 1,
            "kind": "m3c3_bench_judgement",
            "judgement_id": judgement_id,
            "created_at": now,
            "trial_id": trial["trial_id"],
            "scenario_id": scenario["scenario_id"],
            "check_id": check["check_id"],
            "response_sha256": trial["response"]["text_sha256"],
            "judge": {
                "kind": "model",
                "name": judge_name,
                "harness": JUDGE_HARNESS,
                "model_version": "unknown",
            },
            "blinding": {
                "arm_withheld": True,
                "subject_withheld": True,
                "other_arms_withheld": True,
                "framework_material_withheld": True,
                "material_supplied": MATERIAL_SUPPLIED,
            },
            "verdict": verdict,
            "rationale": rationale[:2000],
            **({"supersedes": [replaces]} if replaces else {}),
            "limitations": [
                "Juge modèle, non humain : il reproduit une lecture de grille, il ne la garantit pas.",
                "Juge unique par contrôle : aucun accord inter-juges n'est mesuré, donc la fiabilité "
                "du verdict n'est pas établie.",
                "L'identité exacte du juge n'est pas vérifiable depuis le harnais ; model_version "
                "reste unknown, comme pour les sujets.",
                "Le juge ne voit pas les modes d'échec du scénario : il note la grille, pas la "
                "conformité au cadre.",
            ],
        }
        if args.write:
            (JUDGEMENTS_DIR / f"{judgement_id}.yaml").write_text(
                yaml.safe_dump(document, allow_unicode=True, sort_keys=False, width=100),
                encoding="utf-8",
            )
        written.append(document)

    tally = {"pass": 0, "fail": 0, "not_run": 0}
    for document in written:
        tally[document["verdict"]] += 1

    if args.format == "json":
        print(json.dumps({"judgements": len(written), "tally": tally}, ensure_ascii=False, sort_keys=True))
    else:
        for document in sorted(written, key=lambda item: item["judgement_id"]):
            mark = {"pass": "✓", "fail": "✗", "not_run": "·"}[document["verdict"]]
            print(f"  {mark} {document['verdict']:<8} {document['trial_id'][:46]:46} {document['check_id']}")
        print(f"\npass={tally['pass']} fail={tally['fail']} not_run={tally['not_run']}"
              + ("" if args.write else "  (essai à blanc — rien écrit, utiliser --write)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
