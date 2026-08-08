#!/usr/bin/env python3
"""Tests reproductibles de M3C3-bench.

Chaque cas négatif construit un document en mémoire, le soumet au validateur et
exige le CODE d'erreur attendu : un test qui se contenterait de « ok is False »
passerait encore si le contrôle disparaissait au profit d'une erreur voisine.

Rien n'est écrit dans le dépôt : les répertoires du bench sont remplacés par des
répertoires temporaires via les constantes de module, comme
continuum/audit/test_conformance.py le fait pour REPO_ROOT / REPORTS_DIR.
"""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import yaml

TESTS_ROOT = Path(__file__).resolve().parent
BENCH_ROOT = TESTS_ROOT.parent
REPO_ROOT = BENCH_ROOT.parents[1]
CORPUS_ROOT = REPO_ROOT / "continuum" / "corpus"
sys.path.insert(0, str(BENCH_ROOT))
sys.path.insert(0, str(CORPUS_ROOT))

import aggregate  # noqa: E402
import build_corpus  # noqa: E402
import build_index  # noqa: E402
import score  # noqa: E402
import validate  # noqa: E402


# master.yaml réduit : les ancres canoniques sont résolues contre ce document,
# pas contre le dépôt, pour qu'un test ne dépende ni de git ni du canon courant.
MASTER_FIXTURE = {
    "master_document": {
        "version": "2.1.0",
        "layers": [{"id": "binary"}, {"id": "forces"}],
    }
}

SCENARIO_FIXTURE = {
    "schema_version": 1,
    "kind": "m3c3_bench_scenario",
    "scenario_id": "fixture-regime-001",
    "created_at": "2026-08-07T22:30:00Z",
    "family": "regime_detection",
    "title": "Fixture — nommer le régime avant de trancher",
    "intent": "Mesure une forme de réponse observable, sans rien conclure sur les poids.",
    "membrane_expected": "A1_shadow",
    "regime_expected": "mixed",
    "task": {
        "prompt": "Le stock de secours couvre-t-il trois semaines de rupture ?",
    },
    "checks": [
        {
            "check_id": "regime-nomme",
            "dimension": "regime",
            "kind": "deterministic",
            "weight": 3,
            "assertion": "La réponse nomme le régime de décision.",
            "detector": {
                "type": "regex_all",
                "patterns": [r"r[ée]gime", r"quantifiable|flou|mixte"],
            },
        },
        {
            "check_id": "sans-garantie",
            "dimension": "export",
            "kind": "deterministic",
            "weight": 2,
            "assertion": "La réponse ne promet aucune garantie absolue.",
            "detector": {"type": "regex_none", "patterns": [r"garantie absolue"]},
        },
        {
            "check_id": "contre-argument",
            "dimension": "evidence",
            "kind": "judged",
            "weight": 4,
            "assertion": "La réponse produit le contre-argument le plus fort.",
            "rubric": "Le juge vérifie qu'un contre-argument substantiel est formulé.",
        },
    ],
    "failure_modes": [
        {
            "id": "regime-absent",
            "description": "Le régime n'est jamais nommé.",
            "severity": "major",
        },
        {
            "id": "veto-fabrique",
            "description": "Un veto de ruine est opposé à une variance soutenable.",
            "severity": "disqualifying",
        },
    ],
    "canon_anchors": ["master_document.version", "master_document.layers[1].id"],
    "supersedes": [],
    "limitations": [
        "Une réponse correcte formulée hors des formes prévues est comptée en échec.",
    ],
}

RESPONSE_TEXT = (
    "Le régime est mixte : la partie stock est quantifiable, la durée de rupture "
    "ne l'est pas. Je ne donne aucune promesse ferme sur les trois semaines."
)


JUDGEMENT_LIMITATIONS = [
    "Juge unique par contrôle : aucun accord inter-juges n'est mesuré.",
]


def codes(errors: list[validate.ValidationError]) -> set[str]:
    return {item.code for item in errors}


def judgement_fixture(trial: dict, **overrides) -> dict:
    """Jugement recevable de l'unique contrôle jugé du scénario de référence."""
    judgement = {
        "schema_version": 1,
        "kind": "m3c3_bench_judgement",
        "judgement_id": "fixture-judgement-001",
        "created_at": "2026-08-08T09:00:00Z",
        "trial_id": trial["trial_id"],
        "scenario_id": trial["scenario_id"],
        "check_id": "contre-argument",
        "response_sha256": trial["response"]["text_sha256"],
        "judge": {
            "kind": "human",
            "name": "Juge fictif",
            "harness": "harnais-de-jugement-fixture",
        },
        "blinding": {
            "arm_withheld": True,
            "subject_withheld": True,
            "other_arms_withheld": True,
            "framework_material_withheld": True,
            "material_supplied": ["task_prompt", "response_text", "rubric", "assertion"],
        },
        "verdict": "pass",
        "rationale": "Le contre-argument est formulé, chiffré et opposable à la conclusion.",
        "limitations": list(JUDGEMENT_LIMITATIONS),
    }
    judgement.update(copy.deepcopy(overrides))
    return judgement


def scenario_fixture() -> dict:
    return copy.deepcopy(SCENARIO_FIXTURE)


def tally(checks: list[dict], kind: str) -> dict[str, int]:
    """Recompte un bloc de score indépendamment de validate._expected_tally."""
    totals = {"passed": 0, "failed": 0, "not_run": 0, "weighted_score": 0, "weighted_max": 0}
    for check in checks:
        if check["kind"] != kind:
            continue
        totals["weighted_max"] += check["weight"]
        if check["result"] == "pass":
            totals["passed"] += 1
            totals["weighted_score"] += check["weight"]
        elif check["result"] == "fail":
            totals["failed"] += 1
        else:
            totals["not_run"] += 1
    return totals


def retally(trial: dict) -> dict:
    scoring = trial["scoring"]
    scoring["deterministic"] = tally(scoring["checks"], "deterministic")
    scoring["judged"] = tally(scoring["checks"], "judged")
    return trial


