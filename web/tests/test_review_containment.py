"""Tests for web/routers/review.py -- the review-queue GUI's accept/reject
dispatch and, specifically, the containment rule (docs/design/web-ui.md
Decision 2e: "'Select all -> accept' is forbidden for counterparty-sourced
items by construction"). The main thing worth proving here is that the
request body shape itself makes batching impossible, not just that the UI
happens not to offer a batch button -- so this test tries to construct a
batch call and confirms it's rejected by validation before any handler code
even runs.

Runs against a throwaway journal root under a temp directory (never the real
~/.config/folk config or ~/.folk/triples.ndjson) -- same isolation pattern as
test_edit_write.py.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_WEB_DIR = Path(__file__).resolve().parent.parent
if str(_WEB_DIR) not in sys.path:
    sys.path.insert(0, str(_WEB_DIR))

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from routers import review as review_router  # noqa: E402
from folk import config, journal, person  # noqa: E402

PERSON_MD = """# Test Person

A test person for web/routers/review.py's containment tests.

## Tags
fixture
"""


class ReviewContainmentTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="folk-web-review-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.collection_dir = self.tmp / "characters"
        person_dir = self.collection_dir / "t" / "test-person"
        person_dir.mkdir(parents=True)
        (person_dir / "test-person.md").write_text(PERSON_MD, encoding="utf-8")

        self.journal_root = self.collection_dir / "journal"
        self.journal_root.mkdir()
        self.roots = [{"path": self.journal_root, "collection": "characters"}]

        self.vocab_path = self.tmp / "vocab.json"
        self.vocab_path.write_text(json.dumps({
            "types": ["person", "tag"],
            "predicates": {"tagged": "person carries this tag"},
            "aliases": {}, "stability": {}, "functional": [], "decay": {},
        }))
        vocab_patch = mock.patch.object(config, "VOCAB_FILE", self.vocab_path)
        vocab_patch.start()
        self.addCleanup(vocab_patch.stop)

        collections_patch = mock.patch(
            "routers.review.config.load_collections",
            return_value={"characters": str(self.collection_dir)},
        )
        collections_patch.start()
        self.addCleanup(collections_patch.stop)

        roots_patch = mock.patch(
            "routers.review.config.load_journal_roots", return_value=self.roots
        )
        roots_patch.start()
        self.addCleanup(roots_patch.stop)

        self.index_path = self.tmp / "triples.ndjson"

        def fake_rebuild():
            return journal.rebuild_index(
                collections={"characters": str(self.collection_dir)},
                roots=self.roots,
                index_path=self.index_path,
            )

        rebuild_patch = mock.patch("routers.review.triples.index_rebuild", side_effect=fake_rebuild)
        rebuild_patch.start()
        self.addCleanup(rebuild_patch.stop)

        # One session with an external counterparty, and one bedrock-level
        # promotion tied to it -- the shape review-queue.md's containment
        # rule is about: a counterparty-sourced suggestion that must never
        # be batch-acceptable.
        session_event = {
            "kind": "session", "actor": "human", "ts": "2026-07-01T00:00:00",
            "session": "sess1", "s": "", "p": "", "o": "",
            "counterparty": ["person:external-friend"],
        }
        promotion_event = {
            "kind": "promotion", "actor": "agent:test", "ts": "2026-07-01T00:05:00",
            "session": "sess1", "evidence": "stated", "level": "bedrock",
            "s": "person:test-person", "p": "tagged", "o": "tag:friend",
            "note": "test fixture note", "src": "msg:20260701_000000_aaaaaaaa#1",
        }
        journal.append_event(self.journal_root, "testwriter", session_event, run_lint=False)
        journal.append_event(self.journal_root, "testwriter", promotion_event, run_lint=False)

    def _get_pending_bedrock_item(self):
        items = review_router.get_review_queue()
        self.assertEqual(len(items["bedrock"]), 1)
        return items["bedrock"][0]

    def test_bedrock_item_surfaces_with_counterparty_marker(self):
        item = self._get_pending_bedrock_item()
        self.assertEqual(item["counterparty"], ["person:external-friend"])
        self.assertIn("preview", item)
        self.assertIn("diff", item["preview"])
        self.assertIn("external counterparty", item["description"])

    def test_action_endpoint_rejects_a_list_of_items_structurally(self):
        """The core containment proof: ReviewAction.item is typed as a
        single object. Handing it a list -- the shape a "select all ->
        accept" batch action would need -- must fail Pydantic validation
        before review_action() ever runs, not merely be discouraged by the
        UI."""
        item = self._get_pending_bedrock_item()
        with self.assertRaises(ValidationError):
            review_router.ReviewAction(item=[item, item], verdict="accept")
        # A bare list with no wrapping object at all is equally invalid.
        with self.assertRaises(ValidationError):
            review_router.ReviewAction.model_validate({"item": [item], "verdict": "accept"})

    def test_single_item_accept_applies_bedrock_edit_and_records_review(self):
        item = self._get_pending_bedrock_item()
        action = review_router.ReviewAction(item=item, verdict="accept")
        result = review_router.review_action(action)
        self.assertEqual(result["outcome"], "accepted")

        fpath = self.collection_dir / "t" / "test-person" / "test-person.md"
        sections = person._parse_sections(fpath.read_text())
        self.assertIn("friend", person._parse_tags(sections))

        # Queue is empty now -- a review event resolved the promotion.
        remaining = review_router.get_review_queue()
        self.assertEqual(remaining["bedrock"], [])

    def test_single_item_reject_leaves_no_person_file_change(self):
        item = self._get_pending_bedrock_item()
        action = review_router.ReviewAction(item=item, verdict="reject")
        result = review_router.review_action(action)
        self.assertEqual(result["outcome"], "rejected")

        fpath = self.collection_dir / "t" / "test-person" / "test-person.md"
        self.assertEqual(fpath.read_text(), PERSON_MD)

        remaining = review_router.get_review_queue()
        self.assertEqual(remaining["bedrock"], [])

    def test_unknown_item_type_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            review_router.review_action(
                review_router.ReviewAction(item={"type": "not-a-real-type"}, verdict="accept")
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_lint_failure_accept_is_rejected(self):
        """Matches the CLI: lint_failure items only ever offer reject
        (discard) -- there's no accept action for them."""
        with self.assertRaises(HTTPException) as ctx:
            review_router.review_action(
                review_router.ReviewAction(
                    item={"type": "lint_failure", "session": "x", "path": str(self.tmp / "nope.ndjson")},
                    verdict="accept",
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
