#!/usr/bin/env python3
"""Construit les enregistrements d'essai depuis les sorties brutes d'une campagne.

Le scoring déterministe vient de score.py. Les contrôles jugés restent not_run
ici : ils sont tranchés séparément par judge.py, dans des enregistrements de
jugement additifs qui ne touchent jamais l'essai.

Une cellule sans sortie exploitable n'est pas écrite. L'agrégat doit voir un
trou et le compter comme tel, jamais une valeur inventée pour compléter la grille.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

BENCH_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_ROOT))

import score  # noqa: E402
import validate as v  # noqa: E402

REPO_ROOT = v.REPO_ROOT
HARNESS = (
    "claude-code-cli -p --disable-slash-commands --allowedTools '' "
    "(répertoire de travail neutre, dépôt non attaché)"
)

EXPOSURE = {
    "A_placebo": {"channels": ["none"], "paths": []},
    "B_adapter": {"channels": ["instruction"], "paths": ["CLAUDE.md"]},
    "C_canonical": {"channels": ["instruction", "context"], "paths": ["CLAUDE.md", "master.yaml"]},
    "D_candidate": {
        "channels": ["instruction", "context"],
        "paths": ["CLAUDE.md", "continuum/weights/proposal/bench_informed_v2_2_0-candidate.yaml"],
    },
    "D2_candidate": {
        "channels": ["instruction", "context"],
        "paths": ["CLAUDE.md", "continuum/weights/proposal/bench_informed_v2_3_0-candidate.yaml"],
    },
}

CELL_RE = re.compile(r"^(?P<scenario>.+)\.(?P<arm>A_placebo|B_adapter|C_canonical|D_candidate|D2_candidate)\.r(?P<rep>\d+)$")

COMMON_LIMITATIONS = [
    "L'identité exacte du sujet n'est pas pleinement établie depuis l'intérieur du "
    "harnais : le CLI rapporte claude-opus-5 comme modèle principal et fait aussi "
    "intervenir claude-haiku-4-5 en auxiliaire. model_version reste unknown.",
    "Les contrôles jugés sont enregistrés not_run dans l'essai : ils sont tranchés "
    "séparément par des jugements aveugles, et un contrôle non tranché ne vaut jamais réussi.",
    "Le confondant de volume déclaré dans arms.yaml n'est pas mitigé : le bras "
    "C_canonical reçoit environ 38 Ko de texte structuré de plus que le bras A, sans "
    "bras à volume apparié pour départager le contenu du cadre de sa masse.",
    "Les réplicats varient par le seul échantillonnage du modèle : ni la température "
    "ni la graine ne sont contrôlées par ce harnais, donc la dispersion observée "
    "mélange variabilité du sujet et variabilité de décodage.",
]

ARM_LIMITATIONS = {
    "A_placebo": [
        "Aveuglement structurel : sujet exécuté depuis un répertoire de travail neutre, "
        "sans ce dépôt attaché, sans outils et sans instruction de projet. L'aveuglement "
        "ne repose pas sur la rédaction de l'invite."
    ],
    "B_adapter": [
        "L'adaptateur est injecté par --append-system-prompt, donc comme instruction "
        "réelle du sujet et non comme texte cité dans l'énoncé."
    ],
    "C_canonical": [
        "master.yaml est injecté en tête de l'invite utilisateur, donc par canal de "
        "contexte, l'adaptateur restant sur le canal d'instruction."
    ],
    "D2_candidate": [
        "Le document d'autorité est un CANDIDAT non activé (v2.3.0, itération "
        "garde-première), pas le canon : master.yaml reste l'autorité du dépôt et "
        "l'activation appartient à l'émetteur désigné.",
        "L'en-tête de commentaires du fichier est retiré avant présentation au "
        "sujet (mécanisme mesuré en v2.2 : un corps auto-déclaré candidat "
        "s'invoque mal comme verrou) ; l'empreinte enregistrée est celle du "
        "fichier complet du dépôt, la transformation est déclarée dans arms.yaml.",
        "Le candidat est informé par les résultats de famille de deux campagnes "
        "sur ces mêmes scénarios : il vise des mécanismes, pas des détecteurs, "
        "mais la confirmation finale exige des scénarios rédigés sans "
        "connaissance de ce document.",
    ],
    "D_candidate": [
        "Le document d'autorité est un CANDIDAT non activé, pas le canon : "
        "master.yaml reste l'autorité opérationnelle et l'activation appartient "
        "à l'émetteur désigné.",
        "Les additions du candidat ont été choisies après avoir vu les résultats "
        "d'une campagne antérieure : l'écart D−C mesuré sur les scénarios déjà "
        "joués est contaminé, seul celui mesuré sur des scénarios rédigés sans "
        "connaissance du candidat est recevable.",
    ],
}


def head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


# Messages émis par le HARNAIS, jamais par le sujet. Les accepter fabriquerait
# des essais scorés à zéro qui rempliraient la grille sans rien mesurer — une
# campagne qui paraît complète alors qu'aucune réponse n'a été produite. C'est
# le mode de corruption le plus dangereux du dispositif, parce qu'il est
# silencieux : rien dans un score bas ne signale que le sujet n'a jamais répondu.
HARNESS_NOISE = (
    ("API Error", "refus ou erreur de l'API"),
    ("session limit", "quota de session atteint — aucune réponse produite"),
    ("usage limit", "quota d'usage atteint — aucune réponse produite"),
    ("rate limit", "limitation de débit — aucune réponse produite"),
    ("no stdin data received", "bruit de harnais dans la sortie"),
    ("Invalid API key", "authentification en échec"),
    ("Credit balance is too low", "crédit épuisé"),
)
# Une réponse plus courte que ce seuil ne peut pas satisfaire un scénario du
# bench : les énoncés demandent une décision argumentée, pas un accusé de
# réception. Le seuil est choisi, pas dérivé.
MINIMUM_RESPONSE_CHARS = 200


def usable(text: str) -> str | None:
    """Retourne None si la sortie est une réponse du sujet, sinon le motif du rejet."""
    if not text.strip():
        return "sortie vide"
    lowered = text.lower()
    for needle, reason in HARNESS_NOISE:
        if needle.lower() in lowered:
            return reason
    if len(text.strip()) < MINIMUM_RESPONSE_CHARS:
        return f"réponse trop courte ({len(text.strip())} caractères) pour être une réponse au scénario"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path, default=Path("/tmp/bench-campaign/responses"))
    parser.add_argument("--prefix", default="full", help="préfixe des trial_id")
    parser.add_argument("--stamp", default=None, help="date des trial_id (défaut : aujourd'hui)")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv or sys.argv[1:])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = args.stamp or now[:10]
    commit = head_commit()

    scenarios, errors = v.load_scenarios()
    if errors:
        print("registre de scénarios invalide — construction refusée", file=sys.stderr)
        return 1
    by_id = {scenario["scenario_id"]: scenario for scenario in scenarios}
    arms_document = v.load_path(v.ARMS_PATH)

    trials_dir = v.TRIALS_DIR
    if args.write:
        trials_dir.mkdir(parents=True, exist_ok=True)

    written, skipped = [], []
    for path in sorted(args.responses.glob("*.txt")):
        match = CELL_RE.match(path.stem)
        if not match:
            continue
        sid, arm, rep = match["scenario"], match["arm"], match["rep"]
        scenario = by_id.get(sid)
        if scenario is None:
            skipped.append((path.stem, "scénario inconnu"))
            continue

        text = path.read_text(encoding="utf-8")
        problem = usable(text)
        if problem:
            skipped.append((path.stem, problem))
            continue

        scoring = score.score_response(scenario, text)
        scoring["scored_at"] = now
        eligibility = score.corpus_eligibility(scenario, scoring)

        latency = None
        meta = path.with_suffix(".meta")
        if meta.is_file():
            for line in meta.read_text(encoding="utf-8").splitlines():
                if line.startswith("latency_ms="):
                    latency = int(line.split("=", 1)[1])

        response = {"text": text, "text_sha256": v.sha256_text(text)}
        if latency is not None:
            response["latency_ms"] = latency

        exposure = EXPOSURE[arm]
        trial_id = f"{args.prefix}-{sid}-{arm.lower().replace('_', '-')}-r{rep}-{stamp}"
        trial = {
            "schema_version": 1,
            "kind": "m3c3_bench_trial",
            "trial_id": trial_id,
            "created_at": now,
            "scenario_id": sid,
            "scenario_sha256": v.file_sha256(v.SCENARIOS_DIR / f"{sid}.yaml"),
            "arm": arm,
            "arm_sha256": v.value_sha256(arms_document["arms"][arm]),
            "subject": {
                "provider": "Anthropic",
                "model": "claude-opus-5",
                "model_version": "unknown",
                "harness": HARNESS,
            },
            "exposure": {
                "channels": exposure["channels"],
                "artifacts": [
                    {
                        "path": artifact,
                        "commit": commit,
                        "content_sha256": v.file_sha256(REPO_ROOT / artifact),
                    }
                    for artifact in exposure["paths"]
                ],
            },
            "response": response,
            "scoring": scoring,
            "corpus_eligibility": eligibility,
            "limitations": COMMON_LIMITATIONS + ARM_LIMITATIONS[arm],
        }
        if args.write:
            (trials_dir / f"{trial_id}.yaml").write_text(
                yaml.safe_dump(trial, allow_unicode=True, sort_keys=False, width=100),
                encoding="utf-8",
            )
        det = scoring["deterministic"]
        written.append(
            {
                "trial_id": trial_id,
                "scenario_id": sid,
                "arm": arm,
                "score": det["weighted_score"],
                "max": det["weighted_max"],
                "sft": eligibility["sft"],
            }
        )

    if args.format == "json":
        print(json.dumps({"written": len(written), "skipped": skipped}, ensure_ascii=False, sort_keys=True))
    else:
        print(f"essais construits : {len(written)}" + ("" if args.write else "  (essai à blanc)"))
        print(f"cellules écartées : {len(skipped)}")
        for cell, why in skipped:
            print(f"  ✗ {cell} — {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