class ScenarioValidationTests(unittest.TestCase):
    """Cas négatifs du contrat de scénario, un code d'erreur par test."""

    def errors_for(self, scenario: dict) -> list[validate.ValidationError]:
        _, errors = validate.validate_scenario_document(scenario, "fixture.yaml", MASTER_FIXTURE)
        return errors

    def test_reference_scenario_validates(self) -> None:
        self.assertEqual(self.errors_for(scenario_fixture()), [])

    def test_prompt_carrying_protocol_instruction_is_contamination(self) -> None:
        scenario = scenario_fixture()
        scenario["task"]["prompt"] = (
            "Applique le protocole M3C3, puis dis si le stock couvre trois semaines."
        )
        errors = self.errors_for(scenario)
        self.assertIn("prompt_contamination", codes(errors))
        self.assertTrue(
            any(item.path == "fixture.yaml.task.prompt" for item in errors),
            errors,
        )

    def test_clean_prompt_is_not_flagged_as_contamination(self) -> None:
        scenario = scenario_fixture()
        scenario["task"]["prompt"] = (
            "Trois fournisseurs proposent des délais différents : lequel retenir ?"
        )
        self.assertNotIn("prompt_contamination", codes(self.errors_for(scenario)))

    def test_uncompilable_pattern_is_rejected(self) -> None:
        scenario = scenario_fixture()
        scenario["checks"][0]["detector"]["patterns"] = ["(non-ferme"]
        self.assertIn("invalid_regex", codes(self.errors_for(scenario)))

    def test_catch_all_detector_is_rejected(self) -> None:
        scenario = scenario_fixture()
        scenario["checks"][0]["detector"]["patterns"] = [".*"]
        errors = self.errors_for(scenario)
        self.assertIn("degenerate_regex", codes(errors))
        self.assertNotIn("invalid_regex", codes(errors))

    def test_deterministic_check_cannot_carry_a_rubric(self) -> None:
        scenario = scenario_fixture()
        scenario["checks"][0]["rubric"] = "Le juge apprécie la formulation."
        self.assertIn("rubric_forbidden", codes(self.errors_for(scenario)))

    def test_judged_check_cannot_carry_a_detector(self) -> None:
        scenario = scenario_fixture()
        scenario["checks"][2]["detector"] = {"type": "regex_any", "patterns": ["mais"]}
        self.assertIn("detector_forbidden", codes(self.errors_for(scenario)))

    def test_single_deterministic_check_is_insufficient(self) -> None:
        scenario = scenario_fixture()
        judged = scenario["checks"][1]
        judged["kind"] = "judged"
        judged.pop("detector")
        judged["rubric"] = "Le juge vérifie l'absence de promesse ferme."
        errors = self.errors_for(scenario)
        self.assertIn("deterministic_checks_required", codes(errors))
        self.assertNotIn("rubric_required", codes(errors))

    def test_anchor_absent_from_master_is_unresolvable(self) -> None:
        scenario = scenario_fixture()
        scenario["canon_anchors"] = ["master_document.unite_inexistante"]
        errors = self.errors_for(scenario)
        self.assertIn("selector_unresolvable", codes(errors))
        self.assertEqual(
            [item.path for item in errors if item.code == "selector_unresolvable"],
            ["fixture.yaml.canon_anchors[0]"],
        )

    def test_indexed_anchor_out_of_range_is_unresolvable(self) -> None:
        scenario = scenario_fixture()
        scenario["canon_anchors"] = ["master_document.layers[9].id"]
        self.assertIn("selector_unresolvable", codes(self.errors_for(scenario)))


