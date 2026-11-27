"""docs/design/collection-registry-integrity.md, Decision 2: a missing
collection directory is a hard error when the collection was explicitly
requested, and a stderr warning (not silence) when iterating all of them."""

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from folk import config, graph, person


class TestExplicitRequestHardErrors(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.missing = self.tmp / "not-here"

    def test_explicit_dir_missing_raises(self):
        with self.assertRaises(config.CollectionMissing) as cm:
            config.resolve_collection_dir(explicit_dir=str(self.missing))
        self.assertIn(str(self.missing), str(cm.exception))

    def test_registered_name_with_missing_dir_raises_naming_both(self):
        with mock.patch.object(config, "load_collections", return_value={"ghost": str(self.missing)}):
            with self.assertRaises(config.CollectionMissing) as cm:
                config.resolve_collection_dir(collection_name="ghost")
        self.assertIn("ghost", str(cm.exception))
        self.assertIn(str(self.missing), str(cm.exception))

    def test_unknown_name_is_a_different_error(self):
        with mock.patch.object(config, "load_collections", return_value={}):
            with self.assertRaises(ValueError) as cm:
                config.resolve_collection_dir(collection_name="nope")
        self.assertNotIsInstance(cm.exception, config.CollectionMissing)
        self.assertIn("unknown collection", str(cm.exception))

    def test_existing_empty_collection_still_resolves(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        path, _ = config.resolve_collection_dir(explicit_dir=str(empty))
        self.assertEqual(path, empty)
        self.assertEqual(list(person._person_files(path)), [])

    def test_cli_exits_nonzero_with_message(self):
        import subprocess, sys
        r = subprocess.run([sys.executable, "-m", "folk", "-d", str(self.missing), "list"],
                           capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not exist", r.stderr)
        self.assertEqual(r.stdout.strip(), "")


class TestIterateAllIsTolerantButLoud(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.missing = self.tmp / "absent"
        config._WARNED_MISSING.discard(str(self.missing))

    def test_person_files_skips_and_warns_on_stderr_once(self):
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            self.assertEqual(list(person._person_files(self.missing)), [])
            self.assertEqual(list(person._person_files(self.missing)), [])
        self.assertEqual(err.getvalue().count(str(self.missing)), 1)
        self.assertEqual(out.getvalue(), "")

    def test_graph_index_skips_missing_and_keeps_others(self):
        good = self.tmp / "good" / "s" / "sam"
        good.mkdir(parents=True)
        (good / "sam.md").write_text("# Sam\n")
        regs = {"gone": str(self.missing), "good": str(self.tmp / "good")}
        err = io.StringIO()
        with mock.patch.object(config, "load_collections", return_value=regs), \
                contextlib.redirect_stderr(err):
            idx = graph.build_person_index()
        self.assertEqual(idx, {"sam": "Sam"})
        self.assertIn(str(self.missing), err.getvalue())


if __name__ == "__main__":
    unittest.main()
