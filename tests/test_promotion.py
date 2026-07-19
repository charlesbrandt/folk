"""Tests for folk/promotion.py against session-promotion-job.md's exit criteria.

Uses a synthetic Hermes session file (the real prototype's raw transcript
isn't checked into the repo -- only its derived journal/llm outputs are,
per docs/HANDOFF.md) built the shape extract_observations.py expects: one
{role, content, timestamp} object per line. msg indices are the file's own
raw line numbers -- folk/sources/hermes.py and journal.build_transcript_texts
already agree on this numbering (see test_journal.py's TestBuildTranscriptTexts).
"""

import json
import shutil
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from folk import journal
from folk import promotion
from folk import review
from folk import sources
from folk.sources import hermes as hermes_source

SESSION_LINES = [
    {"role": "session_meta", "timestamp": "2026-07-01T00:00:00", "platform": "telegram"},
    {"role": "user", "timestamp": "2026-07-01T00:00:01", "content": "I love hiking in the mountains."},
    {"role": "assistant", "timestamp": "2026-07-01T00:00:02", "content": "<think>note</think>That's great to hear!"},
]


def _write_session_file(path, lines=SESSION_LINES):
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def _read_all_staging_events(staging_dir):
    events = []
    for f in sorted(Path(staging_dir).glob("*.ndjson")):
        events.extend(journal.read_segment(f))
    return events


class HermesAdapterTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.sessions_dir = self.tmp / "sessions"
        self.sessions_dir.mkdir()
        _write_session_file(self.sessions_dir / "testsession.jsonl")

        self.source_cfg = {
            "profiles": {
                "test-profile": {
                    "sessions_dir": str(self.sessions_dir),
                    "user_slug": "person:test",
                    "agent_slug": "agent:test-main",
                    "collection": "personal",
                }
            }
        }

    def test_discover_finds_session_file(self):
        refs = hermes_source.discover(self.source_cfg)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["session_id"], "testsession")
        self.assertEqual(refs[0]["profile"], "test-profile")

    def test_load_normalizes_messages_with_raw_line_index(self):
        ref = hermes_source.discover(self.source_cfg)[0]
        session_id = sources.session_id_for("hermes", ref)
        conv = f"conv:{session_id}"
        session = hermes_source.load(ref, self.source_cfg, session_id, conv)

        self.assertEqual(session["session_id"], "hermes-testsession")
        self.assertEqual(session["platform"], "telegram")
        self.assertEqual(session["collection"], "personal")
        self.assertEqual(len(session["messages"]), 2)
        # session_meta consumes raw line 0; later messages keep their own
        # raw line index rather than being renumbered/compacted.
        self.assertEqual(session["messages"][0]["index"], 1)
        self.assertEqual(session["messages"][0]["speaker"], "person:test")
        self.assertEqual(session["messages"][0]["text"], "I love hiking in the mountains.")
        self.assertEqual(session["messages"][1]["index"], 2)
        self.assertEqual(session["messages"][1]["speaker"], "agent:test-main")
        self.assertEqual(session["messages"][1]["text"], "That's great to hear!")  # <think> stripped


class ExtractTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        sessions_dir = self.tmp / "sessions"
        sessions_dir.mkdir()
        _write_session_file(sessions_dir / "testsession.jsonl")
        source_cfg = {"profiles": {"p": {
            "sessions_dir": str(sessions_dir),
            "user_slug": "person:test", "agent_slug": "agent:test-main",
            "collection": "personal",
        }}}
        ref = hermes_source.discover(source_cfg)[0]
        self.session_id = sources.session_id_for("hermes", ref)
        self.session = hermes_source.load(ref, source_cfg, self.session_id, f"conv:{self.session_id}")

    def test_extract_produces_session_and_observation_events(self):
        events = promotion.extract(self.session)
        kinds = [e["kind"] for e in events]
        self.assertEqual(kinds[0], "session")
        self.assertEqual(kinds.count("observation"), 4)  # 2 participated_in + 2 uttered

        session_event = events[0]
        self.assertEqual(session_event["o"], "platform:telegram")
        self.assertEqual(session_event["actor"], "extract:v1")

        uttered = [e for e in events if e.get("p") == "uttered"]
        self.assertEqual(uttered[0]["o"], f"msg:{self.session_id}#1")
        self.assertEqual(uttered[0]["s"], "person:test")
        self.assertEqual(uttered[1]["o"], f"msg:{self.session_id}#2")
        self.assertEqual(uttered[1]["s"], "agent:test-main")


class ProcessSessionTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        sessions_dir = self.tmp / "sessions"
        sessions_dir.mkdir()
        _write_session_file(sessions_dir / "testsession.jsonl")
        self.source_cfg = {"profiles": {"p": {
            "sessions_dir": str(sessions_dir),
            "user_slug": "person:test", "agent_slug": "agent:test-main",
            "collection": "personal",
        }}}
        ref = hermes_source.discover(self.source_cfg)[0]
        self.session_id = sources.session_id_for("hermes", ref)
        self.session = hermes_source.load(ref, self.source_cfg, self.session_id, f"conv:{self.session_id}")

        self.vocab = {
            "types": ["person", "agent", "conv", "msg", "platform", "topic"],
            "predicates": {"participated_in": "x", "uttered": "x", "opened_on": "x",
                           "interested_in": "subject has an ongoing interest in a topic"},
            "aliases": {},
        }
        self.staging_root = self.tmp / "staging"
        self.quarantine_dir = self.tmp / "quarantine"
        self.index_path = self.tmp / "triples.ndjson"  # absent -> empty known-slug set

    def _clean_call(self, prompt, model, url):
        event = {"kind": "promotion", "evidence": "stated", "level": "core",
                 "s": "person:test", "p": "interested_in", "o": "topic:hiking",
                 "src": f"msg:{self.session_id}#1", "note": "I love hiking in the mountains."}
        return json.dumps(event)

    def test_clean_promotion_appends_to_staging_segment(self):
        outcome, counts, _wall, errors = promotion.process_session(
            self.session, self.vocab, self.index_path, self.staging_root, self.quarantine_dir,
            "test-model", "http://unused", promote_call=self._clean_call)

        self.assertEqual(outcome, "ok")
        self.assertEqual(errors, [])
        self.assertEqual(counts["promotion"], 1)

        events = _read_all_staging_events(self.staging_root)
        self.assertEqual(len(events), 6)  # 1 session + 2 participated_in + 2 uttered + 1 promotion
        promos = [e for e in events if e["kind"] == "promotion"]
        self.assertEqual(len(promos), 1)
        self.assertEqual(promos[0]["o"], "topic:hiking")
        self.assertTrue(promos[0]["id"])  # append_event computed id/v

    def test_lint_failure_quarantines_after_retry_and_appends_no_promotion(self):
        call_count = {"n": 0}

        def bad_call(prompt, model, url):
            call_count["n"] += 1
            # msg#2 is the assistant's line -- a stated fact about person:test
            # sourced there is a speaker-attribution violation (COMPARISON.md
            # finding 1's exact mechanism).
            event = {"kind": "promotion", "evidence": "stated", "level": "core",
                     "s": "person:test", "p": "interested_in", "o": "topic:x",
                     "src": f"msg:{self.session_id}#2", "note": "That's great to hear!"}
            return json.dumps(event)

        outcome, _counts, _wall, errors = promotion.process_session(
            self.session, self.vocab, self.index_path, self.staging_root, self.quarantine_dir,
            "test-model", "http://unused", promote_call=bad_call)

        self.assertEqual(outcome, "quarantined")
        self.assertEqual(call_count["n"], 2, "expected exactly one automatic retry before quarantining")
        self.assertTrue(any("didn't say this here" in e for e in errors))

        # extract step always runs, even though promotion failed
        events = _read_all_staging_events(self.staging_root)
        self.assertEqual(len(events), 5)
        self.assertTrue(all(e["kind"] != "promotion" for e in events))

        qpath = self.quarantine_dir / f"{self.session_id}.ndjson"
        errors_path = self.quarantine_dir / f"{self.session_id}.errors.txt"
        self.assertTrue(qpath.exists())
        self.assertTrue(errors_path.exists())

        items = review.pending_items(collections={}, roots=[], index_path=self.index_path,
                                      quarantine_dir=self.quarantine_dir, vocab=self.vocab)
        self.assertTrue(any(it["session"] == self.session_id for it in items["lint_failure"]))

    def test_network_error_defers_without_quarantine_or_appending_promotion(self):
        def failing_call(prompt, model, url):
            raise TimeoutError("ollama busy")

        outcome, _counts, _wall, _errors = promotion.process_session(
            self.session, self.vocab, self.index_path, self.staging_root, self.quarantine_dir,
            "test-model", "http://unused", promote_call=failing_call)

        self.assertEqual(outcome, "deferred")
        self.assertFalse((self.quarantine_dir / f"{self.session_id}.ndjson").exists())
        events = _read_all_staging_events(self.staging_root)
        self.assertEqual(len(events), 5)  # extract still ran


class RunOnceTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.sessions_dir = self.tmp / "sessions"
        self.sessions_dir.mkdir()
        for i in range(3):
            _write_session_file(self.sessions_dir / f"session{i}.jsonl")

        self.job_cfg = {
            "model": "test-model", "ollama_url": "http://unused",
            "cap_per_run": 10, "quiet_seconds": 0,
            "sources": {"hermes": {"profiles": {"p": {
                "sessions_dir": str(self.sessions_dir),
                "user_slug": "person:test", "agent_slug": "agent:test-main",
                "collection": "personal",
            }}}},
        }
        self.state_path = self.tmp / "promotion-state.json"
        self.staging_root = self.tmp / "staging"
        self.quarantine_dir = self.tmp / "quarantine"
        self.index_path = self.tmp / "triples.ndjson"
        self.log_path = self.tmp / "promotion.log"

    def _clean_call(self, prompt, model, url):
        # evidence: interpreted needs no verifiable src, so one fixed
        # response works for whichever of the 3 sessions is running.
        event = {"kind": "promotion", "evidence": "interpreted", "level": "core",
                 "s": "person:test", "p": "interested_in", "o": "topic:hiking", "note": "n"}
        return json.dumps(event)

    def _run(self, **overrides):
        kwargs = dict(job_cfg=self.job_cfg, state_path=self.state_path, index_path=self.index_path,
                      staging_root=self.staging_root, quarantine_dir=self.quarantine_dir,
                      log_path=self.log_path, promote_call=self._clean_call)
        kwargs.update(overrides)
        return promotion.run_once(**kwargs)

    def test_run_once_processes_all_then_second_run_processes_zero(self):
        results = self._run()
        self.assertEqual(len(results), 3)
        self.assertTrue(all(o == "ok" for _s, o in results))

        state = json.loads(self.state_path.read_text())
        self.assertEqual(len(state), 3)

        log_lines = self.log_path.read_text().splitlines()
        self.assertEqual(len(log_lines), 3)

        second = self._run()
        self.assertEqual(second, [], "running the job twice should process zero sessions the second time")

    def test_cap_limits_sessions_processed_per_run(self):
        results = self._run(cap=2)
        self.assertEqual(len(results), 2)

    def test_quiescence_skips_recently_written_sessions(self):
        job_cfg = dict(self.job_cfg, quiet_seconds=3600)
        results = self._run(job_cfg=job_cfg)
        self.assertEqual(results, [], "sessions younger than quiet_seconds should not be processed yet")


