"""Tests for folk/bulk.py against docs/design/bulk-import.md's exit criteria."""

import shutil
import tempfile
import unittest
from pathlib import Path

from folk import bulk, journal


def _good_event(n):
    return {
        "v": 1, "ts": f"2026-08-3{n}T03:00:00", "actor": "import:directory-scrape:v1",
        "kind": "observation", "s": f"person:record-{n}", "p": "works_at",
        "o": "locus:neurology", "src": f"directory-scrape:profile:{n}#department",
    }


def _bad_event(n):
    # Missing "actor" -- a hard lint error (journal.lint_events_detailed
    # requires ts/actor/kind), not something append_event should tolerate.
    return {
        "v": 1, "ts": f"2026-08-3{n}T03:00:00", "kind": "observation",
        "s": f"person:record-{n}", "p": "works_at", "o": "locus:neurology",
        "src": f"directory-scrape:profile:{n}#department",
    }


class TestImportBatch(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "journal"

    def _segment_events(self):
        segments = list(self.root.glob("*.ndjson"))
        events = []
        for seg in segments:
            events.extend(journal.read_segment(seg))
        return events

    def test_all_good_batch_appends_everything(self):
        events = [_good_event(1), _good_event(2), _good_event(3)]
        outcomes = bulk.import_batch(self.root, "directory-scrape", events)

        self.assertEqual([o["status"] for o in outcomes], ["appended", "appended", "appended"])
        self.assertTrue(all(o["reason"] is None for o in outcomes))
        self.assertTrue(all(o["event"]["id"] for o in outcomes))
        self.assertEqual(len(self._segment_events()), 3)

    def test_one_bad_record_is_skipped_and_reported_without_blocking_the_rest(self):
        events = [_good_event(1), _bad_event(2), _good_event(3)]
        outcomes = bulk.import_batch(self.root, "directory-scrape", events)

        statuses = [o["status"] for o in outcomes]
        self.assertEqual(statuses, ["appended", "skipped", "appended"])
        self.assertIsNone(outcomes[0]["reason"])
        self.assertIsNotNone(outcomes[1]["reason"])
        self.assertIn("actor", outcomes[1]["reason"])
        self.assertIsNone(outcomes[1]["event"])

        # Decision 1: a bad record must not block its siblings from landing.
        written = self._segment_events()
        self.assertEqual(len(written), 2)
        written_subjects = {e["s"] for e in written}
        self.assertEqual(written_subjects, {"person:record-1", "person:record-3"})

    def test_outcomes_preserve_input_order_and_src(self):
        events = [_good_event(1), _bad_event(2)]
        outcomes = bulk.import_batch(self.root, "directory-scrape", events)
        self.assertEqual([o["src"] for o in outcomes],
                         ["directory-scrape:profile:1#department",
                          "directory-scrape:profile:2#department"])


if __name__ == "__main__":
    unittest.main()
