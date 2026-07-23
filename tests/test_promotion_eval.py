"""Tests for scripts/promotion_eval.py against promotion-eval.md's exit
criteria (Phase 2, task 7). Pure/replay-mode only -- live mode touches
Ollama and is never exercised here, per the spec's own scope.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import promotion_eval as pe  # noqa: E402

from folk import journal, promotion  # noqa: E402


def _write_md(path, heading, sections=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {heading}", ""]
    for name, body_lines in (sections or {}).items():
        lines.append(f"## {name}")
        lines.extend(body_lines)
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


class TripleKeyTestCase(unittest.TestCase):

    def test_alias_canonicalizes_s_and_o_but_not_p(self):
        aliases = {"topic:local-history-stories": "topic:collecting-local-history-stories",
                   "person:c": "person:mara"}
        event = {"s": "person:c", "p": "worked_on", "o": "topic:local-history-stories"}
        self.assertEqual(
            pe.triple_key(event, aliases),
            ("person:mara", "worked_on", "topic:collecting-local-history-stories"))

    def test_predicate_drift_is_not_aliased(self):
        # Decision 2: matching is (s, p, o) after *entity-slug* alias
        # canonicalization only -- predicate drift is a real finding, not
        # something aliasing papers over.
        aliases = {}
        ref = {"s": "person:mara", "p": "prioritizes", "o": "project:garden-tracker"}
        cand = {"s": "person:mara", "p": "worked_on", "o": "project:garden-tracker"}
        self.assertNotEqual(pe.triple_key(ref, aliases), pe.triple_key(cand, aliases))


class ScorerDeterminismTestCase(unittest.TestCase):

    def setUp(self):
        self.vocab = {"aliases": {}}
        self.labels = {
            "reference": [{"s": "person:a", "p": "interested_in", "o": "topic:x"}],
            "acceptable_extras": [], "known_false": [],
        }
        self.candidates = [
            {"kind": "promotion", "evidence": "interpreted", "level": "core",
             "s": "person:a", "p": "interested_in", "o": "topic:x", "note": "n"},
        ]

    def test_scoring_the_same_output_twice_is_byte_identical(self):
        r1 = pe.score_session(self.candidates, self.labels, self.vocab)
        r2 = pe.score_session(self.candidates, self.labels, self.vocab)
        s1 = json.dumps(r1, sort_keys=True)
        s2 = json.dumps(r2, sort_keys=True)
        self.assertEqual(s1, s2)


class AliasCanonicalizedMatchingTestCase(unittest.TestCase):

    def test_coverage_matches_via_alias_on_object_slug(self):
        vocab = {"aliases": {"topic:local-history-stories": "topic:collecting-local-history-stories"}}
        labels = {
            "reference": [{"s": "person:mara", "p": "interested_in",
                            "o": "topic:collecting-local-history-stories"}],
            "acceptable_extras": [], "known_false": [],
        }
        candidates = [{"kind": "promotion", "evidence": "stated", "level": "core",
                       "s": "person:mara", "p": "interested_in",
                       "o": "topic:local-history-stories", "note": "n"}]
        report = pe.score_session(candidates, labels, vocab)
        self.assertEqual(report["coverage"]["ratio"], 1.0)
        self.assertEqual(report["coverage"]["missed"], [])

    def test_known_false_pinned_to_evidence_tier_does_not_shadow_reference(self):
        # The same (s, p, o) is a true fact at evidence=interpreted (reference)
        # but false specifically at evidence=stated (known_false) -- the
        # third-party-testimony pattern (synthetic-family-testimony fixture).
        vocab = {"aliases": {}}
        labels = {
            "reference": [{"s": "person:elena", "p": "bakes_daily", "o": "event:daily-bread-baking"}],
            "acceptable_extras": [],
            "known_false": [{"s": "person:elena", "p": "bakes_daily", "o": "event:daily-bread-baking",
                              "evidence": "stated"}],
        }
        stated = [{"kind": "promotion", "evidence": "stated", "level": "core",
                   "s": "person:elena", "p": "bakes_daily", "o": "event:daily-bread-baking", "note": "n"}]
        interpreted = [{"kind": "promotion", "evidence": "interpreted", "level": "core",
                        "s": "person:elena", "p": "bakes_daily", "o": "event:daily-bread-baking", "note": "n"}]

        bad = pe.score_session(stated, labels, vocab)
        good = pe.score_session(interpreted, labels, vocab)

        self.assertEqual(bad["faithfulness"]["ratio"], 0.0)
        self.assertIn(("person:elena", "bakes_daily", "event:daily-bread-baking"),
                      bad["faithfulness"]["violations"])
        self.assertEqual(good["faithfulness"]["ratio"], 1.0)
        self.assertEqual(good["faithfulness"]["violations"], [])
        # coverage is unaffected by the evidence tier either way (Decision 2:
        # a fact recovered at the wrong tier is a finding, not a miss).
        self.assertEqual(bad["coverage"]["ratio"], 1.0)
        self.assertEqual(good["coverage"]["ratio"], 1.0)


class PreservationTestCase(unittest.TestCase):

    def test_untouched_lines_are_preserved(self):
        before = ['{"o": "tag:alpha", "p": "tagged", "s": "person:x"}']
        after = before + ['{"o": "topic:new", "p": "interested_in", "s": "person:y"}']
        ok, missing = pe.check_preservation(before, after)
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_a_dropped_or_mutated_pre_existing_line_fails_preservation(self):
        before = ['{"o": "tag:alpha", "p": "tagged", "s": "person:x"}']
        after = ['{"o": "tag:beta", "p": "tagged", "s": "person:x"}']  # mutated, not preserved
        ok, missing = pe.check_preservation(before, after)
        self.assertFalse(ok)
        self.assertEqual(missing, before)


class FullPipelinePreservationTestCase(unittest.TestCase):
    """Exit criterion: 'the planted-corruption test fails preservation; an
    untouched pipeline run passes it' -- exercised over the real
    extract -> promote -> append(staging) -> rebuild(before/after) pipeline,
    not just the comparison function in isolation.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.personal_dir = self.tmp / "personal"
        self.person_path = self.personal_dir / "x" / "x" / "x.md"
        _write_md(self.person_path, "Person X", {"Tags": ["alpha"]})

        self.collections = {"personal": str(self.personal_dir)}
        self.roots = []  # no pre-existing journal segments; the person file is the pre-existing state

        self.vocab = {"types": ["person", "topic"], "predicates": {"interested_in": "x"}, "aliases": {}}

        self.session = {
            "session_id": "eval-preservation", "conv": "conv:eval-preservation",
            "platform": "telegram", "collection": "personal",
            "user_slug": "person:x", "agent_slug": "agent:test-main",
            "counterparty": [],
            "messages": [{"index": 1, "role": "user", "speaker": "person:x",
                          "text": "I love hiking.", "ts": "2026-07-01T00:00:00"}],
            "session_ts": "2026-07-01T00:00:00",
        }

    def _promote_call(self, prompt, model, url):
        event = {"kind": "promotion", "evidence": "stated", "level": "core",
                 "s": "person:x", "p": "interested_in", "o": "topic:hiking",
                 "src": "msg:eval-preservation#1", "note": "I love hiking."}
        return json.dumps(event)

    def test_untouched_run_preserves(self):
        result = pe.run_preservation(self.session, self.vocab, self._promote_call,
                                      self.collections, self.roots, self.tmp / "run-clean")
        self.assertEqual(result["outcome"], "ok")
        self.assertTrue(result["preserved"], result["missing"])

    def test_planted_corruption_fails_preservation(self):
        tmp_dir = self.tmp / "run-corrupt"
        tmp_dir.mkdir()
        index_before = tmp_dir / "before.ndjson"
        journal.rebuild_index(collections=self.collections, roots=self.roots, index_path=index_before)
        before_lines = index_before.read_text(encoding="utf-8").splitlines()
        self.assertTrue(before_lines)  # sanity: the tag really is pre-existing state

        # Plant the corruption: mutate the pre-existing person file's curated
        # content in between building BEFORE and AFTER -- unrelated to the
        # new session's own promotion, exactly the "adding a session never
        # mutates what was already true" property Decision 2 guards.
        _write_md(self.person_path, "Person X", {"Tags": ["beta"]})

        staging_root = tmp_dir / "staging" / "personal"
        outcome, _counts, _wall, _errors = promotion.process_session(
            self.session, self.vocab, index_before, staging_root, tmp_dir / "quarantine",
            "eval", "unused", promote_call=self._promote_call)
        self.assertEqual(outcome, "ok")

        all_roots = list(self.roots) + [{"path": staging_root, "collection": "personal"}]
        index_after = tmp_dir / "after.ndjson"
        journal.rebuild_index(collections=self.collections, roots=all_roots, index_path=index_after)
        after_lines = index_after.read_text(encoding="utf-8").splitlines()

        ok, missing = pe.check_preservation(before_lines, after_lines)
        self.assertFalse(ok)
        self.assertTrue(any("tag:alpha" in ln for ln in missing))


