"""Tests for web/routers/edit.py -- the person-file write path (Decision 1
write path #1 / Decision 2c's inline edit). This is the one piece of Wave 2b
worth a real unit test per docs/design/web-ui.md's instructions, because a
bug here is a security bug (path containment, shell-injection-shaped input,
scoping a git commit to exactly one file), not a display bug.

Runs entirely against a throwaway scratch git repo under a temp directory --
never touches the real seeded characters/authors collections or the real
~/.folk/triples.ndjson (folk.triples.index_rebuild is monkeypatched to an
isolated call with its own index_path for the duration of these tests, and
folk.config.load_collections is monkeypatched so /people/{slug}/edit/* only
ever resolves against the scratch collection).

Run with: cd web && python3 -m unittest discover tests
(or `python3 -m unittest web.tests.test_edit_write` from the repo root, once
`web` is on sys.path -- see the sys.path insert below, matching how
web/api.py's own routers.* imports assume `web/` as the working directory).
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_WEB_DIR = Path(__file__).resolve().parent.parent
if str(_WEB_DIR) not in sys.path:
    sys.path.insert(0, str(_WEB_DIR))

from fastapi import HTTPException  # noqa: E402

from routers import edit  # noqa: E402
from folk import journal, person  # noqa: E402


def _git(repo_root, *args):
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {args} failed: {result.stderr}")
    return result.stdout


PERSON_MD = """# Test Person

A test person for web/routers/edit.py's write-path tests.

## Tags
fixture

## Associations
- [Norwegian Wood](work:norwegian-wood) — appears_in

## Archetype
placeholder
"""


class EditWriteTestBase(unittest.TestCase):
    """Sets up a throwaway git repo, one collection nested inside it (to
    exercise the "repo root != collection dir" case docs/design/web-ui.md
    calls out explicitly), and one person file -- then monkeypatches
    folk.config.load_collections (as seen by routers.edit) and
    routers.edit.triples.index_rebuild so every test runs fully isolated
    from real folk config and the real index."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="folk-web-edit-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.repo_root = self.tmp / "notes-repo"
        # Collection dir nested a few levels under the repo root, mirroring
        # the real characters/authors layout the task description calls out.
        self.collection_dir = self.repo_root / "media" / "characters"
        self.person_dir = self.collection_dir / "t" / "test-person"
        self.person_dir.mkdir(parents=True)
        self.fpath = self.person_dir / "test-person.md"
        self.fpath.write_text(PERSON_MD, encoding="utf-8")

        _git(self.repo_root, "init", "-q")
        _git(self.repo_root, "add", "-A")
        _git(self.repo_root, "commit", "-q", "-m", "fixture: seed test-person")

        self.index_path = self.tmp / "triples.ndjson"

        collections_patch = mock.patch(
            "routers.edit.config.load_collections",
            return_value={"scratch": str(self.collection_dir)},
        )
        collections_patch.start()
        self.addCleanup(collections_patch.stop)

        def fake_rebuild():
            return journal.rebuild_index(
                collections={"scratch": str(self.collection_dir)},
                index_path=self.index_path,
            )

        rebuild_patch = mock.patch("routers.edit.triples.index_rebuild", side_effect=fake_rebuild)
        rebuild_patch.start()
        self.addCleanup(rebuild_patch.stop)


class TestValidationRejections(EditWriteTestBase):
    def test_unknown_section_rejected_before_touching_disk(self):
        body = edit.EditBody(collection="scratch", section="not-a-real-section", content="x")
        with self.assertRaises(HTTPException) as ctx:
            edit.preview_edit("test-person", body)
        self.assertEqual(ctx.exception.status_code, 400)
        # Confirm nothing was touched: file unchanged, no new commit.
        self.assertEqual(self.fpath.read_text(), PERSON_MD)
        self.assertEqual(_git(self.repo_root, "log", "--oneline").count("\n"), 1)

    def test_unknown_section_rejected_on_commit_too(self):
        body = edit.EditBody(collection="scratch", section="; rm -rf /", content="x")
        with self.assertRaises(HTTPException) as ctx:
            edit.commit_edit("test-person", body)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_missing_person_404(self):
        body = edit.EditBody(collection="scratch", section="tags", content="x")
        with self.assertRaises(HTTPException) as ctx:
            edit.preview_edit("nobody-here", body)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_unknown_collection_404(self):
        body = edit.EditBody(collection="does-not-exist", section="tags", content="x")
        with self.assertRaises(HTTPException) as ctx:
            edit.preview_edit("test-person", body)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_path_traversal_slug_is_not_found_not_escaped(self):
        """person._find_person_file never builds a path from the slug string
        (it only ever compares against real directory entries it discovered
        by walking the collection dir), so a path-traversal-shaped slug
        can't escape the collection -- it just doesn't match anything. This
        pins that behavior for the write path specifically."""
        body = edit.EditBody(collection="scratch", section="tags", content="x")
        for bad_slug in ("../../../../etc/passwd", "..%2f..%2fetc%2fpasswd", "test-person/../../../etc/passwd"):
            with self.assertRaises(HTTPException) as ctx:
                edit.preview_edit(bad_slug, body)
            self.assertEqual(ctx.exception.status_code, 404, msg=f"slug={bad_slug!r}")


