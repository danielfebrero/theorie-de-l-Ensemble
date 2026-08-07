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


def codes(errors: list[validate.ValidationError]) -> set[str]:
    return {item.code for item in errors}


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
        self.scenarios_dir.mkdir()
        self.trials_dir.mkdir()
        self.corpus_root = self.root / "corpus"
        self.records_dir = self.corpus_root / "records"
        self.export_dir = self.corpus_root / "export"
        self.corpus_root.mkdir()

        patches = [
            mock.patch.object(validate, "SCENARIOS_DIR", self.scenarios_dir),
            mock.patch.object(validate, "TRIALS_DIR", self.trials_dir),
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