class CorpusReplayTestCase(unittest.TestCase):
    """Exercises the real, committed eval/corpus/ fixtures -- the actual
    exit-criteria sanity checks, not synthetic stand-ins.
    """

    def test_prototype_fixture_scores_honestly_not_the_stale_six_of_eight(self):
        report = pe.replay_score("20260601_025800_7f3ac9e2")
        self.assertEqual(report["coverage"]["n_reference"], 8)
        # Real, checked-in second-pass output recovers 4/8 -- see that
        # session's NOTE.md for why this isn't the historical "6/8" (a
        # different, unpreserved first-pass run).
        self.assertEqual(report["coverage"]["ratio"], 0.5)
        self.assertIsNone(report["faithfulness"]["src_lint"])  # no raw transcript for this session

    def test_scoring_the_prototype_fixture_twice_is_byte_identical(self):
        r1 = pe.replay_score("20260601_025800_7f3ac9e2")
        r2 = pe.replay_score("20260601_025800_7f3ac9e2")
        self.assertEqual(json.dumps(r1, sort_keys=True), json.dumps(r2, sort_keys=True))

    def test_synthetic_session_pre_fix_output_is_a_faithfulness_violation(self):
        report = pe.replay_score("synthetic-family-testimony", output_filename="2026-07-18.pre-fix.ndjson")
        self.assertLess(report["faithfulness"]["src_lint"]["pass_rate"], 1.0)
        self.assertIn(("person:elena", "bakes_daily", "event:daily-bread-baking"),
                      report["faithfulness"]["violations"])

    def test_synthetic_session_post_fix_output_does_not_recur(self):
        report = pe.replay_score("synthetic-family-testimony", output_filename="2026-07-19.post-fix.ndjson")
        self.assertEqual(report["faithfulness"]["src_lint"]["pass_rate"], 1.0)
        self.assertEqual(report["faithfulness"]["violations"], [])
        self.assertEqual(report["coverage"]["ratio"], 1.0)


class RegressionGateTestCase(unittest.TestCase):

    def test_no_regressions_against_matching_baseline(self):
        report = {"session_id": "s1", "coverage": {"ratio": 0.5},
                  "faithfulness": {"ratio": 1.0, "src_lint": {"pass_rate": 1.0}}}
        baseline = {"sessions": {"s1": {"coverage": {"ratio": 0.5}, "faithfulness": {"ratio": 1.0},
                                        "src_lint": {"pass_rate": 1.0}}}}
        self.assertEqual(pe.check_regression([report], baseline), [])

    def test_a_dropped_metric_is_flagged(self):
        report = {"session_id": "s1", "coverage": {"ratio": 0.4},
                  "faithfulness": {"ratio": 1.0, "src_lint": None}}
        baseline = {"sessions": {"s1": {"coverage": {"ratio": 0.5}, "faithfulness": {"ratio": 1.0},
                                        "src_lint": None}}}
        problems = pe.check_regression([report], baseline)
        self.assertEqual(len(problems), 1)
        self.assertIn("coverage", problems[0])


if __name__ == "__main__":
    unittest.main()
