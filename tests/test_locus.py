"""Tests for folk/locus.py, folk/config.py's load_loci_roots, and the
loci-aware parts of journal.py/graph.py, against docs/design/loci.md's exit
criteria.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from folk import config, graph, journal, locus, triples


def _write_md(path, heading, sections=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {heading}", ""]
    for name, body_lines in (sections or {}).items():
        lines.append(f"## {name}")
        lines.extend(body_lines)
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


def _wrap(event, idx):
    e = dict(event)
    e.setdefault("v", 1)
    ts = e.setdefault("ts", f"2026-07-2{idx}T00:00:00")
    actor = e.get("actor", "extract:v1")
    e["id"] = journal.compute_id(ts, actor, e.get("s", ""), e.get("p", ""), e.get("o", ""))
    return e


class TestLoadLociRoots(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.fiction_dir = self.tmp / "fiction"
        (self.fiction_dir / "loci").mkdir(parents=True)
        self.personal_dir = self.tmp / "personal"
        self.personal_dir.mkdir()  # no loci/ subdir -- should not become a root

        self.explicit_root = self.tmp / "cross-cutting-loci"
        self.explicit_root.mkdir()

        self.loci_roots_file = self.tmp / "loci-roots"

        self.collections_patch = mock.patch.object(
            config, "load_collections",
            return_value={"fiction": str(self.fiction_dir), "personal": str(self.personal_dir)},
        )
        self.roots_file_patch = mock.patch.object(config, "LOCI_ROOTS_FILE", self.loci_roots_file)
        self.collections_patch.start()
        self.roots_file_patch.start()
        self.addCleanup(self.collections_patch.stop)
        self.addCleanup(self.roots_file_patch.stop)

    def test_automatic_root_from_collection_with_loci_subdir(self):
        roots = config.load_loci_roots()
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]["collection"], "fiction")
        self.assertEqual(Path(roots[0]["path"]), self.fiction_dir / "loci")

    def test_explicit_root_added_from_loci_roots_file(self):
        self.loci_roots_file.write_text(json.dumps([
            {"path": str(self.explicit_root), "collection": "personal"},
        ]))
        roots = config.load_loci_roots()
        collections = {r["collection"] for r in roots}
        self.assertEqual(collections, {"fiction", "personal"})


class LociScenarioTestCase(unittest.TestCase):
    """A Locus registered both mechanisms (automatic under 'fiction', explicit
    cross-cutting root scoped to 'personal'), a person:sam who has one
    locus-tagged (ephemeral) journal event and one unrelated fact, and a
    second Locus's curated guest_of edge -- mirrors loci.md's own examples.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.fiction_dir = self.tmp / "fiction"
        _write_md(
            self.fiction_dir / "loci" / "murakami-world" / "murakami-world.md",
            "Murakami World",
            sections={"Genius Loci": ["A liminal, melancholy place."], "Tags": ["fiction"]},
        )

        self.personal_dir = self.tmp / "personal"
        _write_md(
            self.personal_dir / "s" / "sam" / "sam.md",
            "Sam",
            sections={"Tags": ["friend"]},
        )

        self.explicit_root = self.tmp / "cross-cutting-loci"
        _write_md(
            self.explicit_root / "night-owl-club" / "night-owl-club.md",
            "Night Owl Club",
            sections={"Genius Loci": ["Late-night, low-stakes."]},
        )

        self.journal_root = self.personal_dir / "journal"
        self.journal_root.mkdir(parents=True)
        events = [
            _wrap({"kind": "observation", "actor": "extract:v1", "s": "person:sam",
                   "p": "participated_in", "o": "conv:scene1", "session": "conv:scene1",
                   "locus": "locus:murakami-world"}, 1),
            _wrap({"kind": "promotion", "actor": "agent:hermes-main", "evidence": "interpreted",
                   "level": "core", "s": "person:sam", "p": "interested_in", "o": "topic:jazz",
                   "note": "unrelated, no locus tag", "src": "msg:conv:other#0"}, 2),
        ]
        with open(self.journal_root / "2026-07.testwriter.ndjson", "w") as f:
            for e in events:
                f.write(json.dumps(e, sort_keys=True) + "\n")

        self.collections = {"fiction": str(self.fiction_dir), "personal": str(self.personal_dir)}
        self.roots = [{"path": self.journal_root, "collection": "personal"}]
        self.loci_roots = [
            {"path": self.fiction_dir / "loci", "collection": "fiction"},
            {"path": self.explicit_root, "collection": "personal"},
        ]
        self.index_path = self.tmp / "triples.ndjson"
        # graph.py reads through triples.query(), which always reads
        # triples.DEFAULT_INDEX -- point it at this scenario's index so
        # graph.locus_edges() sees the same rebuilt data the other
        # assertions read via journal.load_index(self.index_path).
        self.index_patch = mock.patch.object(triples, "DEFAULT_INDEX", self.index_path)
        self.index_patch.start()
        self.addCleanup(self.index_patch.stop)

    def rebuild(self):
        return journal.rebuild_index(
            collections=self.collections, roots=self.roots, loci_roots=self.loci_roots,
            index_path=self.index_path)

    def sam_file(self):
        return self.personal_dir / "s" / "sam" / "sam.md"

    def locus_file(self):
        return self.fiction_dir / "loci" / "murakami-world" / "murakami-world.md"


