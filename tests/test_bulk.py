"""Tests for folk/bulk.py against docs/design/bulk-import.md's exit criteria."""

import json
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


class TestImportBatchMinting(unittest.TestCase):
    """docs/design/collection-curation.md's create_person_file_as_agent,
    wired into import_batch per docs/design/bulk-import.md's "Not built"
    follow-up.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "journal"
        self.agent_collection = self.tmp / "agent-collection"
        self.agent_collection.mkdir()
        (self.agent_collection / "COLLECTION.json").write_text(
            json.dumps({"curation": "agent"}), encoding="utf-8")
        self.human_collection = self.tmp / "human-collection"
        self.human_collection.mkdir()  # no COLLECTION.json -- fails closed to human

    def test_no_collection_dir_mints_nothing(self):
        outcomes = bulk.import_batch(self.root, "directory-scrape", [_good_event(1)],
                                      person_names={"person:record-1": "Record One"})
        self.assertEqual(outcomes[0]["status"], "appended")
        self.assertIsNone(outcomes[0]["minted"])

    def test_agent_curated_collection_mints_from_person_names(self):
        outcomes = bulk.import_batch(
            self.root, "directory-scrape", [_good_event(1)],
            collection_dir=self.agent_collection,
            person_names={"person:record-1": "Record One"})

        fpath = self.agent_collection / "r" / "record-1" / "record-1.md"
        self.assertEqual(outcomes[0]["minted"], str(fpath))
        self.assertTrue(fpath.exists())
        self.assertEqual(fpath.read_text(encoding="utf-8").splitlines()[0], "# Record One")

    def test_missing_display_name_mints_nothing_but_still_appends(self):
        outcomes = bulk.import_batch(
            self.root, "directory-scrape", [_good_event(1)],
            collection_dir=self.agent_collection, person_names={})

        self.assertEqual(outcomes[0]["status"], "appended")
        self.assertIsNone(outcomes[0]["minted"])
        self.assertFalse((self.agent_collection / "r" / "record-1" / "record-1.md").exists())

    def test_human_curated_collection_refuses_minting_but_still_appends(self):
        outcomes = bulk.import_batch(
            self.root, "directory-scrape", [_good_event(1)],
            collection_dir=self.human_collection,
            person_names={"person:record-1": "Record One"})

        self.assertEqual(outcomes[0]["status"], "appended")
        self.assertIsNone(outcomes[0]["minted"])
        self.assertFalse((self.human_collection / "r" / "record-1" / "record-1.md").exists())

    def test_second_event_for_same_subject_is_not_reminted(self):
        events = [_good_event(1),
                  {**_good_event(1), "p": "holds_title", "o": "title:researcher",
                   "src": "directory-scrape:profile:1#title"}]
        outcomes = bulk.import_batch(
            self.root, "directory-scrape", events,
            collection_dir=self.agent_collection,
            person_names={"person:record-1": "Record One"})

        self.assertIsNotNone(outcomes[0]["minted"])
        self.assertIsNone(outcomes[1]["minted"])
        # Only one file, not overwritten or duplicated.
        self.assertEqual(
            len(list((self.agent_collection / "r" / "record-1").iterdir())), 1)

    def test_preexisting_file_is_not_overwritten_and_batch_still_appends(self):
        fdir = self.agent_collection / "r" / "record-1"
        fdir.mkdir(parents=True)
        (fdir / "record-1.md").write_text("# Record One\n\nhand-authored\n", encoding="utf-8")

        outcomes = bulk.import_batch(
            self.root, "directory-scrape", [_good_event(1)],
            collection_dir=self.agent_collection,
            person_names={"person:record-1": "Record One"})

        self.assertEqual(outcomes[0]["status"], "appended")
        self.assertIsNone(outcomes[0]["minted"])
        self.assertIn("hand-authored", (fdir / "record-1.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
