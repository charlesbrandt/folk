"""Tests for scripts/appearance_eval.py -- docs/design/appearance.md Decision 10.

Mirrors test_promotion_eval.py's shape: the scorer is importable so its own
behavior can be pinned, and the load-bearing test is a *planted failure* --
a check that never fires is indistinguishable from a clean run.
"""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "appearance_eval", REPO_ROOT / "scripts" / "appearance_eval.py")
appearance_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(appearance_eval)


class TestCorpusScores(unittest.TestCase):
    """The committed corpus must be green, and its planted-stale prompt must
    stay planted -- if someone 'fixes' 02-stale-frame.txt, propagation stops
    proving anything and this fails.
    """

    def setUp(self):
        self.reports = appearance_eval.score()

    def test_corpus_is_not_empty(self):
        self.assertTrue(self.reports)

    def test_all_gating_checks_pass(self):
        for r in self.reports:
            for check in appearance_eval.GATING_CHECKS:
                self.assertTrue(r[check]["ok"], f"{r['figure']} {check}: {r[check]['detail']}")

    def test_planted_stale_prompt_is_still_stale(self):
        lamplighter = next(r for r in self.reports if r["figure"] == "lamplighter")
        self.assertEqual(lamplighter["propagation"]["unexpectedly_current"], [])

    def test_scoring_twice_yields_an_identical_report(self):
        again = appearance_eval.score()
        self.assertEqual(json.dumps(self.reports, sort_keys=True),
                         json.dumps(again, sort_keys=True))


class TestChecksAgainstAFixtureCorpus(unittest.TestCase):
    """Each check gets its own planted failure, in a temp corpus so the
    committed one stays green.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.figure_dir = self.tmp / "figure"
        (self.figure_dir / "prompts").mkdir(parents=True)
        self.person_path = self.figure_dir / "person.md"
        self._write_person("- build: narrow\n- hair: grey\n- face: long")
        self.consumers = {"dream": {"required_labels": ["build", "hair", "face"]}}

    def _write_person(self, appearance_body):
        self.person_path.write_text(
            "# A Figure\n\nA fixture.\n\n## Appearance\n\n" + appearance_body + "\n",
            encoding="utf-8")

    def _compiled(self):
        return appearance_eval.compile_brief(self.person_path)

    def _write_golden(self):
        (self.figure_dir / "expected.json").write_text(
            json.dumps(self._compiled(), indent=2) + "\n", encoding="utf-8")

    def test_stability_fails_when_the_brief_changes_under_a_golden(self):
        self._write_golden()
        self.assertTrue(appearance_eval.check_stability(self.figure_dir, self._compiled())["ok"])
        self._write_person("- build: broad\n- hair: grey\n- face: long")
        result = appearance_eval.check_stability(self.figure_dir, self._compiled())
        self.assertFalse(result["ok"])
        self.assertIn("appearance_text", result["detail"])

    def test_stability_fails_loudly_when_no_golden_exists(self):
        result = appearance_eval.check_stability(self.figure_dir, self._compiled())
        self.assertFalse(result["ok"])
        self.assertIn("no golden snapshot", result["detail"])

    def test_propagation_fails_when_a_brief_is_edited_without_recompiling(self):
        """The planted failure this check exists for: a prompt compiled from
        an older brief is exactly the stale-artifact drift that otherwise
        gets blamed on the model.
        """
        prompt = self.figure_dir / "prompts" / "01.txt"
        prompt.write_text(f"figure: {self._compiled()['appearance_text']}\n", encoding="utf-8")
        self.assertTrue(appearance_eval.check_propagation(self.figure_dir, self._compiled(), {})["ok"])

        self._write_person("- build: narrow\n- hair: white\n- face: long")
        result = appearance_eval.check_propagation(self.figure_dir, self._compiled(), {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["stale"], ["01.txt"])
        self.assertIn("never recompiled", result["detail"])

    def test_expected_stale_prompt_inverts_the_assertion(self):
        prompt = self.figure_dir / "prompts" / "stale.txt"
        prompt.write_text("figure: build: broad; hair: black\n", encoding="utf-8")
        labels = {"expected_stale_prompts": ["stale.txt"]}
        self.assertTrue(
            appearance_eval.check_propagation(self.figure_dir, self._compiled(), labels)["ok"])

        # If the planted-stale prompt silently becomes current, the check
        # itself has stopped proving anything and must say so.
        prompt.write_text(f"figure: {self._compiled()['appearance_text']}\n", encoding="utf-8")
        result = appearance_eval.check_propagation(self.figure_dir, self._compiled(), labels)
        self.assertFalse(result["ok"])
        self.assertEqual(result["unexpectedly_current"], ["stale.txt"])

    def test_coverage_reports_missing_labels_without_gating(self):
        self._write_person("- build: narrow")
        coverage = appearance_eval.check_coverage(self._compiled(), self.consumers)
        self.assertEqual(coverage["dream"]["missing"], ["hair", "face"])
        self.assertEqual(coverage["dream"]["present"], 1)
        # Coverage is a finding, never a gate -- it is not in GATING_CHECKS.
        self.assertNotIn("coverage", appearance_eval.GATING_CHECKS)

    def test_determinism_holds_on_unchanged_input(self):
        self.assertTrue(appearance_eval.check_determinism(self.person_path)["ok"])

    def test_compile_uses_folk_own_flattening(self):
        """The harness must not reimplement the brief it is testing."""
        from folk import person
        info = person.show_person(self.person_path)
        self.assertEqual(self._compiled()["appearance_text"],
                         person.appearance_text(info["appearance"]))


class TestNoImagesAndNoModels(unittest.TestCase):
    """Decision 10's hard rule: the scoring path never opens an image and
    never calls a model. Anything else makes the harness meaningless.
    """

    def test_runner_imports_no_model_or_image_machinery(self):
        source = (REPO_ROOT / "scripts" / "appearance_eval.py").read_text(encoding="utf-8")
        for forbidden in ("urllib", "requests", "http.client", "socket", "PIL", "ollama", "subprocess"):
            self.assertNotIn(f"import {forbidden}", source)

    def test_likeness_grades_are_carried_but_never_scored(self):
        lamplighter = next(r for r in appearance_eval.score() if r["figure"] == "lamplighter")
        self.assertTrue(lamplighter["likeness_grades"])
        for grade in lamplighter["likeness_grades"]:
            self.assertIn("brief_fingerprint", grade)
        # No metric anywhere in the report derives from a grade.
        for check in appearance_eval.GATING_CHECKS:
            self.assertNotIn("likeness", json.dumps(lamplighter[check]))

    def test_grades_are_attributed_to_the_current_brief(self):
        """A grade pinned to an older fingerprint describes a render the
        current brief would no longer produce -- the report must be able to
        tell those apart, which is the whole reason Decision 9 fingerprints
        the brief.
        """
        lamplighter = next(r for r in appearance_eval.score() if r["figure"] == "lamplighter")
        for grade in lamplighter["likeness_grades"]:
            self.assertEqual(grade["brief_fingerprint"], lamplighter["fingerprint"])


if __name__ == "__main__":
    unittest.main()
