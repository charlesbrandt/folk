"""Tests for folk/surface.py's focus() -- docs/design/web-ui.md Decision 3,
"a thin second caller of [surface's] engine that ranks containers rather
than triples." Same fixture style as test_surface.py (temp collection +
journal root + vocab.json; no real Locus markdown file needed, since
focus() reads the already-rebuilt index the same way surface() does).
"""

import json
import shutil
import tempfile
import unittest
import unittest.mock
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


class FocusScenarioTestCase(unittest.TestCase):

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

    def focus(self, **kwargs):
        with unittest.mock.patch.object(journal.config, "VOCAB_FILE", self.vocab_path):
            return surface.focus(index_path=self.index_path, **kwargs)


class TestRanking(FocusScenarioTestCase):
    """sam is highly reinforced, recently active, curated (human tier), and
    well-connected; zed has a single, old, low-tier, disconnected fact.
    focus() must rank sam above zed on every one of the four signals.
    """

    def setUp(self):
        super().setUp()
        self.add_person("sam", associations_block="- [Ben](person:ben) — mentor")
        self.add_person("zed")
        events = [
            _event("2026-06-01T00:00:00", "person:sam", "interested_in", "topic:jazz"),
            _event("2026-06-15T00:00:00", "person:sam", "interested_in", "topic:jazz"),
            _event("2026-07-01T00:00:00", "person:sam", "researches", "topic:folklore"),
            _event("2020-01-01T00:00:00", "person:zed", "interested_in", "topic:origami"),
        ]
        _write_segment(self.journal_root, "2026-07.w.ndjson", events)
        self.rebuild()

    def test_more_reinforced_and_recent_and_connected_container_ranks_first(self):
        items = self.focus()
        ids = [it["id"] for it in items]
        self.assertIn("person:sam", ids)
        self.assertIn("person:zed", ids)
        self.assertLess(ids.index("person:sam"), ids.index("person:zed"))

    def test_result_shape(self):
        items = self.focus()
        for it in items:
            self.assertEqual(set(it.keys()), {"id", "tier", "reason"})

    def test_deterministic_across_repeated_calls(self):
        first = json.dumps(self.focus(), sort_keys=True)
        second = json.dumps(self.focus(), sort_keys=True)
        self.assertEqual(first, second)

    def test_budget_is_never_exceeded(self):
        items = self.focus(budget=1)
        self.assertEqual(len(items), 1)


class TestEmptyIndex(FocusScenarioTestCase):

    def test_empty_index_returns_empty_list_not_error(self):
        self.rebuild()  # no person files, no journal events
        self.assertEqual(self.focus(), [])


class TestScoping(FocusScenarioTestCase):

    def setUp(self):
        super().setUp()
        self.add_person("sam", associations_block="- [Writing Room](locus:writing-room) — guest_of")
        self.add_person("zed")
        events = [
            _event("2026-06-01T00:00:00", "person:sam", "researches", "topic:folklore",
                   locus="locus:writing-room"),
            _event("2026-06-01T00:00:00", "person:zed", "interested_in", "topic:origami"),
        ]
        _write_segment(self.journal_root, "2026-07.w.ndjson", events)
        self.rebuild()

    def test_locus_scope_excludes_containers_outside_the_focus_set(self):
        items = self.focus(locus_id="locus:writing-room")
        ids = {it["id"] for it in items}
        self.assertIn("person:sam", ids)
        self.assertNotIn("person:zed", ids)

    def test_person_scope_restricts_to_explicit_ids(self):
        items = self.focus(person_ids=["person:zed"])
        self.assertEqual([it["id"] for it in items], ["person:zed"])

    def test_collection_scope_matches_existing_collection(self):
        items = self.focus(collection="personal")
        ids = {it["id"] for it in items}
        self.assertIn("person:sam", ids)
        self.assertIn("person:zed", ids)

    def test_collection_scope_excludes_unknown_collection(self):
        self.assertEqual(self.focus(collection="nonexistent"), [])


if __name__ == "__main__":
    unittest.main()
