"""Tests for folk/review.py against review-queue.md's exit criteria.

Reuses prototypes/journal-promotion/ fixtures via test_journal.py's helpers
(per docs/HANDOFF.md: the prototype is the regression corpus), the same way
test_journal.py does. Two of the three exit-criteria items -- the radio workshop
bedrock candidate and the known false-stated event -- come straight from
those fixtures. The third (a coined predicate / a near-duplicate entity
slug) has no surviving fixture: vocab.json was already expanded to cover
every predicate either saved LLM pass used, so nothing in prototypes/ still
exercises the "unknown predicate" or "near-duplicate object slug" lint
paths. COMPARISON.md documents that history narratively (predicate drift,
`topic:local-history-stories` vs the reference's
`topic:collecting-local-history-stories`) without preserving it as data, so
these two are small synthetic events in the same session/style as the rest
-- the same pattern test_journal.py's TestLint already uses for scenarios
(duplicate triple, id mismatch, unknown predicate) no saved fixture covers.
"""

import json
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from folk import journal
from folk import review

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_journal as tj  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = REPO_ROOT / "prototypes" / "journal-promotion"


def _full_transcript_texts():
    """Authoritative quote-check text for msg #32 (see test_journal.py's
    identical helper docstring: the observation note is truncated mid-word).
    """
    observations = tj.wrapped_observation_events()
    texts = dict(journal._self_contained_transcript_texts(observations))
    full_32 = ("Makes sense to me. I just worked through those materials back in December 2025, "
               "so they are a recent development for me too... Trying to make sense of what led me "
               "where I am at now. I'm still interested in collecting local history stories.")
    speaker_32 = texts[32][0]
    texts[32] = (speaker_32, journal._words(full_32))
    return texts


