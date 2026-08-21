"""Tests for `## Appearance` against docs/design/appearance.md's exit criteria."""

import argparse
import io
import json
import shutil
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path

from folk import cli, person, render


def _write_md(path, heading, sections=None, bio=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {heading}", ""]
    if bio:
        lines.append(bio)
        lines.append("")
    for name, body_lines in (sections or {}).items():
        lines.append(f"## {name}")
        lines.extend(body_lines)
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


APPEARANCE_LINES = [
    "- build: narrow, stooped from years of reaching upward",
    "- hair: cropped close, gone grey at the temples",
    "- distinguishing marks: a burn scar across the right hand",
]


class TestAppearanceParsing(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _fixture(self, appearance_lines, slug="lamplighter"):
        fpath = self.tmp / slug[0] / slug / f"{slug}.md"
        _write_md(fpath, "The Lamplighter", bio="Tends the lamps.",
                  sections={"Appearance": appearance_lines})
        return fpath

    def test_round_trips_through_show_person(self):
        info = person.show_person(self._fixture(APPEARANCE_LINES))
        self.assertEqual(
            info["appearance"]["labels"],
            [
                {"label": "build", "value": "narrow, stooped from years of reaching upward"},
                {"label": "hair", "value": "cropped close, gone grey at the temples"},
                {"label": "distinguishing marks", "value": "a burn scar across the right hand"},
            ],
        )
        self.assertEqual(info["appearance"]["note"], "")

    def test_absent_section_is_empty_not_missing(self):
        fpath = self.tmp / "j" / "jane-doe" / "jane-doe.md"
        _write_md(fpath, "Jane Doe", bio="Brief description.")
        info = person.show_person(fpath)
        self.assertEqual(info["appearance"], {"labels": [], "note": ""})
        self.assertEqual(person.appearance_text(info["appearance"]), "")
        self.assertEqual(person.appearance_fingerprint(info["appearance"]), "")

    def test_unlabeled_prose_reaches_note_rather_than_being_dropped(self):
        """Exit criterion: prose written under ## Appearance must survive."""
        info = person.show_person(self._fixture(
            APPEARANCE_LINES + ["Carries the pole always, even when unlit."]))
        self.assertEqual(info["appearance"]["note"], "Carries the pole always, even when unlit.")
        self.assertIn("Carries the pole always", person.appearance_text(info["appearance"]))

    def test_prose_only_section_still_reaches_appearance_text(self):
        info = person.show_person(self._fixture(["Tall, weathered, never without the coat."]))
        self.assertEqual(info["appearance"]["labels"], [])
        self.assertEqual(person.appearance_text(info["appearance"]),
                         "Tall, weathered, never without the coat.")

    def test_label_order_is_file_order(self):
        info = person.show_person(self._fixture(list(reversed(APPEARANCE_LINES))))
        self.assertEqual([i["label"] for i in info["appearance"]["labels"]],
                         ["distinguishing marks", "hair", "build"])

    def test_appearance_text_joins_labels_then_note(self):
        info = person.show_person(self._fixture(
            ["- build: narrow", "- hair: grey", "Never without the coat."]))
        self.assertEqual(person.appearance_text(info["appearance"]),
                         "build: narrow; hair: grey; Never without the coat.")

    def test_fingerprint_is_stable_and_brief_specific(self):
        a = person.show_person(self._fixture(["- build: narrow"], slug="a-one"))
        b = person.show_person(self._fixture(["- build: narrow"], slug="b-two"))
        c = person.show_person(self._fixture(["- build: broad"], slug="c-three"))
        fp = person.appearance_fingerprint
        self.assertEqual(fp(a["appearance"]), fp(b["appearance"]))
        self.assertNotEqual(fp(a["appearance"]), fp(c["appearance"]))
        self.assertEqual(len(fp(a["appearance"])), 12)


class TestAppearanceRender(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fpath = self.tmp / "l" / "lamplighter" / "lamplighter.md"
        _write_md(
            self.fpath, "The Lamplighter",
            bio="Tends the lamps.",
            sections={
                "Archetype": ["keeper of small lights"],
                "Voice": ["few words, spoken late"],
                "Appearance": APPEARANCE_LINES + ["Carries the pole always."],
                "Tags": ["character"],
            },
        )

    def test_soul_places_appearance_after_voice(self):
        out = render.render_soul(self.fpath)
        self.assertIn("## Appearance", out)
        self.assertLess(out.index("## Voice"), out.index("## Appearance"))
        self.assertLess(out.index("## Appearance"), out.index("## Tags"))
        self.assertIn("- build: narrow, stooped from years of reaching upward", out)
        self.assertIn("Carries the pole always.", out)

    def test_soul_omits_empty_appearance_without_an_empty_header(self):
        bare = self.tmp / "j" / "jane-doe" / "jane-doe.md"
        _write_md(bare, "Jane Doe", bio="Brief.")
        self.assertNotIn("## Appearance", render.render_soul(bare))

    def test_dream_json_carries_appearance_as_a_sibling_of_description(self):
        data = json.loads(render.render_dream_json(self.fpath))
        # Decision 4: description stays bio + Archetype/Voice, so a consumer
        # that predates this keeps working and nothing double-prints.
        self.assertNotIn("build:", data["description"])
        self.assertNotIn("Appearance", data["description"])
        self.assertEqual(data["appearance"][0],
                         {"label": "build", "value": "narrow, stooped from years of reaching upward"})
        self.assertIn("hair: cropped close", data["appearance_text"])
        self.assertEqual(len(data["appearance_fingerprint"]), 12)

    def test_dream_json_key_order_is_stable_and_additive(self):
        data = json.loads(render.render_dream_json(self.fpath))
        self.assertEqual(
            list(data.keys()),
            ["kind", "slug", "name", "description", "appearance", "appearance_text",
             "appearance_fingerprint", "checkpoint", "checkpoints", "tags", "associations",
             "defining_moments"],
        )

    def test_undescribed_figure_still_resolves_cleanly(self):
        """A missing shell is the normal case, never an error: description
        stays non-empty and the appearance keys are [] / "" , never null --
        the contract folkref.resolve checks on the consumer side.
        """
        bare = self.tmp / "j" / "jane-doe" / "jane-doe.md"
        _write_md(bare, "Jane Doe", bio="Brief description.")
        data = json.loads(render.render_dream_json(bare))
        self.assertTrue(data["description"].strip())
        self.assertEqual(data["appearance"], [])
        self.assertEqual(data["appearance_text"], "")
        self.assertEqual(data["appearance_fingerprint"], "")

    def test_dream_readable_form_appends_an_appearance_block(self):
        out = render.render_dream(self.fpath)
        self.assertIn("Appearance:", out)
        self.assertLess(out.index("Voice:"), out.index("Appearance:"))
        self.assertTrue(out.endswith("\n"))

    def test_both_formats_are_byte_identical_across_runs(self):
        for fmt in ("soul", "dream"):
            self.assertEqual(render.render(fmt, self.fpath), render.render(fmt, self.fpath))
        self.assertEqual(render.render_dream_json(self.fpath), render.render_dream_json(self.fpath))


class TestAppearanceCli(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fpath = self.tmp / "l" / "lamplighter" / "lamplighter.md"
        _write_md(self.fpath, "The Lamplighter", bio="Tends the lamps.",
                  sections={"Appearance": APPEARANCE_LINES, "Tags": ["character"]})

    def test_show_displays_appearance(self):
        args = argparse.Namespace(name="lamplighter", collection=None)
        buf = io.StringIO()
        with unittest.mock.patch.object(cli, "_resolve", return_value=(self.tmp, "fixture")):
            with redirect_stdout(buf):
                cli.cmd_show(args)
        out = buf.getvalue()
        self.assertIn("Appearance:", out)
        self.assertIn("- build: narrow, stooped from years of reaching upward", out)

    def test_stats_counts_described_people(self):
        undescribed = self.tmp / "j" / "jane-doe" / "jane-doe.md"
        _write_md(undescribed, "Jane Doe", bio="Brief.")
        stats = person.collection_stats(self.tmp)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["described"], 1)


class TestNoLabelNamesInFolkCode(unittest.TestCase):
    """Decision 2's hard constraint: the label set is open, so no label name
    may appear anywhere in folk's own source. The moment one does, adding
    `gait` is a code change and folk has appointed itself the owner of a
    taxonomy of bodies. docs/design/appearance-checkpoints.md Decision 3
    makes the same claim about checkpoint names, and reuses this same test
    per its own text rather than adding a second test with a second idea of
    the rule -- `forbidden` below carries both label and checkpoint samples.
    """

    def test_folk_package_names_no_labels(self):
        folk_dir = Path(__file__).resolve().parent.parent / "folk"
        # Sampled from the conventional set documented in the skill/spec;
        # these are the ones a well-meaning refactor would most plausibly
        # hardcode -- appearance labels, then appearance-checkpoints.md's own
        # worked-example checkpoint names.
        forbidden = ("wardrobe", "hairstyle", "eye color", "distinguishing marks",
                     "age 7", "age 17", "chapter 1")
        offenders = []
        for src in sorted(folk_dir.rglob("*.py")):
            text = src.read_text(encoding="utf-8").lower()
            for label in forbidden:
                if label in text:
                    offenders.append(f"{src.name}: {label}")
        self.assertEqual(offenders, [], f"label/checkpoint names found in folk/: {offenders}")


if __name__ == "__main__":
    unittest.main()
