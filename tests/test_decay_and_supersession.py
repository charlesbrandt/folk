"""Tests for decay-and-supersession.md exit criteria: journal.staleness (a
pure read-time lens) and rebuild-time supersession of functional predicates,
plus the folk review classification proposal that lets a predicate become
classified in the first place.
"""

import json
import shutil
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta
from pathlib import Path

from folk import journal, review

REPO_ROOT = Path(__file__).resolve().parent.parent


def _event(ts, s, p, o, evidence="interpreted", level="core", actor="agent:x", note="n"):
    e = {"v": 1, "kind": "promotion", "actor": actor, "ts": ts,
         "evidence": evidence, "level": level, "s": s, "p": p, "o": o, "note": note}
    e["id"] = journal.compute_id(ts, actor, s, p, o)
    return e


def _write_segment(root, filename, events):
    root.mkdir(parents=True, exist_ok=True)
    with open(root / filename, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, sort_keys=True) + "\n")


class SupersessionScenarioTestCase(unittest.TestCase):
    """A temp collection with an optional person file + a temp journal root,
    plus a temp vocab.json (patched in via config.VOCAB_FILE, same technique
    as test_journal.py's TestAliasResolution) so functional/stability
    classifications never touch the real machine-local vocab.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.collection_dir = self.tmp / "personal"
        self.journal_root = self.collection_dir / "journal"
        self.journal_root.mkdir(parents=True)

        self.collections = {"personal": str(self.collection_dir)}
        self.roots = [{"path": self.journal_root, "collection": "personal"}]
        self.index_path = self.tmp / "triples.ndjson"
        self.vocab_path = self.tmp / "vocab.json"

    def write_vocab(self, **overrides):
        vocab = {"types": ["person", "org"], "predicates": {"works_at": "employer"},
                  "aliases": {}, "stability": {}, "functional": [], "decay": {}}
        vocab.update(overrides)
        self.vocab_path.write_text(json.dumps(vocab))

    def add_person(self, slug, associations_block=""):
        person_dir = self.collection_dir / slug[0] / slug
        person_dir.mkdir(parents=True)
        content = f"# {slug.title()}\n"
        if associations_block:
            content += f"\n## Associations\n{associations_block}\n"
        (person_dir / f"{slug}.md").write_text(content)

    def rebuild(self):
        with unittest.mock.patch.object(journal.config, "VOCAB_FILE", self.vocab_path):
            return journal.rebuild_index(collections=self.collections, roots=self.roots,
                                          index_path=self.index_path)

    def load_records(self):
        return journal.load_index(self.index_path)


class TestFunctionalSupersession(SupersessionScenarioTestCase):

    def setUp(self):
        super().setUp()
        self.write_vocab(functional=["works_at"])
        older = _event("2026-01-01T00:00:00", "person:sam", "works_at", "org:acme")
        newer = _event("2026-06-01T00:00:00", "person:sam", "works_at", "org:beta")
        self.older_id, self.newer_id = older["id"], newer["id"]
        _write_segment(self.journal_root, "2026-06.w.ndjson", [older, newer])

    def test_older_fact_gets_superseded_by_newer_event_id(self):
        self.rebuild()
        records = self.load_records()
        acme = next(r for r in records if r["o"] == "org:acme")
        beta = next(r for r in records if r["o"] == "org:beta")
        self.assertEqual(acme.get("superseded_by"), self.newer_id)
        self.assertNotIn("superseded_by", beta)

    def test_rebuild_twice_is_byte_identical(self):
        self.rebuild()
        first = self.index_path.read_bytes()
        self.rebuild()
        second = self.index_path.read_bytes()
        self.assertEqual(first, second)

    def test_rebuild_reports_superseded_count(self):
        n_triples, n_suggestions, n_superseded = self.rebuild()
        self.assertEqual(n_superseded, 1)


class TestUnclassifiedPredicateCoexists(SupersessionScenarioTestCase):

    def setUp(self):
        super().setUp()
        self.write_vocab(functional=[])  # unclassified
        older = _event("2026-01-01T00:00:00", "person:sam", "works_at", "org:acme")
        newer = _event("2026-06-01T00:00:00", "person:sam", "works_at", "org:beta")
        self.events = [older, newer]
        _write_segment(self.journal_root, "2026-06.w.ndjson", self.events)

    def test_both_facts_remain_current(self):
        self.rebuild()
        records = self.load_records()
        self.assertFalse(any(r.get("superseded_by") for r in records))
        self.assertEqual({r["o"] for r in records if r["p"] == "works_at"},
                          {"org:acme", "org:beta"})

    def test_review_surfaces_classification_proposal(self):
        with unittest.mock.patch.object(journal.config, "VOCAB_FILE", self.vocab_path):
            items = review.pending_items(roots=self.roots, index_path=self.index_path)
        classification = [it for it in items["vocab"]
                           if it.get("proposal_kind") == "functional_classification"]
        self.assertEqual(len(classification), 1)
        item = classification[0]
        self.assertEqual(item["p"], "works_at")
        self.assertEqual(item["s"], "person:sam")
        self.assertEqual(item["values"], ["org:acme", "org:beta"])
        self.assertIn(item["event_id"], {self.events[0]["id"], self.events[1]["id"]})

    def test_accepting_classification_then_rebuild_supersedes(self):
        with unittest.mock.patch.object(journal.config, "VOCAB_FILE", self.vocab_path):
            items = review.pending_items(roots=self.roots, index_path=self.index_path)
            item = next(it for it in items["vocab"]
                        if it.get("proposal_kind") == "functional_classification")
            vocab = review.accept_vocab(item)
            review.record_review(item, "accept", roots=self.roots)

        self.assertIn("works_at", vocab["functional"])

        self.rebuild()
        records = self.load_records()
        acme = next(r for r in records if r["o"] == "org:acme")
        beta = next(r for r in records if r["o"] == "org:beta")
        self.assertEqual(acme.get("superseded_by"), self.events[1]["id"])
        self.assertNotIn("superseded_by", beta)


class TestHumanTierNeverSuperseded(SupersessionScenarioTestCase):

    def setUp(self):
        super().setUp()
        self.write_vocab(functional=["works_at"])
        self.add_person("sam", "- [Acme](org:acme) — works_at")
        newer = _event("2026-06-01T00:00:00", "person:sam", "works_at", "org:beta")
        self.newer_id = newer["id"]
        _write_segment(self.journal_root, "2026-06.w.ndjson", [newer])

    def test_neither_side_is_superseded(self):
        self.rebuild()
        records = self.load_records()
        acme = next(r for r in records if r["o"] == "org:acme")
        beta = next(r for r in records if r["o"] == "org:beta")
        self.assertEqual(acme["tier"], "human")
        self.assertNotIn("superseded_by", acme)
        self.assertNotIn("superseded_by", beta, "a person-file fact must never supersede a journal fact either -- the machine doesn't resolve the tension, the human does")

    def test_holds_at_every_journal_evidence_tier(self):
        for evidence in ("stated", "interpreted"):
            with self.subTest(evidence=evidence):
                self.journal_root.mkdir(parents=True, exist_ok=True)
                for f in self.journal_root.glob("*.ndjson"):
                    f.unlink()
                newer = _event("2026-06-01T00:00:00", "person:sam", "works_at", "org:beta",
                                evidence=evidence)
                _write_segment(self.journal_root, "2026-06.w.ndjson", [newer])
                self.rebuild()
                records = self.load_records()
                acme = next(r for r in records if r["o"] == "org:acme")
                self.assertNotIn("superseded_by", acme)


class TestExactTieAnchors(SupersessionScenarioTestCase):

    def setUp(self):
        super().setUp()
        self.write_vocab(functional=["works_at"])
        a = _event("2026-01-01T00:00:00", "person:sam", "works_at", "org:acme")
        b = _event("2026-01-01T00:00:00", "person:sam", "works_at", "org:beta")
        _write_segment(self.journal_root, "2026-01.w.ndjson", [a, b])

    def test_no_supersession_on_exact_tie(self):
        self.rebuild()
        records = self.load_records()
        self.assertFalse(any(r.get("superseded_by") for r in records))


class TestStaleness(unittest.TestCase):

    def test_situational_predicate_goes_stale_under_far_future_now(self):
        vocab = {"stability": {"works_at": "situational"}, "functional": [], "decay": {}}
        record = {"p": "works_at", "last_reinforced": "2020-01-01T00:00:00"}
        now = datetime(2026, 1, 1)
        self.assertEqual(journal.staleness(record, now, vocab), "stale")

    def test_identity_predicate_never_stale(self):
        vocab = {"stability": {"born_in": "identity"}, "functional": [], "decay": {}}
        record = {"p": "born_in", "last_reinforced": "2000-01-01T00:00:00"}
        now = datetime(2026, 1, 1)
        self.assertEqual(journal.staleness(record, now, vocab), "fresh")

    def test_unclassified_predicate_never_stale(self):
        vocab = {"stability": {}, "functional": [], "decay": {}}
        record = {"p": "interested_in", "last_reinforced": "2000-01-01T00:00:00"}
        now = datetime(2026, 1, 1)
        self.assertEqual(journal.staleness(record, now, vocab), "fresh")

    def test_aging_before_stale(self):
        vocab = {"stability": {"works_at": "situational"}, "functional": [],
                  "decay": {"aging_days": 10, "stale_days": 100}}
        last = datetime(2026, 1, 1)
        record = {"p": "works_at", "last_reinforced": last.isoformat()}
        self.assertEqual(journal.staleness(record, last + timedelta(days=5), vocab), "fresh")
        self.assertEqual(journal.staleness(record, last + timedelta(days=20), vocab), "aging")
        self.assertEqual(journal.staleness(record, last + timedelta(days=200), vocab), "stale")


class TestNoWallClockInRebuild(SupersessionScenarioTestCase):

    def test_no_record_carries_a_staleness_or_now_derived_field(self):
        self.write_vocab(functional=["works_at"], stability={"works_at": "situational"})
        older = _event("2026-01-01T00:00:00", "person:sam", "works_at", "org:acme")
        newer = _event("2026-06-01T00:00:00", "person:sam", "works_at", "org:beta")
        _write_segment(self.journal_root, "2026-06.w.ndjson", [older, newer])
        self.rebuild()
        records = self.load_records()
        self.assertTrue(records)
        for r in records:
            self.assertNotIn("staleness", r)

    def test_rebuild_output_is_a_pure_function_of_input_regardless_of_wallclock(self):
        self.write_vocab(functional=["works_at"])
        older = _event("2026-01-01T00:00:00", "person:sam", "works_at", "org:acme")
        newer = _event("2026-06-01T00:00:00", "person:sam", "works_at", "org:beta")
        _write_segment(self.journal_root, "2026-06.w.ndjson", [older, newer])
        self.rebuild()
        first = self.index_path.read_bytes()
        # A second rebuild, no time passed simulated or otherwise -- nothing
        # in replay()/rebuild_index() reads datetime.now(), so this is
        # trivially identical; the real guarantee is structural (grep the
        # module), this just pins the observable behavior.
        self.rebuild()
        self.assertEqual(first, self.index_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