class ReviewQueueTestCase(unittest.TestCase):
    """Mirrors test_journal.py's JournalScenarioTestCase: a temp collection
    in folk's real person-file layout + a temp journal root, but split into
    two rebuild phases so the entity near-duplicate check has a stable
    "already known" index snapshot to compare the new batch against (the
    same order folk review is meant to be used in: rebuild, then new
    promotions land, then review before the next rebuild).
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.collection_dir = self.tmp / "personal"
        person_dir = self.collection_dir / "m" / "mara"
        person_dir.mkdir(parents=True)
        (person_dir / "mara.md").write_text((PROTO_DIR / "fixtures" / "mara.md").read_text())

        self.journal_root = self.collection_dir / "journal"
        self.journal_root.mkdir()

        self.vocab_path = self.tmp / "vocab.json"
        self.vocab_path.write_text(json.dumps(tj.proto_vocab()))
        patcher = unittest.mock.patch.object(journal.config, "VOCAB_FILE", self.vocab_path)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.collections = {"personal": str(self.collection_dir)}
        self.roots = [{"path": self.journal_root, "collection": "personal"}]
        self.index_path = self.tmp / "triples.ndjson"
        self.quarantine_dir = self.tmp / "quarantine"

        # Phase 1: observations + the reference promotions (radio workshop bedrock
        # candidate among them) land and get rebuilt, establishing the
        # "already known" index the phase-2 batch's entity check compares
        # against.
        reference_events = tj.observation_events() + tj._load_ndjson(
            PROTO_DIR / "journal" / "2026-06-promotions.ndjson")
        reference_events = [tj._wrap(e) if "id" not in e else e for e in reference_events]
        seg1 = self.journal_root / "2026-05.testwriter.ndjson"
        with open(seg1, "w") as f:
            for e in reference_events:
                f.write(json.dumps(e, sort_keys=True) + "\n")
        self.rebuild()

        self.moment_event = next(
            e for e in reference_events if e.get("o") == "moment:radio-workshop-refuge")

        # Phase 2: a later batch with a coined predicate and a near-duplicate
        # object slug of the phase-1 topic, not yet rebuilt.
        self.coined_predicate_event = tj._wrap({
            "kind": "promotion", "evidence": "interpreted", "level": "core",
            "s": "person:mara", "p": "digs_into", "o": "topic:synth-history",
            "note": "stand-in for a coined predicate (see module docstring)",
            "src": "msg:20260601_025800_7f3ac9e2#1",
            "p_def": "subject explored a topic in depth",
        }, ts="2026-06-01T00:00:00")
        self.near_dup_event = tj._wrap({
            "kind": "promotion", "evidence": "interpreted", "level": "core",
            "s": "person:mara", "p": "interested_in", "o": "topic:collecting-local-history-and-stories",
            "note": "stand-in for a near-duplicate entity slug (see module docstring)",
            "src": "msg:20260601_025800_7f3ac9e2#1",
        }, ts="2026-06-01T00:00:00")
        seg2 = self.journal_root / "2026-06.testwriter.ndjson"
        with open(seg2, "w") as f:
            f.write(json.dumps(self.coined_predicate_event, sort_keys=True) + "\n")
            f.write(json.dumps(self.near_dup_event, sort_keys=True) + "\n")

        # The known false-stated event: quarantined by re-lint, per the
        # session-promotion job's all-or-nothing rule (session-promotion-job.md
        # step 4) -- it never enters the journal.
        self.session_id = tj.SESSION.split(":", 1)[-1]
        llm_events = tj.llm_first_pass_events()
        errors, _proposals = journal.lint_events(
            tj.wrapped_observation_events() + llm_events,
            transcript_texts=_full_transcript_texts(), vocab=tj.proto_vocab())
        self.assertTrue(errors, "fixture should still fail lint (speaker attribution)")
        self.quarantine_errors = errors
        review.write_quarantine(self.session_id, llm_events, errors, quarantine_dir=self.quarantine_dir)

    def rebuild(self):
        return journal.rebuild_index(collections=self.collections, roots=self.roots, index_path=self.index_path)

    def pending(self):
        return review.pending_items(
            collections=self.collections, roots=self.roots,
            index_path=self.index_path, quarantine_dir=self.quarantine_dir,
            vocab=journal.load_vocab())


class TestQueueContents(ReviewQueueTestCase):

    def test_bedrock_shows_radio_workshop_candidate(self):
        items = self.pending()
        self.assertTrue(any(it["o"] == "moment:radio-workshop-refuge" for it in items["bedrock"]))

    def test_vocab_shows_coined_predicate(self):
        items = self.pending()
        self.assertTrue(any(it["value"] == "digs_into" and it["proposal_kind"] == "predicate"
                             for it in items["vocab"]))

    def test_entity_shows_near_duplicate(self):
        items = self.pending()
        self.assertTrue(any(
            it["slug"] == "topic:collecting-local-history-and-stories"
            and it["dup_of"] == "topic:collecting-local-history-stories"
            for it in items["entity"]))

    def test_lint_failure_shows_quarantined_session(self):
        items = self.pending()
        self.assertTrue(any(it["session"] == self.session_id for it in items["lint_failure"]))
        failure = next(it for it in items["lint_failure"] if it["session"] == self.session_id)
        self.assertEqual(failure["n_events"], 7)
        self.assertTrue(any("didn't say this here" in e for e in failure["errors"]))


class TestBedrockAccept(ReviewQueueTestCase):

    def test_accept_appends_to_person_file_writes_review_event_and_leaves_queue(self):
        items = self.pending()
        item = next(it for it in items["bedrock"] if it["o"] == "moment:radio-workshop-refuge")

        fpath, section, line, diff = review.preview_bedrock_edit(item, collections=self.collections)
        self.assertIn("Defining Moments", diff)
        self.assertIn("radio-workshop", diff.lower())

        review.apply_bedrock_edit(fpath, section, line)
        content = fpath.read_text()
        self.assertIn("## Defining Moments", content)
        self.assertIn("moment:radio-workshop-refuge", content)

        review.record_review(item, "accept", roots=self.roots)

        after = self.pending()
        self.assertFalse(any(it["event_id"] == item["event_id"] for it in after["bedrock"]))


class TestVocabAccept(ReviewQueueTestCase):

    def test_accept_adds_predicate_definition_and_leaves_queue(self):
        items = self.pending()
        item = next(it for it in items["vocab"] if it["value"] == "digs_into")

        review.accept_vocab(item)
        review.record_review(item, "accept", roots=self.roots)

        vocab = journal.load_vocab()
        self.assertEqual(vocab["predicates"]["digs_into"], "subject explored a topic in depth")

        after = self.pending()
        self.assertFalse(any(it.get("value") == "digs_into" for it in after["vocab"]))


class TestEntityAccept(ReviewQueueTestCase):

    def test_accept_adds_alias_and_leaves_queue(self):
        items = self.pending()
        item = next(it for it in items["entity"]
                    if it["slug"] == "topic:collecting-local-history-and-stories")

        review.accept_entity(item)
        review.record_review(item, "accept", roots=self.roots)

        vocab = journal.load_vocab()
        self.assertEqual(vocab["aliases"]["topic:collecting-local-history-and-stories"],
                          "topic:collecting-local-history-stories")

        after = self.pending()
        self.assertFalse(any(it.get("slug") == "topic:collecting-local-history-and-stories"
                              for it in after["entity"]))


class TestRejectDropsFromIndex(ReviewQueueTestCase):

    def test_reject_then_rebuild_drops_triples_empties_queue_and_stays_deterministic(self):
        # Reject the prioritizes/garden-tracker stated fact from phase 1.
        items = self.pending()
        # It's not a bedrock/vocab/entity item (ordinary core stated fact) --
        # find its id directly from the phase-1 events rather than the queue.
        target = next(e for e in journal.read_segment(self.journal_root / "2026-05.testwriter.ndjson")
                       if e.get("o") == "project:garden-tracker")
        fake_item = {"event_id": target["id"], "col": "personal"}

        review.record_review(fake_item, "reject", roots=self.roots)
        self.rebuild()

        triples, _suggestions = journal.replay(collections=self.collections, roots=self.roots)
        self.assertFalse(any(t["o"] == "project:garden-tracker" for t in triples))

        first = self.index_path.read_bytes()
        self.rebuild()
        second = self.index_path.read_bytes()
        self.assertEqual(first, second)


class TestCounterpartyFlagging(ReviewQueueTestCase):
    """review-queue.md's memory-poisoning containment rule: promotions from a
    session with an external counterparty carry that on the queue item, so
    interactive review can flag them (surfaced individually is automatic --
    there is no batch mode at all -- but the item itself must say so).
    """

    def test_bedrock_item_carries_session_counterparty(self):
        session_event = tj._wrap({"kind": "session", "s": "", "p": "", "o": "",
                                   "counterparty": ["unknown:some-telegram-handle"]})
        seg = self.journal_root / "2026-05.testwriter.ndjson"
        with open(seg, "a") as f:
            f.write(json.dumps(session_event, sort_keys=True) + "\n")

        items = self.pending()
        moment_item = next(it for it in items["bedrock"] if it["o"] == "moment:radio-workshop-refuge")
        self.assertEqual(moment_item["counterparty"], ["unknown:some-telegram-handle"])


class TestLintFailureDiscard(ReviewQueueTestCase):

    def test_discard_removes_quarantine_files_and_empties_that_group(self):
        items = self.pending()
        item = next(it for it in items["lint_failure"] if it["session"] == self.session_id)
        review.discard_quarantine(item)

        after = self.pending()
        self.assertEqual(after["lint_failure"], [])
        self.assertFalse((self.quarantine_dir / f"{self.session_id}.ndjson").exists())
        self.assertFalse((self.quarantine_dir / f"{self.session_id}.errors.txt").exists())


if __name__ == "__main__":
    unittest.main()
