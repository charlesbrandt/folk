"""Tests for folk/journal.py against the journal-in-folk.md exit criteria.

Reuses the real prototype scenario fixtures at prototypes/journal-promotion/
as the regression corpus (per docs/HANDOFF.md) rather than re-authoring new
fixtures: the observation/promotion segments, the person-file fixture, and
the LLM first-pass output that contains the known-bad speaker-attribution
event (COMPARISON.md finding 1). Prototype events predate the id/v fields
(journal-schema.md's noted intentional divergence), so tests wrap them with
id/v the way journal.append_event would, rather than editing the prototype
files themselves.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from folk import journal

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = REPO_ROOT / "prototypes" / "journal-promotion"
SESSION = "conv:20260601_025800_7f3ac9e2"
DEFAULT_TS = "2026-06-01T03:20:00"


def _load_ndjson(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _wrap(event, ts=None, actor=None, session=SESSION):
    """Give a raw prototype-shaped event the fields folk-proper requires:
    v, id (computed), ts, actor, session -- as append_event would at write time.
    """
    e = dict(event)
    e.setdefault("ts", ts or DEFAULT_TS)
    e.setdefault("actor", actor or "agent:hermes-main")
    e.setdefault("session", session)
    e["v"] = 1
    e["id"] = journal.compute_id(e["ts"], e["actor"], e.get("s", ""), e.get("p", ""), e.get("o", ""))
    return e


def observation_events():
    return _load_ndjson(PROTO_DIR / "journal" / "2026-06-observations.ndjson")


def wrapped_observation_events():
    return [_wrap(e, actor=e.get("actor", "extract:v1")) for e in observation_events()]


def proto_vocab():
    return json.loads((PROTO_DIR / "vocab.json").read_text())


def promotion_events():
    """The hand-authored reference promotions, wrapped as real journal events."""
    return [_wrap(e) for e in _load_ndjson(PROTO_DIR / "journal" / "2026-06-promotions.ndjson")]


def llm_first_pass_events():
    """Raw LLM output -- contains the known-bad speaker-attribution event
    (index 4: person:mara 'believes' start-over-elsewhere, sourced from an
    assistant message quoting Mara's memoir, per COMPARISON.md finding 1).
    """
    return [_wrap(e) for e in _load_ndjson(PROTO_DIR / "llm" / "20260601_025800_7f3ac9e2.gemma4-31b.ndjson")]


def llm_second_pass_clean_events():
    """The COMPARISON.md-diagnosed fix applied: the mis-attributed event is
    downgraded from stated to interpreted (it's the agent's reading of the
    memoir material, not something Mara said in this conversation) --
    which is exactly the resolution COMPARISON.md's finding 1 describes.
    """
    events = llm_first_pass_events()
    events[4] = dict(events[4])
    events[4]["evidence"] = "interpreted"
    events[4]["id"] = journal.compute_id(
        events[4]["ts"], events[4]["actor"], events[4]["s"], events[4]["p"], events[4]["o"])
    return events


class JournalScenarioTestCase(unittest.TestCase):
    """Sets up a temp collection (folk person-file layout) + a temp journal
    root containing the ported prototype events, mirroring the prototype's
    three-record scenario inside folk's real storage shape.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.collection_dir = self.tmp / "personal"
        person_dir = self.collection_dir / "m" / "mara"
        person_dir.mkdir(parents=True)
        (person_dir / "mara.md").write_text((PROTO_DIR / "fixtures" / "mara.md").read_text())

        self.journal_root = self.collection_dir / "journal"
        self.journal_root.mkdir()

        events = observation_events() + [_wrap(e) for e in _load_ndjson(PROTO_DIR / "journal" / "2026-06-promotions.ndjson")]
        # observation events predate id/v too
        events = [_wrap(e) if "id" not in e else e for e in events]
        segment = self.journal_root / "2026-05.testwriter.ndjson"
        with open(segment, "w") as f:
            for e in events:
                f.write(json.dumps(e, sort_keys=True) + "\n")

        self.collections = {"personal": str(self.collection_dir)}
        self.roots = [{"path": self.journal_root, "collection": "personal"}]
        self.index_path = self.tmp / "triples.ndjson"

    def rebuild(self):
        return journal.rebuild_index(collections=self.collections, roots=self.roots, index_path=self.index_path)


class TestReplayAndRebuild(JournalScenarioTestCase):

    def test_rebuild_twice_is_byte_identical(self):
        self.rebuild()
        first = self.index_path.read_bytes()
        self.rebuild()
        second = self.index_path.read_bytes()
        self.assertEqual(first, second)

    def test_delete_index_and_rebuild_survives_agent_written_memories(self):
        self.rebuild()
        before = self.index_path.read_bytes()
        self.index_path.unlink()
        self.assertFalse(self.index_path.exists())

        self.rebuild()
        after = self.index_path.read_bytes()
        self.assertEqual(before, after)

        records = journal.load_index(self.index_path)
        stated = [r for r in records if r.get("tier") == "stated" and r["p"] == "prioritizes"]
        self.assertTrue(any(r["o"] == "project:garden-tracker" for r in stated),
                         "agent-written stated fact should survive index deletion + rebuild")

    def test_human_tier_from_person_file(self):
        self.rebuild()
        records = journal.load_index(self.index_path)
        human = [r for r in records if r.get("tier") == "human" and r["s"] == "person:mara"]
        self.assertTrue(any(r["p"] == "tagged" and r["o"] == "tag:writer" for r in human))
        self.assertTrue(any(r["p"] == "agent" and r["o"] == "person:hermes" for r in human))

    def test_observed_tier_excludes_uttered(self):
        self.rebuild()
        records = journal.load_index(self.index_path)
        observed = [r for r in records if r.get("tier") == "observed"]
        self.assertTrue(all(r["p"] != "uttered" for r in observed),
                         "uttered observations are journal-only and must never be indexed")
        self.assertTrue(any(r["p"] == "participated_in" for r in observed))

    def test_bedrock_promotions_surface_as_suggestions_not_facts(self):
        self.rebuild()
        records = journal.load_index(self.index_path)
        candidates = [r for r in records if r.get("tier") == "candidate"]
        self.assertTrue(any(r["p"] == "defining_moment" and "radio" in r["o"] for r in candidates))
        # never indexed as a fact under any other tier
        self.assertFalse(any(r["p"] == "defining_moment" and r.get("tier") != "candidate" for r in records))

    def test_last_reinforced_derived_from_journal_ts(self):
        self.rebuild()
        records = journal.load_index(self.index_path)
        stated = [r for r in records if r["p"] == "prioritizes" and r["o"] == "project:garden-tracker"]
        self.assertEqual(len(stated), 1)
        self.assertEqual(stated[0].get("last_reinforced"), DEFAULT_TS)


class TestShowTieredProfile(JournalScenarioTestCase):

    def test_person_profile_groups_by_tier(self):
        self.rebuild()
        grouped = journal.person_profile("person:mara", index_path=self.index_path)
        self.assertTrue(grouped["human"])
        self.assertTrue(grouped["observed"])
        self.assertTrue(grouped["stated"])
        self.assertTrue(grouped["candidate"])
        stated_note = grouped["stated"][0]
        self.assertIn("src", stated_note)
        self.assertTrue(stated_note["src"].startswith("msg:"))


class TestAliasResolution(JournalScenarioTestCase):

    def test_alias_merges_triples_without_touching_journal(self):
        self.rebuild()
        before_journal = (self.journal_root / "2026-05.testwriter.ndjson").read_bytes()

        vocab_path = self.tmp / "vocab.json"
        vocab_path.write_text(json.dumps({
            "types": [], "predicates": {},
            "aliases": {"work:parish-archive": "work:parish-records-md"},
        }))

        import unittest.mock
        with unittest.mock.patch.object(journal.config, "VOCAB_FILE", vocab_path):
            self.rebuild()

        after_journal = (self.journal_root / "2026-05.testwriter.ndjson").read_bytes()
        self.assertEqual(before_journal, after_journal, "alias resolution must not rewrite the journal")

        records = journal.load_index(self.index_path)
        merged = [r for r in records if r["o"] == "work:parish-records-md" and r["p"] == "worked_through"]
        self.assertTrue(merged)
        self.assertFalse(any(r["o"] == "work:parish-archive" for r in records))


class TestLint(unittest.TestCase):

    def setUp(self):
        self.observations = wrapped_observation_events()

    def _full_transcript_texts(self):
        """Authoritative full-text override for msg #32, whose observation
        note is truncated to 200 chars (extract_observations.py's snippet
        limit) mid-word -- exactly why the real pipeline lints against the
        raw transcript, not the drill-down snippet (see journal.py module
        docstring / COMPARISON.md).
        """
        texts = journal._self_contained_transcript_texts(self.observations)
        full_32 = ("Makes sense to me. I just worked through those materials back in December 2025, "
                   "so they are a recent development for me too... Trying to make sense of what led me "
                   "where I am at now. I'm still interested in collecting local history stories.")
        speaker_32 = texts[32][0]
        texts = dict(texts)
        texts[32] = (speaker_32, journal._words(full_32))
        return texts

    def test_known_bad_event_fails_speaker_attribution(self):
        events = self.observations + llm_first_pass_events()
        errors, _proposals = journal.lint_events(
            events, transcript_texts=self._full_transcript_texts(), vocab=proto_vocab())
        self.assertTrue(
            any("didn't say this here" in e for e in errors),
            f"expected a speaker-attribution error, got: {errors}",
        )

    def test_clean_second_pass_output_lints_clean(self):
        events = self.observations + llm_second_pass_clean_events()
        errors, proposals = journal.lint_events(
            events, transcript_texts=self._full_transcript_texts(), vocab=proto_vocab())
        self.assertEqual(errors, [])
        self.assertEqual(proposals, [])

    def test_duplicate_triple_is_a_hard_error(self):
        e = _wrap({"kind": "promotion", "evidence": "interpreted", "level": "core",
                    "s": "person:mara", "p": "interested_in", "o": "topic:x",
                    "note": "dup", "src": "msg:foo#0"})
        errors, _ = journal.lint_events([e, dict(e)])
        self.assertTrue(any("duplicate" in err for err in errors))

    def test_id_mismatch_is_a_hard_error(self):
        e = _wrap({"kind": "promotion", "evidence": "interpreted", "level": "core",
                    "s": "person:mara", "p": "interested_in", "o": "topic:x",
                    "note": "n", "src": "msg:foo#0"})
        e["id"] = "0" * 12
        errors, _ = journal.lint_events([e])
        self.assertTrue(any("id mismatch" in err for err in errors))

    def test_unknown_predicate_is_a_soft_proposal_not_an_error(self):
        e = _wrap({"kind": "promotion", "evidence": "interpreted", "level": "core",
                    "s": "person:mara", "p": "brand_new_predicate", "o": "topic:x",
                    "note": "n", "src": "msg:foo#0", "p_def": "a coined predicate"})
        errors, proposals = journal.lint_events([e], vocab={"types": ["person", "topic"], "predicates": {}, "aliases": {}})
        self.assertEqual(errors, [])
        self.assertTrue(any("brand_new_predicate" in p for p in proposals))


class TestRedactionAndReview(unittest.TestCase):

    def test_redaction_expunges_event_entirely(self):
        promo = _wrap({"kind": "promotion", "evidence": "stated", "level": "core",
                        "s": "person:mara", "p": "interested_in", "o": "topic:secret",
                        "note": "shh", "src": "msg:foo#0"}, actor="human")
        redaction = _wrap({"kind": "redaction", "s": "", "p": "", "o": "", "ref": promo["id"]}, actor="human")

        tmp = Path(tempfile.mkdtemp())
        try:
            root = tmp / "journal"
            root.mkdir()
            with open(root / "2026-05.w.ndjson", "w") as f:
                f.write(json.dumps(promo, sort_keys=True) + "\n")
                f.write(json.dumps(redaction, sort_keys=True) + "\n")
            triples, suggestions = journal.replay(collections={}, roots=[{"path": root, "collection": "personal"}])
            self.assertFalse(any(t["o"] == "topic:secret" for t in triples))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rejected_promotion_dropped_from_index(self):
        promo = _wrap({"kind": "promotion", "evidence": "stated", "level": "core",
                        "s": "person:mara", "p": "interested_in", "o": "topic:wrong",
                        "note": "shh", "src": "msg:foo#0"})
        review = _wrap({"kind": "review", "s": "", "p": "", "o": "", "ref": promo["id"], "verdict": "reject"},
                        actor="human", ts="2026-05-15T00:00:00")

        tmp = Path(tempfile.mkdtemp())
        try:
            root = tmp / "journal"
            root.mkdir()
            with open(root / "2026-05.w.ndjson", "w") as f:
                f.write(json.dumps(promo, sort_keys=True) + "\n")
                f.write(json.dumps(review, sort_keys=True) + "\n")
            triples, _suggestions = journal.replay(collections={}, roots=[{"path": root, "collection": "personal"}])
            self.assertFalse(any(t["o"] == "topic:wrong" for t in triples))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_accepted_bedrock_stops_surfacing_as_suggestion(self):
        bedrock = _wrap({"kind": "promotion", "evidence": "interpreted", "level": "bedrock",
                          "s": "person:mara", "p": "values", "o": "value:x",
                          "note": "n", "src": "msg:foo#0"})
        review = _wrap({"kind": "review", "s": "", "p": "", "o": "", "ref": bedrock["id"], "verdict": "accept"},
                        actor="human", ts="2026-05-15T00:00:00")

        tmp = Path(tempfile.mkdtemp())
        try:
            root = tmp / "journal"
            root.mkdir()
            with open(root / "2026-05.w.ndjson", "w") as f:
                f.write(json.dumps(bedrock, sort_keys=True) + "\n")
                f.write(json.dumps(review, sort_keys=True) + "\n")
            _triples, suggestions = journal.replay(collections={}, roots=[{"path": root, "collection": "personal"}])
            self.assertFalse(any(s["o"] == "value:x" for s in suggestions),
                              "an accepted bedrock suggestion should stop resurfacing in the queue")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBuildTranscriptTexts(unittest.TestCase):

    def test_parses_roles_and_strips_think_tags(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            path = tmp / "transcript.jsonl"
            with open(path, "w") as f:
                f.write(json.dumps({"role": "user", "content": "hello there friend"}) + "\n")
                f.write(json.dumps({"role": "assistant", "content": "<think>scheming</think>hi back"}) + "\n")
                f.write(json.dumps({"role": "session_meta", "content": "ignored"}) + "\n")
            texts = journal.build_transcript_texts(path, "person:x", "agent:y")
            self.assertEqual(texts[0], ("person:x", ["hello", "there", "friend"]))
            self.assertEqual(texts[1], ("agent:y", ["hi", "back"]))
            self.assertNotIn(2, texts)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
