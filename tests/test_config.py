import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from folk import config


class TestLoadJournalRoots(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.personal_dir = self.tmp / "personal"
        (self.personal_dir / "journal").mkdir(parents=True)
        self.work_dir = self.tmp / "work"
        self.work_dir.mkdir()  # no journal/ subdir -- should not become a root

        self.explicit_root = self.tmp / "apu-staging"
        self.explicit_root.mkdir()

        self.journal_roots_file = self.tmp / "journal-roots"

        self.collections_patch = mock.patch.object(
            config, "load_collections",
            return_value={"personal": str(self.personal_dir), "work": str(self.work_dir)},
        )
        self.roots_file_patch = mock.patch.object(config, "JOURNAL_ROOTS_FILE", self.journal_roots_file)
        self.collections_patch.start()
        self.roots_file_patch.start()
        self.addCleanup(self.collections_patch.stop)
        self.addCleanup(self.roots_file_patch.stop)

    def test_automatic_root_from_collection_with_journal_subdir(self):
        roots = config.load_journal_roots()
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]["collection"], "personal")
        self.assertEqual(Path(roots[0]["path"]), self.personal_dir / "journal")

    def test_explicit_root_added_from_journal_roots_file(self):
        self.journal_roots_file.write_text(json.dumps([
            {"path": str(self.explicit_root), "collection": "other"},
        ]))
        roots = config.load_journal_roots()
        collections = {r["collection"] for r in roots}
        self.assertEqual(collections, {"personal", "other"})

    def test_no_journal_roots_file_is_fine(self):
        self.assertFalse(self.journal_roots_file.exists())
        roots = config.load_journal_roots()
        self.assertEqual(len(roots), 1)


if __name__ == "__main__":
    unittest.main()
