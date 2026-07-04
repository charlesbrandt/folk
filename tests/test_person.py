"""Tests for folk/person.py's `## Dates` parsing (docs/design/web-ui.md
Decision 4) -- the person-file convention folk/agenda.py's upcoming() rolls
forward against an injected `now`.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from folk import person


def _write_person(path, heading, body=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {heading}\n\n{body}")


class TestPersonFilesMissingDir(unittest.TestCase):
    """A collection directory that doesn't exist (a stale/misconfigured
    entry in ~/.config/folk/collections) should read as empty, not crash --
    the same tolerance graph.build_person_index already gives this case, so
    any caller that iterates every configured collection (agenda.upcoming
    included) doesn't hard-fail because one entry doesn't currently exist.
    """

    def test_missing_dir_yields_nothing(self):
        missing = Path(tempfile.mkdtemp()) / "does-not-exist"
        shutil.rmtree(missing, ignore_errors=True)
        self.assertEqual(list(person._person_files(missing)), [])

    def test_missing_dir_list_persons_empty(self):
        missing = Path(tempfile.mkdtemp()) / "does-not-exist"
        shutil.rmtree(missing, ignore_errors=True)
        self.assertEqual(person.list_persons(missing), [])


class TestParseDates(unittest.TestCase):

    def test_month_day_only(self):
        sections = {"dates": ["- birthday: 03-14"]}
        self.assertEqual(person._parse_dates(sections),
                          [{"label": "birthday", "month_day": "03-14", "year": None}])

    def test_year_month_day(self):
        sections = {"dates": ["- anniversary: 2019-06-02"]}
        self.assertEqual(person._parse_dates(sections),
                          [{"label": "anniversary", "month_day": "06-02", "year": 2019}])

    def test_multiple_lines_preserve_order(self):
        sections = {"dates": ["- birthday: 03-14", "- met on: 2021-11-05"]}
        result = person._parse_dates(sections)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["label"], "birthday")
        self.assertEqual(result[1]["label"], "met on")

    def test_malformed_line_is_skipped(self):
        sections = {"dates": ["- birthday: not-a-date", "- birthday: 03-14"]}
        result = person._parse_dates(sections)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["month_day"], "03-14")

    def test_missing_section_returns_empty_list(self):
        self.assertEqual(person._parse_dates({}), [])

    def test_blank_lines_ignored(self):
        sections = {"dates": ["", "- birthday: 03-14", ""]}
        self.assertEqual(len(person._parse_dates(sections)), 1)


class TestShowPersonDates(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_show_person_surfaces_dates(self):
        fpath = self.tmp / "sam.md"
        _write_person(fpath, "Sam", "## Dates\n- birthday: 03-14\n- anniversary: 2019-06-02\n")
        info = person.show_person(fpath)
        self.assertEqual(info["dates"], [
            {"label": "birthday", "month_day": "03-14", "year": None},
            {"label": "anniversary", "month_day": "06-02", "year": 2019},
        ])

    def test_show_person_no_dates_section(self):
        fpath = self.tmp / "sam.md"
        _write_person(fpath, "Sam")
        info = person.show_person(fpath)
        self.assertEqual(info["dates"], [])


if __name__ == "__main__":
    unittest.main()
