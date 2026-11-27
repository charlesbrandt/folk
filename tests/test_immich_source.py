"""Tests for folk/sources/immich.py and folk/immich_narrative.py
(docs/design/immich-source.md). Fabricated fixtures only: invented names,
fictional places, placeholder asset ids and a placeholder API key."""

import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import urllib.error
from pathlib import Path

from folk import bulk, immich_narrative, journal
from folk.sources import immich

REPO_ROOT = Path(__file__).resolve().parent.parent

FAKE_KEY = "fake-key-do-not-use-0123456789"
ASSET_A = "00000000-0000-4000-8000-00000000000a"
ASSET_B = "00000000-0000-4000-8000-00000000000b"
TS = "2026-11-01T10:00:00"


def _asset(asset_id, people=(), description=None, city=None, country=None, local=None):
    raw = {"id": asset_id, "people": [{"id": f"p-{n}", "name": n} for n in people]}
    exif = {}
    if description is not None:
        exif["description"] = description
    if city is not None:
        exif["city"] = city
    if country is not None:
        exif["country"] = country
    raw["exifInfo"] = exif
    if local is not None:
        raw["localDateTime"] = local
    return raw


def _slugs(events):
    return sorted((e["s"], e["p"], e["o"]) for e in events)


class TestParse(unittest.TestCase):

    def test_description_only_single_person_emits_described_in_and_place(self):
        raw = _asset(ASSET_A, people=["Test Person One"], description="a picnic by the lake",
                     city="Fictional Falls", local="2024-06-01T12:00:00.000Z")
        events = immich.parse(raw, TS)
        self.assertEqual(_slugs(events), [
            ("person:test-person-one", "described_in", f"photo:{ASSET_A}"),
            ("person:test-person-one", "pictured_at", "locus:fictional-falls"),
        ])
        described = [e for e in events if e["p"] == "described_in"][0]
        self.assertEqual(described["note"], "a picnic by the lake")
        self.assertEqual(described["when"], "2024-06-01")
        self.assertEqual(described["src"], f"immich:asset:{ASSET_A}")
        self.assertEqual(described["actor"], "import:immich:v1")
        self.assertEqual(described["kind"], "observation")
        self.assertNotIn("session", described)
        self.assertNotIn("evidence", described)

    def test_people_only_two_people_emits_one_pair_and_no_description_event(self):
        raw = _asset(ASSET_A, people=["Test Person Two", "Test Person One"], local="2024-06-01T12:00:00.000Z")
        events = immich.parse(raw, TS)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["p"], "pictured_with")
        self.assertEqual((events[0]["s"], events[0]["o"]), ("person:test-person-one", "person:test-person-two"))
        self.assertNotIn("note", events[0])

    def test_both_description_and_two_people_emits_pair_with_note_and_per_person_events(self):
        raw = _asset(ASSET_A, people=["Test Person One", "Test Person Two"], description="a shared walk",
                     city="Fictional Falls", local="2024-06-01T12:00:00.000Z")
        events = immich.parse(raw, TS)
        preds = [e["p"] for e in events]
        self.assertEqual(preds.count("pictured_with"), 1)
        self.assertEqual(preds.count("pictured_at"), 2)
        self.assertEqual(preds.count("described_in"), 2)
        pair = [e for e in events if e["p"] == "pictured_with"][0]
        self.assertEqual(pair["note"], "a shared walk")

    def test_single_unannotated_person_without_place_emits_nothing(self):
        raw = _asset(ASSET_A, people=["Test Person One"])
        self.assertEqual(immich.parse(raw, TS), [])

    def test_single_person_with_place_emits_only_pictured_at(self):
        raw = _asset(ASSET_A, people=["Test Person One"], city="Fictional Falls")
        self.assertEqual([e["p"] for e in immich.parse(raw, TS)], ["pictured_at"])

    def test_hidden_trashed_offline_assets_are_not_live(self):
        self.assertTrue(immich._is_live({"id": "x", "visibility": "timeline"}))
        self.assertTrue(immich._is_live({"id": "x", "visibility": "archive"}))
        for bad in ({"visibility": "hidden"}, {"visibility": "locked"},
                    {"isTrashed": True}, {"isOffline": True}):
            self.assertFalse(immich._is_live(dict(bad, id="x")))

    def test_no_named_people_emits_nothing_even_with_description(self):
        raw = _asset(ASSET_A, people=[], description="a view of the hills", city="Fictional Falls")
        self.assertEqual(immich.parse(raw, TS), [])

    def test_unnamed_clusters_are_ignored(self):
        raw = {"id": ASSET_A, "people": [{"id": "x", "name": ""}, {"id": "y"}, {"id": "z", "name": "   "},
                                         {"id": "w", "name": "Test Person One"}],
               "exifInfo": {"description": "a quiet afternoon"}}
        events = immich.parse(raw, TS)
        self.assertEqual({e["s"] for e in events}, {"person:test-person-one"})
        self.assertEqual(immich.person_names([raw]), {"person:test-person-one": "Test Person One"})

    def test_missing_date_omits_when_but_keeps_the_event(self):
        raw = _asset(ASSET_A, people=["Test Person One"], description="undated note")
        events = immich.parse(raw, TS)
        self.assertTrue(events)
        self.assertTrue(all("when" not in e for e in events))

    def test_place_falls_back_to_country_when_city_is_absent(self):
        raw = _asset(ASSET_A, people=["Test Person One"], description="x", country="Fictional Republic")
        places = [e["o"] for e in immich.parse(raw, TS) if e["p"] == "pictured_at"]
        self.assertEqual(places, ["locus:fictional-republic"])

    def test_missing_id_raises_keyerror(self):
        with self.assertRaises(KeyError):
            immich.parse({"people": [{"name": "Test Person One"}]}, TS)

    def test_names_with_punctuation_and_diacritics_lint_clean(self):
        raw = _asset(ASSET_A, people=["Zoë Ångström-Test, MD", "José Pérez O'Brien", "Test   Person  Four"],
                     description="three friends", city="Fictional Falls", local="2025-02-03T08:00:00.000Z")
        events = immich.parse(raw, TS)
        self.assertTrue(events)
        stamped = [dict(e, id=journal.compute_id(e["ts"], e["actor"], e["s"], e["p"], e["o"])) for e in events]
        errors, _proposals = journal.lint_events(stamped, vocab={"types": ["person", "locus", "photo"],
                                                                 "predicates": {"pictured_with": "x",
                                                                                "pictured_at": "x",
                                                                                "described_in": "x"}})
        self.assertEqual(errors, [])
        slugs = {e["s"] for e in events} | {e["o"] for e in events if e["o"].startswith("person:")}
        self.assertIn("person:zoe-angstrom-test-md", slugs)
        self.assertIn("person:jose-perez-o-brien", slugs)