class LocusWiringTestCase(unittest.TestCase):
    """docs/design/loci.md Decision 2 ("declared by surface, not inferred")
    wired through the Hermes adapter + promotion pipeline: a Hermes profile
    bound to a locus (source_cfg's "locus" key, web-ui.md Decision 2's
    "mechanically stamped, never LLM-inferred") stamps that locus on every
    event the session produces -- session, observation, and promotion
    alike -- and the tag survives journal.append_event + rebuild_index:
    journal.locus_records() picks the events up on the other end.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        sessions_dir = self.tmp / "sessions"
        sessions_dir.mkdir()
        _write_session_file(sessions_dir / "testsession.jsonl")
        self.source_cfg = {"profiles": {"p": {
            "sessions_dir": str(sessions_dir),
            "user_slug": "person:test", "agent_slug": "agent:test-main",
            "collection": "personal", "locus": "locus:home",
        }}}
        ref = hermes_source.discover(self.source_cfg)[0]
        self.session_id = sources.session_id_for("hermes", ref)
        self.session = hermes_source.load(ref, self.source_cfg, self.session_id, f"conv:{self.session_id}")

        self.vocab = {
            "types": ["person", "agent", "conv", "msg", "platform", "topic", "locus"],
            "predicates": {"participated_in": "x", "uttered": "x", "opened_on": "x",
                           "interested_in": "subject has an ongoing interest in a topic"},
            "aliases": {},
        }
        self.staging_root = self.tmp / "staging"
        self.quarantine_dir = self.tmp / "quarantine"
        self.index_path = self.tmp / "triples.ndjson"

    def _clean_call(self, prompt, model, url):
        event = {"kind": "promotion", "evidence": "stated", "level": "core",
                 "s": "person:test", "p": "interested_in", "o": "topic:hiking",
                 "src": f"msg:{self.session_id}#1", "note": "I love hiking in the mountains."}
        return json.dumps(event)

    def test_hermes_load_carries_locus_from_profile_config(self):
        self.assertEqual(self.session["locus"], "locus:home")

    def test_hermes_load_omits_locus_when_profile_has_none(self):
        cfg = {"profiles": {"p": dict(self.source_cfg["profiles"]["p"])}}
        del cfg["profiles"]["p"]["locus"]
        ref = hermes_source.discover(cfg)[0]
        session = hermes_source.load(ref, cfg, self.session_id, f"conv:{self.session_id}")
        self.assertIsNone(session["locus"])

    def test_extract_stamps_locus_on_every_event(self):
        events = promotion.extract(self.session)
        self.assertTrue(events)
        self.assertTrue(all(e.get("locus") == "locus:home" for e in events))

    def test_extract_stamps_nothing_when_session_has_no_locus(self):
        session = dict(self.session, locus=None)
        events = promotion.extract(session)
        self.assertTrue(events)
        self.assertTrue(all("locus" not in e for e in events))

    def test_process_session_appends_locus_tagged_events(self):
        outcome, _counts, _wall, errors = promotion.process_session(
            self.session, self.vocab, self.index_path, self.staging_root, self.quarantine_dir,
            "test-model", "http://unused", promote_call=self._clean_call)
        self.assertEqual(outcome, "ok")
        self.assertEqual(errors, [])

        events = _read_all_staging_events(self.staging_root)
        self.assertTrue(events)
        self.assertTrue(all(e.get("locus") == "locus:home" for e in events),
                         "every event from a locus-bound session must carry the locus field, "
                         "session/observation/promotion alike")

    def test_locus_survives_append_and_rebuild_into_locus_records(self):
        outcome, _counts, _wall, errors = promotion.process_session(
            self.session, self.vocab, self.index_path, self.staging_root, self.quarantine_dir,
            "test-model", "http://unused", promote_call=self._clean_call)
        self.assertEqual(outcome, "ok")
        self.assertEqual(errors, [])

        vocab_path = self.tmp / "vocab.json"
        vocab_path.write_text(json.dumps(self.vocab))
        roots = [{"path": self.staging_root, "collection": "personal"}]
        with unittest.mock.patch.object(journal.config, "VOCAB_FILE", vocab_path):
            journal.rebuild_index(collections={}, roots=roots, index_path=self.index_path, loci_roots=[])

        records = journal.locus_records("locus:home", index_path=self.index_path)
        self.assertTrue(records, "expected locus-tagged events to survive append + rebuild")
        self.assertTrue(any(r.get("o") == "topic:hiking" for r in records))


if __name__ == "__main__":
    unittest.main()
