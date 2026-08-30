"""Tests for folk/sources/directory_scrape.py's parse() against
docs/design/bulk-import.md's worked example -- fabricated fixture records
only, no real names or organizations.
"""

import unittest

from folk.sources import directory_scrape as ds


class TestParse(unittest.TestCase):

    def test_full_record_produces_title_and_department_events(self):
        raw = {"name": "Priya Anand", "title": "Research Scientist",
               "department": "Neurology", "profile_url": "https://example.org/directory/p-anand"}
        events = ds.parse(raw, ts="2026-08-30T03:00:00")

        self.assertEqual(len(events), 2)
        title_ev, dept_ev = events

        self.assertEqual(title_ev["kind"], "observation")
        self.assertEqual(title_ev["actor"], "import:directory-scrape:v1")
        self.assertEqual(title_ev["s"], "person:priya-anand")
        self.assertEqual(title_ev["p"], "holds_title")
        self.assertEqual(title_ev["o"], "title:research-scientist")
        self.assertEqual(title_ev["note"], "Research Scientist")
        self.assertEqual(title_ev["src"], "directory-scrape:profile:https://example.org/directory/p-anand#title")
        self.assertNotIn("session", title_ev)
        self.assertNotIn("evidence", title_ev)

        self.assertEqual(dept_ev["s"], "person:priya-anand")
        self.assertEqual(dept_ev["p"], "works_at")
        self.assertEqual(dept_ev["o"], "locus:neurology")
        self.assertEqual(dept_ev["src"], "directory-scrape:profile:https://example.org/directory/p-anand#department")

    def test_missing_title_omits_the_title_event_rather_than_emitting_a_bad_one(self):
        raw = {"name": "R. Okafor", "title": "", "department": "Neurology",
               "profile_url": "https://example.org/directory/r-okafor"}
        events = ds.parse(raw, ts="2026-08-30T03:00:00")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["p"], "works_at")

    def test_missing_name_raises(self):
        with self.assertRaises(KeyError):
            ds.parse({"title": "Lab Manager", "department": "Neurology"}, ts="2026-08-30T03:00:00")

    def test_missing_profile_url_falls_back_to_slugified_name(self):
        raw = {"name": "Marcus Webb", "department": "Neurology"}
        events = ds.parse(raw, ts="2026-08-30T03:00:00")
        self.assertEqual(events[0]["src"], "directory-scrape:profile:marcus-webb#department")

    def test_fetch_is_a_documented_stub(self):
        with self.assertRaises(NotImplementedError):
            ds.fetch({})


if __name__ == "__main__":
    unittest.main()