class TestBothRegistrationMechanismsResolve(LociScenarioTestCase):

    def test_automatic_and_explicit_roots_both_resolve_via_find_locus_file(self):
        auto = locus.find_locus_file(self.loci_roots, "murakami-world")
        explicit = locus.find_locus_file(self.loci_roots, "night-owl-club")
        self.assertEqual(auto, self.locus_file())
        self.assertEqual(explicit, self.explicit_root / "night-owl-club" / "night-owl-club.md")

    def test_show_locus_reads_genius_loci_section(self):
        info = locus.show_locus(self.locus_file())
        self.assertEqual(info["name"], "Murakami World")
        self.assertIn("A liminal, melancholy place.", info["content"])


class TestLocusRecordsBarrier(LociScenarioTestCase):

    def test_locus_tagged_event_is_in_scope(self):
        self.rebuild()
        records = journal.locus_records("locus:murakami-world", index_path=self.index_path)
        self.assertTrue(any(r["p"] == "participated_in" and r["s"] == "person:sam" for r in records))

    def test_unrelated_untagged_triple_stays_out_of_scope(self):
        self.rebuild()
        records = journal.locus_records("locus:murakami-world", index_path=self.index_path)
        self.assertFalse(any(r["o"] == "topic:jazz" for r in records),
                           "a triple that is neither locus-tagged nor a curated cast edge must not appear")


class TestGraphLocusCastList(LociScenarioTestCase):

    def test_ephemeral_guest_scene_absent_from_cast_list(self):
        # The Locus's own ## Tags section still produces a legitimate
        # curated (human-tier) edge -- what must be absent is any edge
        # naming person:sam, since his only connection to this Locus so
        # far is the bare locus-tagged event, not a curated guest_of.
        self.rebuild()
        edges = graph.locus_edges("locus:murakami-world")
        self.assertFalse(any(n == "person:sam" for s, _p, o in edges for n in (s, o)),
                          "a bare locus-tagged event must not create a cast-list edge")

    def test_guest_of_curated_in_persons_file_adds_them_to_cast_list_on_rebuild(self):
        self.rebuild()
        before = graph.locus_edges("locus:murakami-world")
        self.assertFalse(any(o == "locus:murakami-world" for _s, _p, o in before))

        with open(self.sam_file(), "a") as f:
            f.write("\n## Associations\n- [Murakami World](locus:murakami-world) — guest_of\n")

        self.rebuild()
        after = graph.locus_edges("locus:murakami-world")
        self.assertIn(("person:sam", "guest_of", "locus:murakami-world"), after)


