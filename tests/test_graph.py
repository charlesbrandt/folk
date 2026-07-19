"""Tests for folk/graph.py against collections-and-graph.md's exit criteria."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from folk import graph, triples


def _write_person(path, heading, associations=(), tags=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {heading}", ""]
    if associations:
        lines.append("## Associations")
        for target, ref, rel in associations:
            href = f"({ref})" if ref else ""
            lines.append(f"- [{target}]{href} — {rel}")
        lines.append("")
    if tags:
        lines.append("## Tags")
        lines.append(" ".join(tags))
    path.write_text("\n".join(lines) + "\n")


class GraphTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        authors_dir = self.tmp / "authors"
        characters_dir = self.tmp / "characters"

        _write_person(
            authors_dir / "h" / "haruki-murakami" / "haruki-murakami.md",
            "Haruki Murakami",
            associations=[("Norwegian Wood", "work:norwegian-wood", "created")],
            tags=["author"],
        )
        _write_person(
            characters_dir / "t" / "toru-watanabe" / "toru-watanabe.md",
            "Toru Watanabe",
            associations=[("Norwegian Wood", "work:norwegian-wood", "appears_in")],
            tags=["character", "protagonist"],
        )
        _write_person(
            characters_dir / "n" / "naoko" / "naoko.md",
            "Naoko",
            associations=[("Norwegian Wood", "work:norwegian-wood", "appears_in")],
            tags=["character"],
        )

        self.collections = {"authors": str(authors_dir), "characters": str(characters_dir)}
        self.collections_patch = mock.patch("folk.graph.config.load_collections", return_value=self.collections)
        self.collections_patch.start()
        self.addCleanup(self.collections_patch.stop)

        self.index_path = self.tmp / "triples.ndjson"
        self.index_patch = mock.patch.object(triples, "DEFAULT_INDEX", self.index_path)
        self.index_patch.start()
        self.addCleanup(self.index_patch.stop)

        from folk import journal
        journal.rebuild_index(collections=self.collections, roots=[], index_path=self.index_path)


class TestBuildPersonIndex(GraphTestBase):

    def test_indexes_people_across_all_collections(self):
        index = graph.build_person_index()
        self.assertEqual(index["haruki-murakami"], "Haruki Murakami")
        self.assertEqual(index["toru-watanabe"], "Toru Watanabe")
        self.assertEqual(index["naoko"], "Naoko")


class TestFindPerson(GraphTestBase):

    def test_exact_slug_match(self):
        result = graph.find_person("Haruki Murakami")
        self.assertEqual(result["match"], {"slug": "haruki-murakami", "name": "Haruki Murakami"})
        self.assertEqual(result["near_matches"], [])

    def test_exact_display_name_match_with_mismatched_slug(self):
        # heading text doesn't slugify to the file's own slug -- a real
        # edge case (renamed person, slug not regenerated) -- so the
        # display-name fallback, not the slug-key lookup, must catch it.
        _write_person(
            self.tmp / "characters" / "r" / "renamed-person" / "renamed-person.md",
            "Someone Else",
        )
        result = graph.find_person("Someone Else")
        self.assertEqual(result["match"], {"slug": "renamed-person", "name": "Someone Else"})

    def test_near_duplicate_surfaced_not_auto_matched(self):
        result = graph.find_person("Toru Extra Watanabe")
        self.assertIsNone(result["match"])
        self.assertEqual(result["near_matches"], [{"slug": "toru-watanabe", "name": "Toru Watanabe"}])

    def test_no_match_for_unrelated_name(self):
        result = graph.find_person("Completely Different Person")
        self.assertIsNone(result["match"])
        self.assertEqual(result["near_matches"], [])


class TestEdgeCollectionFilters(GraphTestBase):

    def test_typed_ref_association_produces_work_object_not_person(self):
        edges = graph.collection_edges("authors")
        self.assertIn(("person:haruki-murakami", "created", "work:norwegian-wood"), edges)

    def test_collection_scoping_excludes_other_collections(self):
        edges = graph.collection_edges("authors")
        subjects = {s for s, _p, _o in edges}
        self.assertNotIn("person:toru-watanabe", subjects)

    def test_context_edges_filters_by_tag(self):
        edges = graph.context_edges("protagonist")
        subjects_and_objects = {n for s, _p, o in edges for n in (s, o)}
        self.assertIn("person:toru-watanabe", subjects_and_objects)
        self.assertNotIn("person:naoko", subjects_and_objects)


class TestEgoGraph(GraphTestBase):

    def test_depth_2_reaches_character_through_shared_work(self):
        # exit criterion: folk graph --person haruki-murakami --depth 2 reaches
        # the characters through the works (author -> work -> character).
        edges = graph.ego_edges("person:haruki-murakami", depth=2)
        nodes = graph.nodes_from_edges(edges)
        self.assertIn("person:toru-watanabe", nodes)
        self.assertIn("person:naoko", nodes)
        self.assertIn("work:norwegian-wood", nodes)

    def test_depth_1_stops_at_the_work(self):
        edges = graph.ego_edges("person:haruki-murakami", depth=1)
        nodes = graph.nodes_from_edges(edges)
        self.assertIn("work:norwegian-wood", nodes)
        self.assertNotIn("person:toru-watanabe", nodes)


class TestRenderMermaid(GraphTestBase):

    def test_output_is_deterministic_and_declares_nodes_before_edges(self):
        edges = graph.collection_edges("authors")
        person_index = graph.build_person_index()
        first = graph.render_mermaid(edges, person_index)
        second = graph.render_mermaid(edges, person_index)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("graph TD\n"))
        first_edge_line = next(i for i, l in enumerate(first.splitlines()) if "-->" in l)
        last_node_line = max(i for i, l in enumerate(first.splitlines()) if l.strip().startswith('person_') or l.strip().startswith('work_'))
        # every node declaration line with a label (no "-->") must precede the first edge line
        node_decl_lines = [i for i, l in enumerate(first.splitlines()) if "[" in l and "-->" not in l]
        self.assertTrue(all(i < first_edge_line for i in node_decl_lines))

    def test_non_person_entity_falls_back_to_slug_label(self):
        edges = graph.collection_edges("authors")
        person_index = graph.build_person_index()
        rendered = graph.render_mermaid(edges, person_index)
        self.assertIn('["norwegian wood"]', rendered)


if __name__ == "__main__":
    unittest.main()
