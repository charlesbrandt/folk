"""Tests for the per-collection curation policy (docs/design/collection-curation.md).

Two halves: config.load_collection_descriptor resolves every on-disk state to
exactly "agent" or "human" (fail closed), and person.create_person_file_as_agent
-- the only path gated by it -- refuses everywhere except an explicitly
agent-curated collection. The human edit path is asserted unchanged.
"""

import os
import re
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from folk import config, person


class TestLoadCollectionDescriptor(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.coll = self.tmp / "collection"
        self.coll.mkdir()

    def _write_descriptor(self, text):
        (self.coll / config.COLLECTION_DESCRIPTOR_FILE).write_text(text, encoding="utf-8")

    def test_absent_file_resolves_to_human(self):
        self.assertEqual(config.load_collection_descriptor(self.coll), {"curation": "human"})

    def test_missing_collection_dir_resolves_to_human(self):
        self.assertEqual(
            config.load_collection_descriptor(self.tmp / "not-there")["curation"], "human")

    def test_malformed_json_resolves_to_human(self):
        self._write_descriptor('{"curation": "agent"')
        self.assertEqual(config.load_collection_descriptor(self.coll)["curation"], "human")

    def test_non_object_json_resolves_to_human(self):
        self._write_descriptor('["agent"]')
        self.assertEqual(config.load_collection_descriptor(self.coll)["curation"], "human")

    def test_unreadable_file_resolves_to_human(self):
        self._write_descriptor('{"curation": "agent"}')
        path = self.coll / config.COLLECTION_DESCRIPTOR_FILE
        if os.geteuid() == 0:
            self.skipTest("root ignores file permissions")
        path.chmod(0)
        self.addCleanup(path.chmod, stat.S_IRUSR | stat.S_IWUSR)
        self.assertEqual(config.load_collection_descriptor(self.coll)["curation"], "human")

    def test_a_directory_where_the_descriptor_should_be_resolves_to_human(self):
        (self.coll / config.COLLECTION_DESCRIPTOR_FILE).mkdir()
        self.assertEqual(config.load_collection_descriptor(self.coll)["curation"], "human")

    def test_explicit_human_resolves_to_human(self):
        self._write_descriptor('{"curation": "human"}')
        self.assertEqual(config.load_collection_descriptor(self.coll)["curation"], "human")

    def test_explicit_agent_resolves_to_agent(self):
        self._write_descriptor('{"curation": "agent"}')
        self.assertEqual(config.load_collection_descriptor(self.coll)["curation"], "agent")

    def test_unrecognized_value_resolves_to_human(self):
        self._write_descriptor('{"curation": "sometimes"}')
        self.assertEqual(config.load_collection_descriptor(self.coll)["curation"], "human")

    def test_non_string_value_resolves_to_human(self):
        self._write_descriptor('{"curation": true}')
        self.assertEqual(config.load_collection_descriptor(self.coll)["curation"], "human")

    def test_curation_key_absent_resolves_to_human(self):
        self._write_descriptor('{"something-else": "agent"}')
        self.assertEqual(config.load_collection_descriptor(self.coll)["curation"], "human")

    def test_unknown_keys_are_not_carried_through(self):
        # One key, one decision: nothing else in this pass reads or exposes
        # any other descriptor key (docs/design/collection-curation.md).
        self._write_descriptor('{"curation": "agent", "likeness": "emit"}')
        self.assertEqual(config.load_collection_descriptor(self.coll), {"curation": "agent"})

    def test_resolved_value_is_always_one_of_two_strings(self):
        for doc in ('', '{}', 'null', '{"curation": null}', '{"curation": "Agent"}',
                    '{"curation": " agent "}', '{"curation": "human"}', '{"curation": "agent"}'):
            with self.subTest(doc=doc):
                self._write_descriptor(doc)
                self.assertIn(config.load_collection_descriptor(self.coll)["curation"],
                              ("agent", "human"))


class TestCreatePersonFileAsAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.coll = self.tmp / "collection"
        self.coll.mkdir()

    def _set_curation(self, value):
        (self.coll / config.COLLECTION_DESCRIPTOR_FILE).write_text(
            '{"curation": "%s"}\n' % value, encoding="utf-8")

    def test_refuses_when_no_descriptor(self):
        with self.assertRaises(person.CurationRefused):
            person.create_person_file_as_agent(self.coll, "a-figure", "A Figure")
        self.assertEqual(list(person._person_files(self.coll)), [])

    def test_refuses_when_curation_is_human(self):
        self._set_curation("human")
        with self.assertRaises(person.CurationRefused) as ctx:
            person.create_person_file_as_agent(self.coll, "a-figure", "A Figure")
        message = str(ctx.exception)
        self.assertIn(str(self.coll), message)
        self.assertIn("human", message)
        self.assertEqual(list(person._person_files(self.coll)), [])

    def test_refuses_when_descriptor_is_malformed(self):
        (self.coll / config.COLLECTION_DESCRIPTOR_FILE).write_text("not json", encoding="utf-8")
        with self.assertRaises(person.CurationRefused):
            person.create_person_file_as_agent(self.coll, "a-figure", "A Figure")

    def test_creates_when_curation_is_agent(self):
        self._set_curation("agent")
        fpath = person.create_person_file_as_agent(
            self.coll, "a-figure", "A Figure", body="First-pass extraction.")
        self.assertEqual(fpath, self.coll / "a" / "a-figure" / "a-figure.md")
        self.assertEqual(fpath.read_text(encoding="utf-8"),
                         "# A Figure\n\nFirst-pass extraction.\n")
        self.assertEqual([slug for slug, _ in person._person_files(self.coll)], ["a-figure"])

    def test_created_file_reads_back_through_show_person(self):
        self._set_curation("agent")
        fpath = person.create_person_file_as_agent(self.coll, "b-figure", "B Figure")
        data = person.show_person(fpath)
        self.assertEqual(data["name"], "B Figure")

    def test_never_overwrites_an_existing_file(self):
        self._set_curation("agent")
        fpath = person.create_person_file_as_agent(self.coll, "a-figure", "A Figure")
        fpath.write_text("# A Figure\n\nHand-edited by the human.\n", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            person.create_person_file_as_agent(self.coll, "a-figure", "A Figure")
        self.assertIn("Hand-edited", fpath.read_text(encoding="utf-8"))

    def test_rejects_an_invalid_slug_before_touching_disk(self):
        self._set_curation("agent")
        for bad in ("", "a figure", "../escape", "-leading"):
            with self.subTest(slug=bad):
                with self.assertRaises(ValueError):
                    person.create_person_file_as_agent(self.coll, bad, "A Figure")


class TestHumanEditPathIsUngated(unittest.TestCase):
    """The policy governs creation by a machine and nothing else. A human-driven
    edit in a collection with no descriptor at all -- i.e. every collection that
    exists today -- behaves exactly as before.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.coll = self.tmp / "collection"
        for slug, heading in (("a-figure", "A Figure"), ("b-figure", "B Figure")):
            fpath = self.coll / slug[0] / slug / f"{slug}.md"
            fpath.parent.mkdir(parents=True)
            fpath.write_text(f"# {heading}\n\nA bio line.\n", encoding="utf-8")

    def _run_human_edits(self):
        person.add_tag(self.coll, "a-figure", "example")
        person.add_association(self.coll, "a-figure", "b-figure", "mentor")
        fpath = person._find_person_file(self.coll, "a-figure")
        person.append_line_to_section(fpath, "defining moments", "- something happened")
        return fpath.read_text(encoding="utf-8")

    def test_human_edits_unaffected_without_a_descriptor(self):
        text = self._run_human_edits()
        self.assertIn("example", text)
        self.assertIn("mentor", text)
        self.assertIn("something happened", text)

    def test_human_edits_identical_under_every_curation_policy(self):
        baseline = self._run_human_edits()
        for value in ("human", "agent", "sometimes"):
            with self.subTest(curation=value):
                self.setUp()
                (self.coll / config.COLLECTION_DESCRIPTOR_FILE).write_text(
                    '{"curation": "%s"}\n' % value, encoding="utf-8")
                self.assertEqual(self._run_human_edits(), baseline)


class TestNoCollectionNamesInFolkCode(unittest.TestCase):
    """Invariant 7, for this feature specifically: which collections are
    agent-curated is a data fact stated by each collection's own
    COLLECTION.json, never a name enumerated in folk's source.
    """

    def test_folk_package_names_no_domain_collections(self):
        # The registered domain collections, i.e. the names a well-meaning
        # refactor would most plausibly special-case once one of them declares
        # `curation: agent`. (Structural directory names like `journal/` and
        # `loci/` are conventions inside a collection, not collection names,
        # and are deliberately not listed.)
        folk_dir = Path(__file__).resolve().parent.parent / "folk"
        forbidden = ("characters", "authors", "musicians")
        # Word-boundary match, not substring: "authors" is a literal prefix
        # of "authorship", which shows up in ordinary prose (bulk.py) with no
        # connection to the collection name.
        patterns = {name: re.compile(rf"\b{re.escape(name)}\b") for name in forbidden}
        offenders = []
        for src in sorted(folk_dir.rglob("*.py")):
            text = src.read_text(encoding="utf-8").lower()
            for name, pattern in patterns.items():
                if pattern.search(text):
                    offenders.append(f"{src.name}: {name}")
        self.assertEqual(offenders, [], f"collection names found in folk/: {offenders}")


if __name__ == "__main__":
    unittest.main()
