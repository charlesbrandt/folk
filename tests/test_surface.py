"""Tests for folk/surface.py against docs/design/folk-surface.md's exit
criteria: the four-ranker RRF query over the triple index, focus-set
expansion via loci.md's cast-list machinery, and the staleness/supersession
filters carried over from decay-and-supersession.md.
"""

import json
import shutil
import tempfile
import unittest
import unittest.mock
from datetime import datetime
from pathlib import Path

from folk import journal, surface


def _event(ts, s, p, o, kind="observation", locus=None, actor="extract:v1", session="conv:x"):
    e = {"v": 1, "kind": kind, "actor": actor, "ts": ts, "s": s, "p": p, "o": o, "session": session}
    if kind == "promotion":
        e["evidence"] = "interpreted"
        e["level"] = "core"
        e["note"] = "n"
    if locus:
        e["locus"] = locus
    e["id"] = journal.compute_id(ts, actor, s, p, o)
    return e


def _write_segment(root, filename, events):
    root.mkdir(parents=True, exist_ok=True)
    with open(root / filename, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, sort_keys=True) + "\n")


class SurfaceScenarioTestCase(unittest.TestCase):
    """A temp 'personal' collection + journal root + vocab.json, no real
    Locus markdown files needed -- surface.py reads the already-rebuilt
    index via journal.locus_records()/load_index(), so a curated guest_of
    association in a person file is enough to put that person in a Locus's
    cast list (loci.md's barrier machinery, exercised the same way
    test_locus.py does, minus the Locus file itself since nothing here
    calls folk show locus:X).
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
        self.write_vocab()

    def write_vocab(self, **overrides):
        vocab = {"types": ["person", "org", "topic", "work", "locus"], "predicates": {},
                  "aliases": {}, "stability": {}, "functional": [], "decay": {}}
        vocab.update(overrides)
        self.vocab_path.write_text(json.dumps(vocab))

    def add_person(self, slug, name=None, associations_block=""):
        person_dir = self.collection_dir / slug[0] / slug
        person_dir.mkdir(parents=True)
        content = f"# {name or slug.title()}\n"
        if associations_block:
            content += f"\n## Associations\n{associations_block}\n"
        (person_dir / f"{slug}.md").write_text(content)

    def rebuild(self):
        with unittest.mock.patch.object(journal.config, "VOCAB_FILE", self.vocab_path):
            return journal.rebuild_index(collections=self.collections, roots=self.roots,
                                          loci_roots=[], index_path=self.index_path)

    def surface(self, **kwargs):
        with unittest.mock.patch.object(journal.config, "VOCAB_FILE", self.vocab_path):
            return surface.surface(index_path=self.index_path, **kwargs)


class TestCrossLocusFixture(SurfaceScenarioTestCase):
    """mira has a fact established while scoped to locus:archive-room (A)
    and is curated as a guest_of locus:writing-room (B, the session
    context) -- the planted fixture from the spec's Scope section: "a
    shared entity spanning two loci that must surface."
    """

    def setUp(self):
        super().setUp()
        self.add_person("mira", associations_block="- [Writing Room](locus:writing-room) — guest_of")
        events = [
            # Established in locus A -- the cross-locus fact that should surface.
            _event("2026-07-10T00:00:00", "person:mira", "researches", "topic:folklore",
                   locus="locus:archive-room"),
            # In-slice for locus B -- must never appear in surface's output.
            _event("2026-07-15T00:00:00", "person:mira", "drafted", "work:draft-7",
                   locus="locus:writing-room"),
        ]
        _write_segment(self.journal_root, "2026-07.w.ndjson", events)
        self.rebuild()

    def test_cross_locus_fact_surfaces_in_top_3_with_shared_entity_reason(self):
        items = self.surface(locus_id="locus:writing-room")
        self.assertTrue(items, "expected the cross-locus fact to surface")
        top3 = items[:3]
        hit = [it for it in top3 if it["o"] == "topic:folklore"]
        self.assertEqual(len(hit), 1, f"expected the mira/folklore fact in the top 3, got {items}")
        self.assertIn("shared entity with locus:writing-room", hit[0]["reason"])

    def test_in_slice_fact_never_appears(self):
        items = self.surface(locus_id="locus:writing-room")
        self.assertFalse(any(it["o"] == "work:draft-7" for it in items),
                          "a fact already inside the queried Locus's own slice must not be re-surfaced")

    def test_byte_identical_across_repeated_runs_with_fixed_now(self):
        now = datetime(2026, 7, 23)
        first = json.dumps(self.surface(locus_id="locus:writing-room", now=now), sort_keys=True)
        second = json.dumps(self.surface(locus_id="locus:writing-room", now=now), sort_keys=True)
        self.assertEqual(first, second)

    def test_no_writes(self):
        before = self.index_path.read_bytes()
        before_files = sorted(p.name for p in self.tmp.rglob("*") if p.is_file())
        self.surface(locus_id="locus:writing-room")
        self.assertEqual(before, self.index_path.read_bytes())
        after_files = sorted(p.name for p in self.tmp.rglob("*") if p.is_file())
        self.assertEqual(before_files, after_files)


class TestDisconnectedFixture(SurfaceScenarioTestCase):
    """person:zeke is the sole cast member of locus:solo-room and has no
    other facts anywhere -- the disconnected fixture that must surface
    nothing, per Scope.
    """

    def setUp(self):
        super().setUp()
        self.add_person("zeke", associations_block="- [Solo Room](locus:solo-room) — guest_of")
        self.rebuild()

    def test_emits_nothing(self):
        items = self.surface(locus_id="locus:solo-room")
        self.assertEqual(items, [])


class TestPersonOnlyInvocation(SurfaceScenarioTestCase):
    """--person-only invocation must work before any real Locus exists."""

    def setUp(self):
        super().setUp()
        events = [_event("2026-07-10T00:00:00", "person:sam", "interested_in", "topic:jazz")]
        _write_segment(self.journal_root, "2026-07.w.ndjson", events)
        self.rebuild()

    def test_works_with_no_locus_configured(self):
        items = self.surface(person_ids=["person:sam"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["o"], "topic:jazz")

    def test_no_locus_no_person_returns_empty(self):
        self.assertEqual(self.surface(), [])


class TestBudgetAndSupersession(SurfaceScenarioTestCase):

    def setUp(self):
        super().setUp()
        self.write_vocab(functional=["works_at"])
        self.add_person("sam", associations_block="- [Writing Room](locus:writing-room) — guest_of")
        events = [
            _event("2026-01-01T00:00:00", "person:sam", "works_at", "org:acme", kind="promotion"),
            _event("2026-06-01T00:00:00", "person:sam", "works_at", "org:beta", kind="promotion"),
            _event("2026-06-01T00:00:00", "person:sam", "interested_in", "topic:jazz"),
        ]
        _write_segment(self.journal_root, "2026-07.w.ndjson", events)
        self.rebuild()

    def test_superseded_record_never_appears(self):
        items = self.surface(locus_id="locus:writing-room")
        self.assertFalse(any(it["o"] == "org:acme" for it in items),
                          "the superseded org:acme fact must be excluded outright")
        self.assertTrue(any(it["o"] == "org:beta" for it in items))

    def test_budget_is_never_exceeded(self):
        items = self.surface(locus_id="locus:writing-room", budget=1)
        self.assertEqual(len(items), 1)


class TestStalenessDemotion(SurfaceScenarioTestCase):

    def setUp(self):
        super().setUp()
        self.write_vocab(stability={"interested_in": "situational"},
                          decay={"aging_days": 10, "stale_days": 100})
        self.add_person("sam", associations_block="- [Writing Room](locus:writing-room) — guest_of")
        events = [
            _event("2020-01-01T00:00:00", "person:sam", "interested_in", "topic:origami"),
            _event("2026-06-01T00:00:00", "person:sam", "researches", "topic:folklore"),
        ]
        _write_segment(self.journal_root, "2026-07.w.ndjson", events)
        self.rebuild()

    def test_stale_record_demoted_below_budget(self):
        now = datetime(2026, 7, 1)
        items = self.surface(locus_id="locus:writing-room", now=now, budget=1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["o"], "topic:folklore", "the fresh record must fill a tight budget first")

    def test_stale_record_still_appears_when_budget_allows(self):
        now = datetime(2026, 7, 1)
        items = self.surface(locus_id="locus:writing-room", now=now, budget=12)
        self.assertEqual({it["o"] for it in items}, {"topic:origami", "topic:folklore"})


if __name__ == "__main__":
    unittest.main()
