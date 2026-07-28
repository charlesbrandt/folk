"""Tests for folk/agenda.py's upcoming() -- docs/design/web-ui.md Decision
4's "Home" dashboard reminders query: recurring `## Dates` rolled forward
against an injected `now`, deterministic and read-only.
"""

import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from folk import agenda


def _write_person(collection_dir, slug, name, dates_block):
    person_dir = collection_dir / slug[0] / slug
    person_dir.mkdir(parents=True)
    content = f"# {name}\n"
    if dates_block:
        content += f"\n## Dates\n{dates_block}\n"
    (person_dir / f"{slug}.md").write_text(content)


class TestUpcoming(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.collection_dir = self.tmp / "personal"
        self.collection_dir.mkdir()

    def test_soonest_first_within_window(self):
        _write_person(self.collection_dir, "amy", "Amy", "- birthday: 07-05")
        _write_person(self.collection_dir, "ben", "Ben", "- birthday: 07-20")
        now = datetime(2026, 7, 1)
        items = agenda.upcoming([self.collection_dir], within_days=30, now=now)
        self.assertEqual([it["person"] for it in items], ["Amy", "Ben"])
        self.assertEqual(items[0]["date"], "2026-07-05")
        self.assertEqual(items[0]["days_until"], 4)

    def test_excludes_events_outside_window(self):
        _write_person(self.collection_dir, "cara", "Cara", "- birthday: 12-25")
        now = datetime(2026, 7, 1)
        items = agenda.upcoming([self.collection_dir], within_days=30, now=now)
        self.assertEqual(items, [])

    def test_rolls_forward_across_year_boundary(self):
        _write_person(self.collection_dir, "dan", "Dan", "- birthday: 01-02")
        now = datetime(2026, 12, 30)
        items = agenda.upcoming([self.collection_dir], within_days=10, now=now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["date"], "2027-01-02")
        self.assertEqual(items[0]["days_until"], 3)

    def test_today_counts_as_zero_days_until(self):
        _write_person(self.collection_dir, "eve", "Eve", "- birthday: 07-01")
        now = datetime(2026, 7, 1)
        items = agenda.upcoming([self.collection_dir], within_days=30, now=now)
        self.assertEqual(items[0]["days_until"], 0)

    def test_year_field_does_not_affect_recurrence(self):
        _write_person(self.collection_dir, "fay", "Fay", "- anniversary: 2019-07-10")
        now = datetime(2026, 7, 1)
        items = agenda.upcoming([self.collection_dir], within_days=30, now=now)
        self.assertEqual(items[0]["date"], "2026-07-10")

    def test_stable_tiebreak_by_person_name_on_same_date(self):
        _write_person(self.collection_dir, "zed", "Zed", "- birthday: 07-10")
        _write_person(self.collection_dir, "abe", "Abe", "- birthday: 07-10")
        now = datetime(2026, 7, 1)
        items = agenda.upcoming([self.collection_dir], within_days=30, now=now)
        self.assertEqual([it["person"] for it in items], ["Abe", "Zed"])

    def test_person_with_no_dates_section_contributes_nothing(self):
        _write_person(self.collection_dir, "gus", "Gus", "")
        now = datetime(2026, 7, 1)
        items = agenda.upcoming([self.collection_dir], within_days=30, now=now)
        self.assertEqual(items, [])

    def test_multiple_collection_dirs(self):
        other_dir = self.tmp / "characters"
        other_dir.mkdir()
        _write_person(self.collection_dir, "amy", "Amy", "- birthday: 07-05")
        _write_person(other_dir, "toru", "Toru", "- birthday: 07-10")
        now = datetime(2026, 7, 1)
        items = agenda.upcoming([self.collection_dir, other_dir], within_days=30, now=now)
        self.assertEqual([it["person"] for it in items], ["Amy", "Toru"])

    def test_deterministic_repeat_calls(self):
        _write_person(self.collection_dir, "amy", "Amy", "- birthday: 07-05")
        _write_person(self.collection_dir, "ben", "Ben", "- birthday: 07-20\n- met on: 2020-03-01")
        now = datetime(2026, 7, 1)
        first = agenda.upcoming([self.collection_dir], within_days=30, now=now)
        second = agenda.upcoming([self.collection_dir], within_days=30, now=now)
        self.assertEqual(first, second)

    def test_empty_collections_return_empty_list(self):
        self.assertEqual(agenda.upcoming([], within_days=30, now=datetime(2026, 7, 1)), [])

    def test_feb29_anniversary_rolls_to_mar1_in_non_leap_year(self):
        _write_person(self.collection_dir, "hal", "Hal", "- born: 02-29")
        now = datetime(2027, 2, 20)  # 2027 is not a leap year
        items = agenda.upcoming([self.collection_dir], within_days=15, now=now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["date"], "2027-03-01")


if __name__ == "__main__":
    unittest.main()