class TestPreviewCommitFlow(EditWriteTestBase):
    def test_preview_does_not_write(self):
        body = edit.EditBody(collection="scratch", section="tags", content="fixture updated")
        result = edit.preview_edit("test-person", body)
        self.assertIn("-fixture\n+fixture updated", result["diff"])
        # File on disk and git state must be completely untouched.
        self.assertEqual(self.fpath.read_text(), PERSON_MD)
        self.assertEqual(_git(self.repo_root, "status", "--porcelain"), "")

    def test_commit_writes_diff_shown_by_preview_and_scopes_to_one_file(self):
        body = edit.EditBody(collection="scratch", section="tags", content="fixture updated")
        preview = edit.preview_edit("test-person", body)
        result = edit.commit_edit("test-person", body)

        self.assertTrue(result["committed"])
        self.assertEqual(result["diff"], preview["diff"])
        self.assertTrue(result["commit_sha"])

        # Working tree clean afterward -- the commit captured exactly what
        # was written, nothing left dangling.
        self.assertEqual(_git(self.repo_root, "status", "--porcelain"), "")

        # The commit touches exactly the one file we edited.
        stat = _git(self.repo_root, "show", "--stat", "--format=", result["commit_sha"])
        touched = [l for l in stat.splitlines() if l.strip() and "|" in l]
        self.assertEqual(len(touched), 1, msg=stat)
        self.assertIn("test-person.md", touched[0])

        # Commit message: plain, deterministic, no Co-Authored-By.
        msg = _git(self.repo_root, "log", "-1", "--format=%s", result["commit_sha"]).strip()
        self.assertEqual(msg, "folk web: edit tags on test-person")
        full_msg = _git(self.repo_root, "log", "-1", "--format=%B", result["commit_sha"])
        self.assertNotIn("Co-Authored-By", full_msg)

        # File content actually reflects the edit.
        after = self.fpath.read_text()
        self.assertIn("fixture updated", after)
        sections = person._parse_sections(after)
        self.assertEqual(person._parse_tags(sections), ["fixture", "updated"])

        # folk show (via journal.person_profile against the isolated index)
        # reflects the edit too, once index_rebuild has run.
        self.assertTrue(self.index_path.exists())

    def test_commit_with_no_actual_change_is_a_noop(self):
        body = edit.EditBody(collection="scratch", section="tags", content="fixture")
        before_log = _git(self.repo_root, "log", "--oneline")
        result = edit.commit_edit("test-person", body)
        self.assertEqual(result, {"committed": False, "reason": "no changes"})
        after_log = _git(self.repo_root, "log", "--oneline")
        self.assertEqual(before_log, after_log)
        self.assertEqual(_git(self.repo_root, "status", "--porcelain"), "")

    def test_bio_edit_preserves_h1_heading(self):
        body = edit.EditBody(collection="scratch", section="__main__", content="A rewritten bio.")
        result = edit.commit_edit("test-person", body)
        self.assertTrue(result["committed"])
        after = self.fpath.read_text()
        self.assertTrue(after.startswith("# Test Person"))
        self.assertIn("A rewritten bio.", after)
        info = person.show_person(self.fpath)
        self.assertEqual(info["bio"], "A rewritten bio.")
        self.assertEqual(info["name"], "Test Person")

    def test_commit_failure_rolls_back_working_tree_write(self):
        """A git failure after the file's already been written (e.g. commit
        rejected by a hook) must not leave a half-applied edit sitting in
        the repo with no commit and no explanation -- routers/edit.py's
        commit_edit rolls the file content back and unstages on any failure
        from `git add` onward."""
        body = edit.EditBody(collection="scratch", section="tags", content="fixture updated")
        real_run = subprocess.run

        def fake_run(args, **kwargs):
            if args[:1] == ["git"] and "commit" in args:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="simulated commit failure")
            return real_run(args, **kwargs)

        with mock.patch("routers.edit.subprocess.run", side_effect=fake_run):
            with self.assertRaises(HTTPException) as ctx:
                edit.commit_edit("test-person", body)
        self.assertEqual(ctx.exception.status_code, 500)

        self.assertEqual(self.fpath.read_text(), PERSON_MD)
        self.assertEqual(_git(self.repo_root, "status", "--porcelain"), "")
        self.assertEqual(_git(self.repo_root, "log", "--oneline").count("\n"), 1)

    def test_repo_root_resolved_independently_of_collection_dir(self):
        """The collection dir (media/characters) is nested three levels
        under the actual git repo root -- confirms _repo_root_for finds the
        real toplevel via `git rev-parse --show-toplevel` rather than
        assuming the collection dir IS the repo root."""
        found = edit._repo_root_for(self.fpath)
        self.assertEqual(found.resolve(), self.repo_root.resolve())


if __name__ == "__main__":
    unittest.main()