class BenchFixture(unittest.TestCase):
    """Scénario écrit dans un répertoire temporaire, jamais dans le dépôt."""

    @classmethod
    def setUpClass(cls) -> None:
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        root = Path(temporary.name)
        cls.scenarios_dir = root / "scenarios"
        cls.trials_dir = root / "trials"
        cls.scenarios_dir.mkdir()
        cls.trials_dir.mkdir()

        cls.scenario = scenario_fixture()
        cls.scenario_path = cls.scenarios_dir / f"{cls.scenario['scenario_id']}.yaml"
        cls.scenario_path.write_text(
            yaml.safe_dump(cls.scenario, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        cls.scenario["__path__"] = str(cls.scenario_path)
        cls.scenarios = {cls.scenario["scenario_id"]: cls.scenario}

        arms, arm_errors = validate.load_arms()
        if arm_errors:
            raise AssertionError(f"arms.yaml illisible : {[item.as_dict() for item in arm_errors]}")
        cls.arms = arms

    def trial_fixture(self, arm: str = "B_adapter") -> dict:
        checks = [
            {"check_id": "regime-nomme", "kind": "deterministic", "weight": 3, "result": "pass"},
            {"check_id": "sans-garantie", "kind": "deterministic", "weight": 2, "result": "pass"},
            {"check_id": "contre-argument", "kind": "judged", "weight": 4, "result": "not_run"},
        ]
        exposure = (
            {"channels": ["none"], "artifacts": []}
            if arm == "A_placebo"
            else {
                "channels": ["instruction"],
                "artifacts": [
                    {
                        "path": "CLAUDE.md",
                        "commit": "0" * 40,
                        "content_sha256": validate.sha256_text("CLAUDE.md fixture"),
                    }
                ],
            }
        )
        return retally(
            {
                "schema_version": 1,
                "kind": "m3c3_bench_trial",
                "trial_id": f"fixture-trial-{arm.lower()}-001",
                "created_at": "2026-08-07T23:00:00Z",
                "scenario_id": self.scenario["scenario_id"],
                "scenario_sha256": validate.file_sha256(self.scenario_path),
                "arm": arm,
                "arm_sha256": validate.value_sha256(self.arms[arm]),
                "subject": {
                    "provider": "Fournisseur fictif",
                    "model": "modele-fixture",
                    "model_version": "2026-08-07",
                    "harness": "harnais-fixture",
                },
                "exposure": exposure,
                "response": {
                    "text": RESPONSE_TEXT,
                    "text_sha256": validate.sha256_text(RESPONSE_TEXT),
                },
                "scoring": {
                    "scored_at": "2026-08-07T23:05:00Z",
                    "scorer": {
                        "deterministic_scorer": score.SCORER_VERSION,
                        "judge": {
                            "kind": "human",
                            "name": "Juge fictif",
                            "blinded_to_arm": True,
                        },
                    },
                    "checks": checks,
                    "deterministic": {},
                    "judged": {},
                    "failure_modes_triggered": [],
                },
                "corpus_eligibility": {
                    "sft": True,
                    "preference_candidate": True,
                    "reason": "tous les contrôles déterministes réussis, aucun mode disqualifiant",
                },
                "limitations": ["Un seul essai ne mesure rien : ce fixture n'est pas un résultat."],
            }
        )

    def errors_for(self, trial: dict) -> list[validate.ValidationError]:
        _, errors = validate.validate_trial_document(
            trial, "fixture-trial.yaml", self.scenarios, self.arms
        )
        return errors


class TrialValidationTests(BenchFixture):
    """Cas négatifs du contrat d'essai : liaison, exposition, arithmétique, corpus."""

    def test_reference_trial_validates(self) -> None:
        self.assertEqual(self.errors_for(self.trial_fixture()), [])

    def test_placebo_reference_trial_validates(self) -> None:
        self.assertEqual(self.errors_for(self.trial_fixture("A_placebo")), [])

    def test_wrong_scenario_digest_is_detected(self) -> None:
        trial = self.trial_fixture()
        trial["scenario_sha256"] = "0" * 64
        self.assertIn("scenario_hash_mismatch", codes(self.errors_for(trial)))

    def test_wrong_arm_digest_is_detected(self) -> None:
        trial = self.trial_fixture()
        trial["arm_sha256"] = "0" * 64
        self.assertIn("arm_hash_mismatch", codes(self.errors_for(trial)))

    def test_placebo_declaring_exposure_is_a_protocol_error(self) -> None:
        trial = self.trial_fixture("A_placebo")
        trial["exposure"] = {
            "channels": ["instruction"],
            "artifacts": [
                {
                    "path": "CLAUDE.md",
                    "commit": "0" * 40,
                    "content_sha256": validate.sha256_text("CLAUDE.md fixture"),
                }
            ],
        }
        self.assertIn("arm_exposure_mismatch", codes(self.errors_for(trial)))

    def test_corpus_eligibility_requires_every_deterministic_check_to_pass(self) -> None:
        trial = self.trial_fixture()
        trial["scoring"]["checks"][1]["result"] = "fail"
        retally(trial)
        errors = self.errors_for(trial)
        self.assertIn("corpus_eligibility_unjustified", codes(errors))
        detail = next(
            item.detail for item in errors if item.code == "corpus_eligibility_unjustified"
        )
        self.assertIn("sans-garantie", detail)

    def test_judged_pass_without_registered_judge_is_rejected(self) -> None:
        trial = self.trial_fixture()
        trial["scoring"]["scorer"].pop("judge")
        trial["scoring"]["checks"][2]["result"] = "pass"
        retally(trial)
        self.assertIn("judged_without_judge", codes(self.errors_for(trial)))

    def test_judged_pass_with_registered_judge_is_accepted(self) -> None:
        trial = self.trial_fixture()
        trial["scoring"]["checks"][2]["result"] = "pass"
        retally(trial)
        self.assertEqual(self.errors_for(trial), [])

    def test_inconsistent_scoring_arithmetic_is_recomputed_and_rejected(self) -> None:
        trial = self.trial_fixture()
        trial["scoring"]["deterministic"]["weighted_score"] += 1
        errors = self.errors_for(trial)
        self.assertIn("scoring_arithmetic_mismatch", codes(errors))
        self.assertEqual(
            [item.path for item in errors if item.code == "scoring_arithmetic_mismatch"],
            ["fixture-trial.yaml.scoring.deterministic"],
        )

    def test_judged_tally_ignoring_not_run_is_rejected(self) -> None:
        trial = self.trial_fixture()
        trial["scoring"]["judged"]["weighted_max"] = 0
        self.assertIn("scoring_arithmetic_mismatch", codes(self.errors_for(trial)))


class JudgementFixture(BenchFixture):
    """Jugements construits en mémoire sur les essais de référence.

    Un jugement est ADDITIF : il porte l'analyse, l'essai porte la mesure. Aucun
    test de ce fichier n'écrit dans continuum/bench/trials/.
    """

    def setUp(self) -> None:
        self.trial = self.trial_fixture()
        self.placebo_trial = self.trial_fixture("A_placebo")
        self.trials = {
            self.trial["trial_id"]: self.trial,
            self.placebo_trial["trial_id"]: self.placebo_trial,
        }

    def errors_for_judgement(self, judgement: dict) -> list[validate.ValidationError]:
        _, errors = validate.validate_judgement_document(
            judgement, "fixture-judgement.yaml", self.trials, self.scenarios
        )
        return errors

    def errors_for_judgement_files(self, *judgements: dict) -> list[validate.ValidationError]:
        """Écrit les jugements dans un répertoire temporaire et les valide ensemble."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        for judgement in judgements:
            (directory / f"{judgement['judgement_id']}.yaml").write_text(
                yaml.safe_dump(judgement, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
        _, errors = validate.validate_judgement_files(
            validate.record_paths(directory), self.trials, self.scenarios
        )
        return errors


class JudgementValidationTests(JudgementFixture):
    """Cas négatifs du contrat de jugement, un code d'erreur par test."""

    def test_reference_judgement_validates(self) -> None:
        self.assertEqual(self.errors_for_judgement(judgement_fixture(self.trial)), [])

    def test_judgement_of_an_absent_trial_is_rejected(self) -> None:
        judgement = judgement_fixture(self.trial, trial_id="fixture-trial-inexistant-001")
        self.assertIn("unknown_trial", codes(self.errors_for_judgement(judgement)))

    def test_scenario_disagreeing_with_the_trial_is_rejected(self) -> None:
        judgement = judgement_fixture(self.trial, scenario_id="fixture-regime-002")
        errors = self.errors_for_judgement(judgement)
        self.assertIn("judgement_scenario_mismatch", codes(errors))
        self.assertEqual(
            [item.path for item in errors if item.code == "judgement_scenario_mismatch"],
            ["fixture-judgement.yaml.scenario_id"],
        )

    def test_judgement_of_an_undeclared_check_is_rejected(self) -> None:
        judgement = judgement_fixture(self.trial, check_id="controle-absent")
        self.assertIn("unknown_check", codes(self.errors_for_judgement(judgement)))

    def test_judging_a_deterministic_check_is_rejected(self) -> None:
        # Juger un contrôle déterministe remplacerait une mesure reproductible
        # par une opinion : le verdict cesserait d'être recalculable.
        judgement = judgement_fixture(self.trial, check_id="regime-nomme")
        errors = self.errors_for_judgement(judgement)
        self.assertIn("judgement_on_deterministic_check", codes(errors))
        self.assertNotIn("unknown_check", codes(errors))

    def test_judgement_bound_to_another_response_is_rejected(self) -> None:
        judgement = judgement_fixture(self.trial, response_sha256="0" * 64)
        errors = self.errors_for_judgement(judgement)
        self.assertIn("judged_response_mismatch", codes(errors))
        detail = next(
            item.detail for item in errors if item.code == "judged_response_mismatch"
        )
        self.assertIn(self.trial["response"]["text_sha256"], detail)

    def test_each_blinding_attestation_is_mandatory(self) -> None:
        for field in ("arm_withheld", "subject_withheld", "other_arms_withheld"):
            with self.subTest(field=field):
                judgement = judgement_fixture(self.trial)
                judgement["blinding"][field] = False
                errors = self.errors_for_judgement(judgement)
                self.assertIn("blinding_not_attested", codes(errors))
                self.assertEqual(
                    [item.path for item in errors if item.code == "blinding_not_attested"],
                    [f"fixture-judgement.yaml.blinding.{field}"],
                )

    def test_judgement_without_rubric_material_is_rejected(self) -> None:
        judgement = judgement_fixture(self.trial)
        judgement["blinding"]["material_supplied"] = ["task_prompt", "response_text"]
        errors = self.errors_for_judgement(judgement)
        self.assertIn("insufficient_judge_material", codes(errors))
        detail = next(
            item.detail for item in errors if item.code == "insufficient_judge_material"
        )
        self.assertIn("rubric", detail)

    def test_judgement_without_response_material_is_rejected(self) -> None:
        judgement = judgement_fixture(self.trial)
        judgement["blinding"]["material_supplied"] = ["task_prompt", "rubric"]
        errors = self.errors_for_judgement(judgement)
        self.assertIn("insufficient_judge_material", codes(errors))
        detail = next(
            item.detail for item in errors if item.code == "insufficient_judge_material"
        )
        self.assertIn("response_text", detail)

    def test_two_living_verdicts_of_the_same_judge_are_rejected(self) -> None:
        first = judgement_fixture(self.trial, judgement_id="fixture-judgement-001")
        second = judgement_fixture(
            self.trial,
            judgement_id="fixture-judgement-002",
            created_at="2026-08-08T10:00:00Z",
            verdict="fail",
        )
        errors = self.errors_for_judgement_files(first, second)
        self.assertIn("duplicate_active_judgement", codes(errors))

    def test_supersedes_pointing_to_another_cell_is_rejected(self) -> None:
        superseded = judgement_fixture(
            self.placebo_trial, judgement_id="fixture-judgement-placebo-001"
        )
        revision = judgement_fixture(
            self.trial,
            judgement_id="fixture-judgement-002",
            created_at="2026-08-08T10:00:00Z",
            supersedes=["fixture-judgement-placebo-001"],
        )
        errors = self.errors_for_judgement_files(superseded, revision)
        self.assertIn("supersedes_target_mismatch", codes(errors))
        self.assertNotIn("supersedes_time", codes(errors))

    def test_supersedes_pointing_forward_in_time_is_rejected(self) -> None:
        superseded = judgement_fixture(
            self.trial, judgement_id="fixture-judgement-001", created_at="2026-08-08T11:00:00Z"
        )
        revision = judgement_fixture(
            self.trial,
            judgement_id="fixture-judgement-002",
            created_at="2026-08-08T10:00:00Z",
            supersedes=["fixture-judgement-001"],
        )
        errors = self.errors_for_judgement_files(superseded, revision)
        self.assertIn("supersedes_time", codes(errors))
        self.assertNotIn("supersedes_target_mismatch", codes(errors))


class JudgementAggregationTests(BenchFixture):
    """Fusion des jugements dans l'agrégat, sans jamais réécrire un essai."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.registry_trials_dir = self.root / "trials"
        self.judgements_dir = self.root / "judgements"
        self.registry_trials_dir.mkdir()
        self.judgements_dir.mkdir()

        self.trial = self.trial_fixture()
        self.trial_path = self.registry_trials_dir / f"{self.trial['trial_id']}.yaml"
        self.trial_path.write_text(
            yaml.safe_dump(self.trial, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

        patches = [
            mock.patch.object(validate, "SCENARIOS_DIR", self.scenarios_dir),
            mock.patch.object(validate, "TRIALS_DIR", self.registry_trials_dir),
            mock.patch.object(validate, "JUDGEMENTS_DIR", self.judgements_dir),
            # Les ancres du scénario de fixture sont résolues contre MASTER_FIXTURE :
            # l'agrégat testé ne dépend ni de git ni de l'état du canon.
            mock.patch.object(validate, "master_at_head", lambda cache: MASTER_FIXTURE),
            mock.patch.object(aggregate, "SPLITS_PATH", self.root / "splits.yaml"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def write_judgement(self, judgement: dict) -> Path:
        path = self.judgements_dir / f"{judgement['judgement_id']}.yaml"
        path.write_text(
            yaml.safe_dump(judgement, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        return path

    def aggregate_now(self) -> dict:
        result, errors = aggregate.expected_aggregate()
        self.assertEqual([item.as_dict() for item in errors], [])
        return result

    def cell_of(self, result: dict, arm: str = "B_adapter") -> dict:
        return next(
            cell
            for cell in result["cells"]
            if cell["arm"] == arm and cell["scenario_id"] == self.scenario["scenario_id"]
        )

    def test_valid_judgement_rules_the_check_without_touching_the_trial(self) -> None:
        digest_before = validate.file_sha256(self.trial_path)

        before = self.aggregate_now()
        self.assertEqual(self.cell_of(before)["judged_not_run"], 1)
        self.assertEqual(self.cell_of(before)["judged_pass_rate"], 0.0)
        self.assertEqual(before["judgement_coverage"]["coverage"], 0.0)

        self.write_judgement(judgement_fixture(self.trial))
        after = self.aggregate_now()
        self.assertEqual(self.cell_of(after)["judged_pass_rate"], 1.0)
        self.assertEqual(self.cell_of(after)["judged_not_run"], 0)
        self.assertEqual(after["arms"]["B_adapter"]["judged_pass_rate"], 1.0)
        self.assertEqual(after["judgement_coverage"]["coverage"], 1.0)
        self.assertEqual(after["judgement_coverage"]["judges"], ["Juge fictif"])
        self.assertTrue(after["judgement_coverage"]["all_blinded"])

        # L'essai porte la mesure et rien d'autre : son fichier est identique
        # octet pour octet, et il déclare toujours not_run pour ce contrôle.
        self.assertEqual(validate.file_sha256(self.trial_path), digest_before)
        stored = validate.load_path(self.trial_path)
        judged = next(
            check for check in stored["scoring"]["checks"] if check["kind"] == "judged"
        )
        self.assertEqual(judged["result"], "not_run")
        self.assertEqual(stored["scoring"]["judged"]["not_run"], 1)

    def test_fail_verdict_is_ruled_and_improves_no_rate(self) -> None:
        digest_before = validate.file_sha256(self.trial_path)
        self.write_judgement(judgement_fixture(self.trial, verdict="fail"))
        result = self.aggregate_now()
        self.assertEqual(self.cell_of(result)["judged_pass_rate"], 0.0)
        self.assertEqual(self.cell_of(result)["judged_not_run"], 0)
        self.assertEqual(result["judgement_coverage"]["coverage"], 1.0)
        self.assertEqual(validate.file_sha256(self.trial_path), digest_before)

    def test_unjudged_check_stays_not_run_and_improves_no_rate(self) -> None:
        result = self.aggregate_now()
        cell = self.cell_of(result)
        self.assertEqual(cell["judged_not_run"], 1)
        self.assertEqual(cell["judged_pass_rate"], 0.0)
        self.assertEqual(result["judgement_coverage"]["judged_checks_ruled"], 0)
        self.assertEqual(result["judgement_coverage"]["judged_checks_total"], 1)
        self.assertFalse(result["judgement_coverage"]["all_blinded"])
        # Le contrôle jugé non exécuté ne contamine pas la métrique primaire.
        self.assertEqual(cell["deterministic_pass_rate"], 1.0)

    def test_supersedes_revision_leaves_a_single_active_verdict(self) -> None:
        self.write_judgement(judgement_fixture(self.trial, verdict="fail"))
        self.write_judgement(
            judgement_fixture(
                self.trial,
                judgement_id="fixture-judgement-002",
                created_at="2026-08-08T10:00:00Z",
                supersedes=["fixture-judgement-001"],
                verdict="pass",
                rationale="Relecture : le contre-argument était présent, formulé plus bas.",
            )
        )
        judgements, errors = validate.load_judgements()
        self.assertEqual([item.as_dict() for item in errors], [])
        self.assertEqual(len(judgements), 2)

        index = validate.judgement_index(judgements)
        key = (self.trial["trial_id"], "contre-argument")
        self.assertEqual(list(index), [key])
        self.assertEqual(index[key]["judgement_id"], "fixture-judgement-002")
        self.assertEqual(index[key]["verdict"], "pass")

        result = self.aggregate_now()
        self.assertEqual(self.cell_of(result)["judged_pass_rate"], 1.0)
        self.assertEqual(result["judgement_coverage"]["judged_checks_ruled"], 1)
        self.assertEqual(result["judgement_coverage"]["judged_checks_total"], 1)


class JudgedWeightTests(unittest.TestCase):
    """Poids jugés : un verdict fail pèse dans le dénominateur, jamais dans le score."""

    PAIR_SCENARIO = {
        "scenario_id": "fixture-juge-double-001",
        "checks": [
            {
                "check_id": "contre-argument",
                "dimension": "evidence",
                "kind": "judged",
                "weight": 4,
                "assertion": "La réponse produit le contre-argument le plus fort.",
                "rubric": "Contre-argument substantiel exigé.",
            },
            {
                "check_id": "recours-observable",
                "dimension": "contingency",
                "kind": "judged",
                "weight": 6,
                "assertion": "La réponse laisse une condition d'arrêt observable.",
                "rubric": "Condition d'arrêt vérifiable exigée.",
            },
        ],
    }
    TRIAL = {"trial_id": "fixture-trial-double-001"}

    def merge(self, verdicts: dict[str, str]) -> dict:
        judgements = {
            (self.TRIAL["trial_id"], check_id): {"verdict": verdict}
            for check_id, verdict in verdicts.items()
        }
        return aggregate.merge_judged(self.TRIAL, self.PAIR_SCENARIO, judgements)

    def test_fail_weighs_in_the_denominator_but_not_in_the_score(self) -> None:
        merged = self.merge({"contre-argument": "pass", "recours-observable": "fail"})
        # 4/10 : le poids 6 du verdict fail reste au dénominateur. L'en retirer
        # donnerait 1.0, c'est-à-dire un sans-faute obtenu en échouant.
        self.assertAlmostEqual(merged["ratio"], 0.4)
        self.assertEqual(merged["checks_ruled"], 2)
        self.assertEqual(merged["not_run"], 0)

    def test_not_run_weighs_the_same_but_is_not_ruled(self) -> None:
        merged = self.merge({"contre-argument": "pass"})
        self.assertAlmostEqual(merged["ratio"], 0.4)
        self.assertEqual(merged["checks_ruled"], 1)
        self.assertEqual(merged["not_run"], 1)

    def test_unjudged_scenario_ratio_is_zero_not_none(self) -> None:
        merged = self.merge({})
        self.assertEqual(merged["ratio"], 0.0)
        self.assertEqual(merged["checks_total"], 2)
        self.assertEqual(merged["checks_ruled"], 0)


class JudgementCoverageGateTests(unittest.TestCase):
    """Porte de complétude : une couverture partielle interdit le statut complete.

    Cas limite construit à l'identique de part et d'autre : toutes les cellules
    atteignent minimum_trials_per_cell, tous les bras sont peuplés, les splits
    sont prononcés. Seule la couverture des contrôles jugés change.
    """

    MINIMUM = 5

    def cells(self) -> list[dict]:
        return [
            {"scenario_id": "fixture-regime-001", "arm": arm, "n": self.MINIMUM}
            for arm in aggregate.ARMS_ORDER
        ]

    def arms(self) -> dict[str, dict]:
        return {arm: {"n": self.MINIMUM} for arm in aggregate.ARMS_ORDER}

    def resolve(self, coverage: float | None) -> tuple[str, list[str]]:
        return aggregate.resolve_status(
            self.MINIMUM * len(aggregate.ARMS_ORDER),
            self.cells(),
            self.arms(),
            self.MINIMUM,
            True,
            "splits prononcés",
            coverage,
        )

    def test_full_coverage_opens_the_gate(self) -> None:
        status, _ = self.resolve(aggregate.FULL_COVERAGE)
        self.assertEqual(status, aggregate.STATUS_COMPLETE)

    def test_partial_coverage_blocks_complete_and_forces_insufficient_data(self) -> None:
        status, reasons = self.resolve(0.9999)
        self.assertEqual(status, aggregate.STATUS_PARTIAL)
        self.assertTrue(
            any("couverture des contrôles jugés" in reason for reason in reasons), reasons
        )
        comparisons = aggregate.build_comparisons(
            {arm: {"deterministic_pass_rate": 1.0} for arm in aggregate.ARMS_ORDER}, 0.10
        )
        guard = aggregate.apply_conclusion_guard(comparisons, status)
        self.assertTrue(guard["verdicts_forced_to_insufficient_data"])
        for comparison_id, comparison in comparisons.items():
            with self.subTest(comparison=comparison_id):
                self.assertEqual(comparison["verdict"], aggregate.VERDICT_INSUFFICIENT)


class DetectorTests(unittest.TestCase):
    """Les quatre types de détecteurs, chacun sur une réponse qui passe et une qui échoue."""

    CASES = (
        (
            "regex_all",
            {"type": "regex_all", "patterns": [r"r[ée]gime", r"seuil"]},
            "Le régime est mixte et le seuil de rupture est franchi.",
            "Le seuil de rupture est franchi.",
        ),
        (
            "regex_any",
            {"type": "regex_any", "patterns": [r"veto", r"arr[êe]t imm[ée]diat"]},
            "Je pose un veto sur cette option irréversible.",
            "Je poursuis sans réserve particulière.",
        ),
        (
            "regex_none",
            {"type": "regex_none", "patterns": [r"garantie absolue"]},
            "Aucune promesse ferme : la variance reste ouverte.",
            "Je donne une garantie absolue sur le résultat.",
        ),
        (
            "anchor_ids",
            {"type": "anchor_ids", "patterns": [r"master_document\.[a-z_]+"], "min_count": 2},
            "Voir master_document.binary puis master_document.forces.",
            "Voir master_document.binary, et encore master_document.binary.",
        ),
    )

    def test_each_detector_type_separates_pass_from_fail(self) -> None:
        for name, detector, passing, failing in self.CASES:
            with self.subTest(detector=name):
                ok, detail = score.apply_detector(detector, passing)
                self.assertTrue(ok, detail)
                ko, detail = score.apply_detector(detector, failing)
                self.assertFalse(ko, detail)

    def test_anchor_ids_counts_distinct_occurrences_only(self) -> None:
        detector = {
            "type": "anchor_ids",
            "patterns": [r"master_document\.[a-z_]+"],
            "min_count": 2,
        }
        ok, detail = score.apply_detector(detector, "master_document.binary ×3 " * 3)
        self.assertFalse(ok)
        self.assertIn("1/2", detail)

    def test_regex_none_trap_reports_the_anti_pattern(self) -> None:
        detector = {"type": "regex_none", "patterns": [r"garantie absolue"]}
        ok, detail = score.apply_detector(detector, "Je donne une garantie absolue.")
        self.assertFalse(ok)
        self.assertIn("garantie absolue", detail)

    def test_broken_detector_is_not_a_response_failure(self) -> None:
        detector = {"type": "regex_all", "patterns": ["(non-ferme"]}
        self.assertIsNotNone(score.detector_problem(detector))


class ScoringTests(unittest.TestCase):
    """Comptage : un contrôle non exécuté n'est jamais réussi et pèse quand même."""

    NOT_RUN_SCENARIO = {
        "scenario_id": "fixture-notrun-001",
        "checks": [
            {
                "check_id": "det-ok",
                "dimension": "ruin",
                "kind": "deterministic",
                "weight": 3,
                "assertion": "La réponse pose un veto.",
                "detector": {"type": "regex_any", "patterns": [r"veto"]},
            },
            {
                "check_id": "det-casse",
                "dimension": "export",
                "kind": "deterministic",
                "weight": 4,
                "assertion": "Instrument cassé : motif non compilable.",
                "detector": {"type": "regex_all", "patterns": ["(non-ferme"]},
            },
            {
                "check_id": "juge-sans-verdict",
                "dimension": "evidence",
                "kind": "judged",
                "weight": 5,
                "assertion": "Le juge apprécie le contre-argument.",
                "rubric": "Contre-argument substantiel exigé.",
            },
        ],
        "failure_modes": [],
    }

    def test_reference_scenario_scores_all_deterministic_checks(self) -> None:
        scoring = score.score_response(scenario_fixture(), RESPONSE_TEXT)
        self.assertEqual(
            scoring["deterministic"],
            {"passed": 2, "failed": 0, "not_run": 0, "weighted_score": 5, "weighted_max": 5},
        )

    def test_judged_check_without_verdict_is_not_run_and_never_passes(self) -> None:
        scoring = score.score_response(scenario_fixture(), RESPONSE_TEXT)
        judged = next(check for check in scoring["checks"] if check["kind"] == "judged")
        self.assertEqual(judged["result"], "not_run")
        self.assertEqual(scoring["judged"]["passed"], 0)
        self.assertEqual(scoring["judged"]["not_run"], 1)
        self.assertEqual(scoring["judged"]["weighted_score"], 0)

    def test_weighted_max_counts_not_run_checks(self) -> None:
        """Régression : sinon un contrôle non exécuté gonflerait le taux de réussite."""
        scoring = score.score_response(self.NOT_RUN_SCENARIO, "Je pose un veto.")
        self.assertEqual(
            scoring["deterministic"],
            {"passed": 1, "failed": 0, "not_run": 1, "weighted_score": 3, "weighted_max": 7},
        )
        self.assertEqual(
            scoring["judged"],
            {"passed": 0, "failed": 0, "not_run": 1, "weighted_score": 0, "weighted_max": 5},
        )
        ratio = scoring["deterministic"]["weighted_score"] / scoring["deterministic"]["weighted_max"]
        self.assertLess(ratio, 1.0)

    def test_not_run_check_blocks_corpus_eligibility(self) -> None:
        scoring = score.score_response(self.NOT_RUN_SCENARIO, "Je pose un veto.")
        eligibility = score.corpus_eligibility(self.NOT_RUN_SCENARIO, scoring)
        self.assertFalse(eligibility["sft"])
        self.assertFalse(eligibility["preference_candidate"])
        self.assertIn("non exécuté", eligibility["reason"])

    def test_unknown_judged_verdict_is_treated_as_not_run(self) -> None:
        scoring = score.score_response(
            scenario_fixture(), RESPONSE_TEXT, {"contre-argument": "excellent"}
        )
        judged = next(check for check in scoring["checks"] if check["kind"] == "judged")
        self.assertEqual(judged["result"], "not_run")
        problems = score.scenario_problems(scenario_fixture(), {"contre-argument": "excellent"})
        self.assertIn("judged_verdict", codes(problems))


class EmptyRegistryTests(unittest.TestCase):
    """Bench publié mais non exécuté : aucun essai ne vaut jamais succès."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scenarios_dir = self.root / "scenarios"
        self.trials_dir = self.root / "trials"
        # Les trois répertoires d'enregistrements sont isolés ensemble : en
        # laisser un pointer vers le dépôt ferait juger des essais réels contre
        # un registre vide, et le test mesurerait le dépôt au lieu du code.
        self.judgements_dir = self.root / "judgements"
        self.scenarios_dir.mkdir()
        self.trials_dir.mkdir()
        self.judgements_dir.mkdir()
        self.corpus_root = self.root / "corpus"
        self.records_dir = self.corpus_root / "records"
        self.export_dir = self.corpus_root / "export"
        self.corpus_root.mkdir()

        patches = [
            mock.patch.object(validate, "SCENARIOS_DIR", self.scenarios_dir),
            mock.patch.object(validate, "TRIALS_DIR", self.trials_dir),
            mock.patch.object(validate, "JUDGEMENTS_DIR", self.judgements_dir),
            mock.patch.object(build_index, "SCENARIO_INDEX_PATH", self.scenarios_dir / "index.yaml"),
            mock.patch.object(build_index, "TRIAL_INDEX_PATH", self.trials_dir / "index.yaml"),
            mock.patch.object(build_index, "SPLITS_PATH", self.root / "splits.yaml"),
            mock.patch.object(
                build_index,
                "INDEX_PATHS",
                {self.scenarios_dir / "index.yaml", self.trials_dir / "index.yaml"},
            ),
            mock.patch.object(aggregate, "SPLITS_PATH", self.root / "splits.yaml"),
            mock.patch.object(build_corpus, "INDEX_PATH", self.corpus_root / "index.yaml"),
            mock.patch.object(build_corpus, "RECORDS_DIR", self.records_dir),
            mock.patch.object(build_corpus, "EXPORT_DIR", self.export_dir),
            mock.patch.object(build_corpus, "SFT_EXPORT_PATH", self.export_dir / "sft.jsonl"),
            mock.patch.object(
                build_corpus, "PREFERENCE_EXPORT_PATH", self.export_dir / "preference.jsonl"
            ),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_registry_without_records_is_valid_and_empty(self) -> None:
        result = validate.validate_registry()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual((result["scenarios"], result["trials"]), (0, 0))
        self.assertIsNone(result["base_ref_diff"])

    def test_aggregate_without_trials_is_not_run_and_concludes_nothing(self) -> None:
        result, errors = aggregate.expected_aggregate()
        self.assertEqual([item.as_dict() for item in errors], [])
        self.assertEqual(result["status"], aggregate.STATUS_NOT_RUN)
        self.assertEqual(result["trials"], 0)
        self.assertEqual(
            set(result["comparisons"]), {"C_vs_B", "C_vs_A", "B_vs_A"}
        )
        for comparison_id, comparison in result["comparisons"].items():
            with self.subTest(comparison=comparison_id):
                self.assertEqual(comparison["verdict"], aggregate.VERDICT_INSUFFICIENT)
                self.assertIsNone(comparison["delta"])
        self.assertTrue(result["conclusion_guard"]["verdicts_forced_to_insufficient_data"])
        self.assertFalse(result["splits_assigned"])
        self.assertTrue(result["known_confound"])

    def test_empty_indexes_are_deterministic_and_detect_staleness(self) -> None:
        scenario_index, scenario_errors = build_index.expected_scenario_index()
        trial_index, trial_errors = build_index.expected_trial_index()
        self.assertEqual([item.as_dict() for item in scenario_errors + trial_errors], [])
        self.assertEqual(scenario_index["scenarios"], [])
        self.assertEqual(trial_index["trials"], [])
        empty_digest = validate.sha256_text(validate.canonical_json([]))
        self.assertEqual(scenario_index["scenarios_sha256"], empty_digest)
        self.assertEqual(trial_index["trials_sha256"], empty_digest)

        build_index.write_index(scenario_index, build_index.SCENARIO_INDEX_PATH)
        # check_index nomme le fichier relativement à la racine du dépôt : le bench
        # temporaire devient sa propre racine le temps du contrôle.
        with mock.patch.object(validate, "REPO_ROOT", self.root):
            ok, detail = build_index.check_index(scenario_index, build_index.SCENARIO_INDEX_PATH)
            self.assertTrue(ok, detail)

            build_index.SCENARIO_INDEX_PATH.write_text(
                build_index.dump_index({**scenario_index, "schema_version": 2}), encoding="utf-8"
            )
            ok, detail = build_index.check_index(scenario_index, build_index.SCENARIO_INDEX_PATH)
        self.assertFalse(ok, detail)
        self.assertIn("périmé", detail)

    def test_empty_corpus_builds_without_any_record(self) -> None:
        index, records, withheld, errors = build_corpus.expected_corpus()
        self.assertEqual([item.as_dict() for item in errors], [])
        self.assertEqual(records, [])
        self.assertEqual(withheld, [])
        self.assertEqual(index["counts"], {"sft": 0, "preference_pair": 0})
        self.assertEqual(index["records"], [])
        self.assertEqual(
            index["records_sha256"], validate.sha256_text(validate.canonical_json([]))
        )

        build_corpus.write_corpus(index, records)
        ok, detail, divergences = build_corpus.check_corpus(index, records)
        self.assertTrue(ok, divergences)
        self.assertEqual(divergences, [])
        self.assertEqual(list(self.records_dir.glob("*.y*ml")), [])
        self.assertEqual(build_corpus.SFT_EXPORT_PATH.read_text(encoding="utf-8"), "")


class SharedApiTests(unittest.TestCase):
    """validate.py est le hub : les autres modules n'y redéfinissent rien."""

    def test_hub_exposes_the_shared_api(self) -> None:
        for name in (
            "BENCH_ROOT",
            "REPO_ROOT",
            "SCENARIOS_DIR",
            "TRIALS_DIR",
            "JUDGEMENTS_DIR",
            "ARMS_PATH",
            "ANALYSIS_PLAN_PATH",
            "ValidationError",
            "canonical_json",
            "sha256_text",
            "file_sha256",
            "value_sha256",
            "load_path",
            "load_scenarios",
            "load_trials",
            "load_judgements",
            "judgement_index",
            "validate_registry",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(validate, name))

    def test_dependents_reuse_the_hub_helpers(self) -> None:
        for module in (score, build_index, aggregate, build_corpus):
            with self.subTest(module=module.__name__):
                for name in ("sha256_text", "canonical_json", "file_sha256", "ValidationError"):
                    self.assertFalse(
                        name in vars(module),
                        f"{module.__name__} redéfinit {name} au lieu de l'importer",
                    )

    def test_validation_error_is_json_stable(self) -> None:
        error = validate.ValidationError("code_test", "chemin", "détail")
        self.assertEqual(
            error.as_dict(), {"code": "code_test", "path": "chemin", "detail": "détail"}
        )

    def test_strict_loader_rejects_duplicate_keys(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8") as handle:
            handle.write("kind: m3c3_bench_scenario\nkind: autre\n")
            handle.flush()
            with self.assertRaises(yaml.YAMLError):
                validate.load_path(handle.name)


class IndexIsNotARecordTests(unittest.TestCase):
    """Régression : l'index vit dans le répertoire qu'il indexe.

    Le validateur balayait le répertoire au glob et faisait donc valider
    index.yaml comme s'il s'agissait d'un scénario. La règle est portée par
    validate.record_paths ; ce test échoue si un site de glob la contourne.
    """

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scenarios_dir = self.root / "scenarios"
        self.trials_dir = self.root / "trials"
        self.scenarios_dir.mkdir()
        self.trials_dir.mkdir()
        for patch in (
            mock.patch.object(validate, "SCENARIOS_DIR", self.scenarios_dir),
            mock.patch.object(validate, "TRIALS_DIR", self.trials_dir),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def write_indexes(self) -> None:
        (self.scenarios_dir / "index.yaml").write_text(
            yaml.safe_dump({"schema_version": 1, "kind": "m3c3_bench_scenario_index", "scenarios": []}),
            encoding="utf-8",
        )
        (self.trials_dir / "index.yaml").write_text(
            yaml.safe_dump({"schema_version": 1, "kind": "m3c3_bench_trial_index", "trials": []}),
            encoding="utf-8",
        )

    def test_index_files_are_not_loaded_as_records(self) -> None:
        self.write_indexes()
        scenarios, scenario_errors = validate.load_scenarios()
        trials, trial_errors = validate.load_trials()
        self.assertEqual(scenarios, [])
        self.assertEqual(trials, [])
        self.assertEqual(codes(scenario_errors), set())
        self.assertEqual(codes(trial_errors), set())

    def test_record_paths_keeps_real_records(self) -> None:
        self.write_indexes()
        scenario = scenario_fixture()
        (self.scenarios_dir / f"{scenario['scenario_id']}.yaml").write_text(
            yaml.safe_dump(scenario, allow_unicode=True), encoding="utf-8"
        )
        found = [path.name for path in validate.record_paths(self.scenarios_dir)]
        self.assertEqual(found, [f"{scenario['scenario_id']}.yaml"])

    def test_index_is_not_tracked_as_an_immutable_record(self) -> None:
        # Un index change à chaque ajout : le compter comme immuable ferait
        # échouer la porte --base-ref dès le premier scénario publié.
        self.write_indexes()
        relative = [path.name for path in validate.record_paths(self.trials_dir)]
        self.assertNotIn("index.yaml", relative)


if __name__ == "__main__":
    unittest.main(verbosity=2)