class TestPersonProfileNotWidenedByLocusCuratedGuest(LociScenarioTestCase):

    def test_locus_authored_guest_of_edge_does_not_widen_persons_own_profile(self):
        self.rebuild()
        before = journal.person_profile("person:sam", index_path=self.index_path)

        with open(self.locus_file(), "a") as f:
            f.write("\n## Associations\n- [Sam](person:sam) — guest_of\n")
        self.rebuild()

        after = journal.person_profile("person:sam", index_path=self.index_path)
        self.assertEqual(before, after,
                          "a guest_of edge curated in the Locus's own file must not widen "
                          "person:sam's own default profile")

        locus_records = journal.locus_records("locus:murakami-world", index_path=self.index_path)
        self.assertTrue(any(r["s"] == "locus:murakami-world" and r["o"] == "person:sam"
                             and r["p"] == "guest_of" for r in locus_records),
                         "the same edge must still surface in the Locus's own profile")


class TestNoCollisionWithPersonFileWalk(LociScenarioTestCase):

    def test_locus_files_never_read_as_person_files(self):
        from folk.person import list_persons
        people = list_persons(self.fiction_dir)
        self.assertFalse(any(name == "Murakami World" for name, _fpath in people))


class TestLocusType(unittest.TestCase):
    """Tests for `## Locus Type` (docs/design/locus-type.md) -- an open,
    unenumerated classifier value, parsed the same way as ## Archetype/
    ## Voice via person._parse_free_text.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_locus_type_parses_via_show_locus(self):
        fpath = self.tmp / "iusm-neurology" / "iusm-neurology.md"
        _write_md(fpath, "Neurology", sections={
            "Locus Type": ["department"],
            "Genius Loci": ["Fluorescent hallways, quiet urgency."],
        })
        info = locus.show_locus(fpath)
        self.assertEqual(info["locus_type"], "department")

    def test_missing_locus_type_is_empty_string_not_error(self):
        fpath = self.tmp / "murakami-world" / "murakami-world.md"
        _write_md(fpath, "Murakami World", sections={
            "Genius Loci": ["A liminal, melancholy place."],
        })
        info = locus.show_locus(fpath)
        self.assertEqual(info["locus_type"], "")

    def test_locus_type_also_present_and_empty_on_ordinary_person_files(self):
        # Consistent with how appearance/appearance_checkpoints already
        # behave on non-Locus files: the key always exists, just empty.
        fpath = self.tmp / "s" / "sam" / "sam.md"
        _write_md(fpath, "Sam", sections={"Tags": ["friend"]})
        from folk.person import show_person
        info = show_person(fpath)
        self.assertEqual(info["locus_type"], "")


class TestNoLocusTypeEnumerationInCode(unittest.TestCase):
    """docs/design/locus-type.md's hard constraint, same reasoning as
    invariant 7 and appearance.md Decision 2: the Locus Type value set is
    open, so no locus-type value may appear anywhere in folk's own source.

    Sampled from the conventional set documented in locus-type.md/the folk
    skill, favoring distinctive multi-word compounds over single common
    English words -- "department" or "resource" alone would false-positive
    against ordinary, unrelated code (e.g. a scraped record's "department"
    field name in folk/sources/directory_scrape.py, which describes a
    person's org unit and has nothing to do with folk validating Locus Type
    values), the same reason appearance.md's own test picks "distinguishing
    marks" over "hair".
    """

    def test_folk_package_names_no_locus_type_values(self):
        folk_dir = Path(__file__).resolve().parent.parent / "folk"
        forbidden = ("research-center", "research center", "narrative-place")
        offenders = []
        for src in sorted(folk_dir.rglob("*.py")):
            text = src.read_text(encoding="utf-8").lower()
            for value in forbidden:
                if value in text:
                    offenders.append(f"{src.name}: {value}")
        self.assertEqual(offenders, [], f"locus-type values found in folk/: {offenders}")


if __name__ == "__main__":
    unittest.main()