class TestPersonNames(unittest.TestCase):

    def test_variants_are_reported_not_resolved(self):
        a = _asset(ASSET_A, people=["Test Person One"], description="x")
        b = _asset(ASSET_B, people=["Test  Person One!"], description="y")
        self.assertEqual(immich.name_variants([a, b]),
                         {"person:test-person-one": ["Test  Person One!", "Test Person One"]})


def _load_glue_script():
    spec = importlib.util.spec_from_file_location(
        "run_immich_import", REPO_ROOT / "scripts" / "run_immich_import.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRequest:
    """Stands in for the HTTP layer: returns scripted pages and records calls."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __call__(self, url, body, key):
        self.calls.append({"url": url, "body": dict(body), "key": key})
        return self.pages[body["page"]]


class TestFetch(unittest.TestCase):

    def test_pages_follow_next_page_until_null(self):
        pages = {
            1: {"assets": {"items": [_asset(ASSET_A, people=["Test Person One"], description="x")],
                           "nextPage": "2"}},
            2: {"assets": {"items": [_asset(ASSET_B, people=["Test Person Two"], description="y")],
                           "nextPage": None}},
        }
        req = FakeRequest(pages)
        items = immich.fetch({"base_url": "http://immich.test:2283/", "page_size": 1},
                             request_fn=req, api_key=FAKE_KEY)
        self.assertEqual([a["id"] for a in items], [ASSET_A, ASSET_B])
        self.assertEqual([c["body"]["page"] for c in req.calls], [1, 2])
        self.assertEqual(req.calls[0]["url"], "http://immich.test:2283/api/search/metadata")
        self.assertTrue(req.calls[0]["body"]["withPeople"])
        self.assertTrue(req.calls[0]["body"]["withExif"])
        self.assertEqual(req.calls[0]["body"]["size"], 1)
        self.assertNotIn("takenAfter", req.calls[0]["body"])

    def test_since_becomes_taken_after(self):
        req = FakeRequest({1: {"assets": {"items": [], "nextPage": None}}})
        immich.fetch({"base_url": "http://immich.test:2283", "since": "2024-01-01"}, request_fn=req, api_key=FAKE_KEY)
        self.assertEqual(req.calls[0]["body"]["takenAfter"], "2024-01-01T00:00:00.000Z")

    def test_bad_since_is_refused(self):
        with self.assertRaises(immich.ImmichError):
            immich.fetch({"base_url": "http://immich.test:2283", "since": "last tuesday"},
                         request_fn=FakeRequest({}), api_key=FAKE_KEY)

    def test_repeated_page_stops_with_an_error(self):
        pages = {1: {"assets": {"items": [], "nextPage": "1"}}}
        with self.assertRaises(immich.ImmichError):
            immich.fetch({"base_url": "http://immich.test:2283"}, request_fn=FakeRequest(pages), api_key=FAKE_KEY)

    def test_unexpected_shape_raises_without_echoing_anything(self):
        with self.assertRaises(immich.ImmichError) as cm:
            immich.fetch({"base_url": "http://immich.test:2283"},
                         request_fn=FakeRequest({1: {"nope": 1}}), api_key=FAKE_KEY)
        self.assertNotIn(FAKE_KEY, str(cm.exception))

    def test_http_error_message_never_contains_the_key(self):
        def opener(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

        with self.assertRaises(immich.ImmichError) as cm:
            immich.fetch({"base_url": "http://immich.test:2283"}, api_key=FAKE_KEY, opener=opener)
        self.assertIn("401", str(cm.exception))
        self.assertNotIn(FAKE_KEY, str(cm.exception))
        self.assertNotIn(FAKE_KEY, repr(cm.exception))

    def test_unreachable_error_never_contains_the_key(self):
        def opener(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        with self.assertRaises(immich.ImmichError) as cm:
            immich.fetch({"base_url": "http://immich.test:2283"}, api_key=FAKE_KEY, opener=opener)
        self.assertNotIn(FAKE_KEY, str(cm.exception))

    def test_key_travels_in_header_only(self):
        captured = {}

        def opener(req, timeout=None):
            captured["headers"] = dict(req.header_items())
            captured["body"] = req.data
            return io.BytesIO(json.dumps({"assets": {"items": [], "nextPage": None}}).encode("utf-8"))

        immich.fetch({"base_url": "http://immich.test:2283"}, api_key=FAKE_KEY, opener=opener)
        self.assertEqual(captured["headers"].get("X-api-key"), FAKE_KEY)
        self.assertNotIn(FAKE_KEY, captured["body"].decode("utf-8"))


class TestApiKeyLoading(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_reads_named_var_from_env_file(self):
        f = self.tmp / "client.env"
        f.write_text(f"# comment\nOTHER=1\nexport IMMICH_API_KEY=\"{FAKE_KEY}\"\n", encoding="utf-8")
        self.assertEqual(immich.load_api_key(str(f), "IMMICH_API_KEY"), FAKE_KEY)

    def test_missing_var_error_names_the_variable_not_a_value(self):
        f = self.tmp / "client.env"
        f.write_text("OTHER=1\n", encoding="utf-8")
        with self.assertRaises(immich.ImmichError) as cm:
            immich.load_api_key(str(f), "IMMICH_API_KEY")
        self.assertIn("IMMICH_API_KEY", str(cm.exception))

    def test_environment_fallback_and_missing(self):
        self.assertEqual(immich.load_api_key(None, "X_VAR", environ={"X_VAR": FAKE_KEY}), FAKE_KEY)
        with self.assertRaises(immich.ImmichError):
            immich.load_api_key(None, "X_VAR", environ={})


class TestIdempotencyAndIdentity(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "journal"

    def _run(self, raw_assets):
        built = []
        for raw in raw_assets:
            built.extend(immich.parse(raw, TS))
        fresh, dropped = immich.dedupe(built, immich.existing_keys(self.root))
        outcomes = bulk.import_batch(self.root, "immich", fresh)
        return outcomes, dropped

    def test_rerun_appends_nothing_new(self):
        raws = [_asset(ASSET_A, people=["Test Person One", "Test Person Two"], description="a walk",
                       city="Fictional Falls", local="2024-06-01T12:00:00.000Z")]
        first, dropped1 = self._run(raws)
        self.assertEqual(dropped1, 0)
        self.assertTrue(all(o["status"] == "appended" for o in first))
        second, dropped2 = self._run(raws)
        self.assertEqual(second, [])
        self.assertEqual(dropped2, len(first))

    def test_edited_description_appends_a_later_observation(self):
        before = [_asset(ASSET_A, people=["Test Person One"], description="first wording")]
        self._run(before)
        after = [_asset(ASSET_A, people=["Test Person One"], description="corrected wording")]
        outcomes, dropped = self._run(after)
        self.assertEqual(dropped, 0)
        self.assertEqual([o["status"] for o in outcomes], ["appended"])

    def test_within_batch_repeat_is_dropped(self):
        raw = _asset(ASSET_A, people=["Test Person One"], description="once")
        built = immich.parse(raw, TS) + immich.parse(raw, TS)
        fresh, dropped = immich.dedupe(built, set())
        self.assertEqual(len(fresh), 1)
        self.assertEqual(dropped, 1)

    def test_split_by_identity_holds_events_touching_a_flagged_person(self):
        events = immich.parse(_asset(ASSET_A, people=["Test Person One", "Test Person Two"],
                                     description="x"), TS)
        near = {"person:test-person-one": [{"slug": "test-person-uno", "name": "Test Person Uno"}]}
        kept, held = immich.split_by_identity(events, near)
        self.assertTrue(held)
        self.assertTrue(all("person:test-person-one" in (e["s"], e["o"]) for e in held))
        self.assertTrue(all("person:test-person-one" not in (e["s"], e["o"]) for e in kept))

    def test_near_match_record_is_jsonl_safe_and_key_free(self):
        script = _load_glue_script()
        events = immich.parse(_asset(ASSET_A, people=["Test Person One", "Test Person Two"], description="x"), TS)
        near = {"person:test-person-one": [{"slug": "test-person-uno", "name": "Test Person Uno"}]}
        kept, held = immich.split_by_identity(events, near)
        plan = {"near_by_slug": near, "held": held}
        recs = script.near_match_records(plan, TS)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["slug"], "person:test-person-one")
        self.assertEqual(recs[0]["events_held"], len(held))
        line = json.dumps(recs[0])
        self.assertNotIn(FAKE_KEY, line)
        json.loads(line)


class TestNarrative(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "journal"
        raws = [
            _asset(ASSET_A, people=["Test Person One", "Test Person Two"], description="a shared picnic",
                   city="Fictional Falls", local="2024-06-01T12:00:00.000Z"),
            _asset(ASSET_B, people=["Test Person One"], description="a rainy afternoon",
                   city="Fictional Falls", local="2023-09-14T09:30:00.000Z"),
            _asset("00000000-0000-4000-8000-00000000000c", people=["Test Person Two"],
                   description="undated snapshot"),
        ]
        built = []
        for raw in raws:
            built.extend(immich.parse(raw, TS))
        bulk.import_batch(self.root, "immich", built)
        self.roots = [{"path": self.root, "collection": "fixture"}]

    def test_render_is_byte_identical_across_runs(self):
        events = immich_narrative.load_events(self.roots)
        first = immich_narrative.render(events, names={"test-person-one": "Test Person One"})
        second = immich_narrative.render(events, names={"test-person-one": "Test Person One"})
        self.assertEqual(first, second)

    def test_written_output_is_byte_identical_across_runs(self):
        out = self.tmp / "out"
        events = immich_narrative.load_events(self.roots)
        immich_narrative.write(out, immich_narrative.render(events))
        snapshot = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*.md")}
        immich_narrative.write(out, immich_narrative.render(immich_narrative.load_events(self.roots)))
        again = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*.md")}
        self.assertEqual(snapshot, again)
        self.assertIn("people/test-person-one.md", snapshot)

    def test_timeline_is_chronological_with_undated_last(self):
        files = immich_narrative.render(immich_narrative.load_events(self.roots))
        one = files["people/test-person-one.md"]
        self.assertLess(one.index("2023-09-14"), one.index("2024-06-01"))
        self.assertIn("with test-person-two", one)
        self.assertIn("at fictional-falls", one)
        two = files["people/test-person-two.md"]
        self.assertLess(two.index("2024-06-01"), two.index("undated"))

    def test_summary_rolls_up_by_year_and_place(self):
        summary = immich_narrative.render(immich_narrative.load_events(self.roots))["summary.md"]
        self.assertIn("- 2024: 1 photo(s)", summary)
        self.assertIn("- 2023: 1 photo(s)", summary)
        self.assertIn("- undated: 1 photo(s)", summary)
        self.assertIn("- fictional-falls: 2 photo(s)", summary)

    def test_later_event_for_same_asset_wins(self):
        raw = _asset(ASSET_A, people=["Test Person One"], description="old wording", local="2024-06-01T12:00:00.000Z")
        bulk.import_batch(self.root, "immich", immich.parse(raw, "2026-11-02T10:00:00"))
        raw2 = _asset(ASSET_A, people=["Test Person One"], description="new wording", local="2024-06-01T12:00:00.000Z")
        bulk.import_batch(self.root, "immich", immich.parse(raw2, "2026-11-03T10:00:00"))
        text = immich_narrative.render(immich_narrative.load_events(self.roots))["people/test-person-one.md"]
        self.assertIn("new wording", text)


if __name__ == "__main__":
    unittest.main()
