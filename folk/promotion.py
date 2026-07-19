"""Session-end promotion job -- docs/design/session-promotion-job.md.

Turns a quiescent conversation into journal events, nightly, without anyone
running scripts by hand. Per-session flow (spec's "Per-session flow"):

  1. extract()   -- mechanical, no LLM. Always runs, even if promotion fails.
  2. promote()   -- the one LLM step. Candidate promotion events, not yet appended.
  3. lint        -- full lint (folk.journal.lint_events) against the transcript + vocab.
  4. append or quarantine -- lint-clean events append; a hard failure quarantines
     the whole batch after one automatic retry (fresh generation).
  5. record      -- the idempotency state file, so a session is processed once.

Ported from prototypes/journal-promotion/{extract_observations,promote_llm}.py
(see that prototype's README.md and COMPARISON.md); generalized over the
source-adapter interface in folk/sources/ (Hermes is the only adapter built,
per the spec's build-against-the-interface instruction) and extended per
journal-in-folk.md's "Entity resolution for object slugs": the prompt now
also carries known entity slugs, not just predicates.
"""

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config
from . import journal
from . import review
from . import sources

SNIPPET_LEN = 200
DEFAULT_EXTRACT_ACTOR = "extract:v1"
DEFAULT_PROMOTE_ACTOR = "agent:promote-v1"  # fallback when a session has no persona-agent
DEFAULT_MODEL = "gemma4:31b"
DEFAULT_OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
DEFAULT_CAP_PER_RUN = 10
DEFAULT_QUIET_SECONDS = 3600  # session-end is detected by mtime quiescence, not a hook

CONFIG_FILE = config.CONFIG_DIR / "promotion.json"
STATE_FILE = Path.home() / ".folk" / "promotion-state.json"
STAGING_ROOT = Path.home() / ".folk-staging"
LOG_FILE = Path.home() / ".folk" / "promotion.log"


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------- extract --

def extract(session, extract_actor=DEFAULT_EXTRACT_ACTOR):
    """Mechanical, deterministic: normalized session -> session + observation
    journal events. No LLM -- the "observed" trust tier. This step cannot
    fail on content, only on I/O (session-promotion-job.md step 1).

    When the session is bound to a Locus (session["locus"], set by a source
    adapter per loci.md Decision 2 -- "declared by surface, not inferred"),
    every event this step emits carries that locus field, mechanically --
    not just the session event, since every event from a locus-bound
    surface happened there.
    """
    conv = session["conv"]
    session_ts = session.get("session_ts") or (session["messages"][0]["ts"] if session["messages"] else "")
    session_locus = session.get("locus")

    session_event = {
        "ts": session_ts, "actor": extract_actor, "kind": "session",
        "s": conv, "p": "opened_on", "o": f"platform:{session.get('platform') or 'unknown'}",
        "session": conv, "note": f"profile={session.get('profile', '')}",
    }
    if session.get("counterparty"):
        session_event["counterparty"] = session["counterparty"]
    if session_locus:
        session_event["locus"] = session_locus
    events = [session_event]

    for who in (session.get("user_slug"), session.get("agent_slug")):
        if not who:
            continue
        e = {
            "ts": session_ts, "actor": extract_actor, "kind": "observation",
            "s": who, "p": "participated_in", "o": conv, "session": conv,
        }
        if session_locus:
            e["locus"] = session_locus
        events.append(e)

    for m in session["messages"]:
        e = {
            "ts": m.get("ts") or session_ts, "actor": extract_actor, "kind": "observation",
            "s": m["speaker"], "p": "uttered", "o": f"msg:{session['session_id']}#{m['index']}",
            "session": conv, "note": m["text"][:SNIPPET_LEN],
        }
        if session_locus:
            e["locus"] = session_locus
        events.append(e)
    return events


# ---------------------------------------------------------------- promote --

PROMPT = """You are a memory promotion job for a personal agent system. Below is a conversation between a human (folk id {user_slug}) and their agent (folk id {agent_slug}). Each message is numbered.

Your task: propose which durable facts from this conversation deserve to be remembered as knowledge-graph triples. Emit 5-10 events as NDJSON -- one JSON object per line, no other text, no code fences.

Each event has exactly these fields:
- "kind": always "promotion"
- "evidence": "stated" (the fact was said directly -- note MUST contain the exact quote, copied verbatim) or "interpreted" (your or the agent's reading of the conversation -- note is a one-sentence summary). "stated" additionally requires that the fact's SUBJECT is the SPEAKER of the message "src" points to. When a speaker describes someone else (family, friends, third parties), that is testimony, not a first-person statement: either record it as a fact about the speaker (subject = speaker, evidence "stated"), or as a fact about the third party with evidence "interpreted" -- keep the quote in "note" either way.
- "level": "core" (ordinary durable fact) or "bedrock" (identity-level: childhood, defining moments, core values and beliefs -- these are never auto-applied, only suggested to the human)
- "s": subject folk id (e.g. {user_slug}, {agent_slug})
- "p": predicate -- USE ONE FROM THE VOCABULARY BELOW whenever one fits. Only if no listed predicate fits, coin a new lowercase snake_case predicate AND add "p_def": "<one-line definition>" to the event so it can be reviewed.
- "o": object folk id -- slug with a type prefix from the vocabulary types, lowercase, hyphen-separated (e.g. topic:surfacing-art). PREFER AN EXISTING SLUG FROM THE LIST BELOW over coining a near-duplicate for the same referent.
- "src": "msg:{session_id}#N" where N is the number of the message the fact comes from
- "when": OPTIONAL but important -- if the fact is anchored in time (a date, month, year, or "as of" moment mentioned in the conversation), record it here as YYYY, YYYY-MM, or YYYY-MM-DD. Dates are what make memories queryable later; do not drop them.
- "note": the evidence (see "evidence" above)

Predicate vocabulary (name: definition):
{vocab}

Object type prefixes: {types}

Known entity slugs by type (prefer reusing one of these over coining a near-duplicate):
{entities}

Rules: skip transient chit-chat and operational details that will be stale in a month (container restarts, config tweaks). Keep facts about people, their interests, values, history, and ongoing projects. Do not repeat the same fact twice.

Conversation (session {conv}):

{dialogue}"""


def build_prompt(session, vocab, known_object_slugs):
    vocab_lines = "\n".join(f"- {k}: {v}" for k, v in (vocab.get("predicates") or {}).items() if k != "uttered")
    types = vocab.get("types") or []

    by_type = {}
    for slug in sorted(known_object_slugs or ()):
        by_type.setdefault(slug.split(":", 1)[0], []).append(slug)
    entity_lines = "\n".join(f"- {t}: {', '.join(by_type[t])}" for t in types if by_type.get(t)) or "(none yet)"

    dialogue = "\n\n".join(
        f"[{m['index']}] {'User' if m['role'] == 'user' else 'Assistant'}: {m['text']}"
        for m in session["messages"]
    )

    return (PROMPT
            .replace("{session_id}", session["session_id"])
            .replace("{conv}", session["conv"])
            .replace("{user_slug}", session["user_slug"])
            .replace("{agent_slug}", session["agent_slug"])
            .replace("{vocab}", vocab_lines)
            .replace("{types}", ", ".join(t + ":" for t in types))
            .replace("{entities}", entity_lines)
            .replace("{dialogue}", dialogue))


def call_ollama(prompt, model, url, timeout=560):
    req = urllib.request.Request(
        url,
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)["choices"][0]["message"]["content"]


def parse_promotion_output(text):
    """NDJSON, one candidate promotion event per line. Malformed or
    schema-incomplete lines are rejected (not raised) -- lint is still the
    hard gate; this is just "did the model even emit valid JSON."
    """
    events, rejected = [], []
    for line in text.splitlines():
        line = line.strip().strip("`")
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
            assert e["kind"] == "promotion"
            assert e["evidence"] in ("stated", "interpreted")
            assert e["level"] in ("core", "bedrock")
            assert all(k in e for k in ("s", "p", "o", "src", "note"))
            events.append(e)
        except Exception:
            rejected.append(line)
    return events, rejected


def promote(session, vocab, known_object_slugs, model, ollama_url, call=None):
    """The one LLM step. Returns candidate promotion events, not yet
    appended -- ts/actor/session get filled in by process_session.
    """
    call = call or call_ollama
    prompt = build_prompt(session, vocab, known_object_slugs)
    text = call(prompt, model, ollama_url)
    events, _rejected = parse_promotion_output(text)
    return events


# --------------------------------------------------------- per-session flow --

def process_session(session, vocab, index_path, staging_root, quarantine_dir,
                     model, ollama_url, writer="apu", promote_call=None, max_attempts=2):
    """Extract, promote, lint, append-or-quarantine for one session. Returns
    (outcome, counts, wall_seconds, errors). outcome is "ok", "quarantined",
    or "deferred" (Ollama unreachable/busy -- session-promotion-job.md
    "Never blocks Hermes": retried next run, not quarantined).
    """
    t0 = time.time()

    extract_events = extract(session)
    for e in extract_events:
        journal.append_event(staging_root, writer, e, run_lint=True, vocab=vocab)
    counts = {"session": 1, "observation": sum(1 for e in extract_events if e["kind"] == "observation")}

    known_object_slugs = review._known_object_slugs(index_path)
    transcript_texts = {m["index"]: (m["speaker"], journal._words(m["text"])) for m in session["messages"]}
    now = _now_iso()

    candidates, errors = [], []
    for _attempt in range(max_attempts):
        try:
            candidates = promote(session, vocab, known_object_slugs, model, ollama_url, call=promote_call)
        except OSError as ex:
            wall = time.time() - t0
            return "deferred", counts, wall, [str(ex)]

        for e in candidates:
            e.setdefault("ts", now)
            e.setdefault("actor", session.get("agent_slug") or DEFAULT_PROMOTE_ACTOR)
            e.setdefault("session", session["conv"])
            e.setdefault("v", 1)
            if session.get("locus"):
                e.setdefault("locus", session["locus"])
            e["id"] = journal.compute_id(e["ts"], e["actor"], e.get("s", ""), e.get("p", ""), e.get("o", ""))

        errors, _proposals = journal.lint_events(
            candidates, transcript_texts=transcript_texts, vocab=vocab, known_object_slugs=known_object_slugs)
        if not errors:
            break

    if not errors:
        for e in candidates:
            journal.append_event(staging_root, writer, e, run_lint=False)
        outcome = "ok"
        counts["promotion"] = len(candidates)
    else:
        review.write_quarantine(session["session_id"], candidates, errors, quarantine_dir=quarantine_dir)
        outcome = "quarantined"
        counts["quarantined"] = len(candidates)
        counts["lint_errors"] = len(errors)

    wall = time.time() - t0
    return outcome, counts, wall, errors


# --------------------------------------------------------------- job state --

def load_job_config(path=None):
    path = Path(path) if path else CONFIG_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _load_state(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _log_line(log_path, session_id, outcome, counts, wall):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    parts = " ".join(f"{k}={v}" for k, v in counts.items())
    line = f"{_now_iso()} session={session_id} outcome={outcome} {parts} wall={wall:.1f}s"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ------------------------------------------------------------------- run --

def run_once(job_cfg=None, state_path=None, index_path=None, staging_root=None,
             quarantine_dir=None, log_path=None, cap=None, quiet_seconds=None,
             now=None, promote_call=None):
    """One invocation of the nightly job: discover quiescent, unprocessed
    sessions across every configured source, cap the batch, process each,
    and record outcomes. Returns [(session_id, outcome), ...] for whichever
    sessions were actually processed this run (deferred sessions are not
    recorded in state, so they're retried next run without needing a
    non-empty return value to know why).
    """
    job_cfg = job_cfg if job_cfg is not None else load_job_config()
    state_path = Path(state_path) if state_path else STATE_FILE
    staging_root = Path(staging_root) if staging_root else STAGING_ROOT
    quarantine_dir = Path(quarantine_dir) if quarantine_dir else review.QUARANTINE_DIR
    log_path = Path(log_path) if log_path else LOG_FILE
    index_path = Path(index_path) if index_path else journal.INDEX_PATH
    cap = cap if cap is not None else job_cfg.get("cap_per_run", DEFAULT_CAP_PER_RUN)
    quiet_seconds = quiet_seconds if quiet_seconds is not None else job_cfg.get("quiet_seconds", DEFAULT_QUIET_SECONDS)
    model = job_cfg.get("model", DEFAULT_MODEL)
    ollama_url = job_cfg.get("ollama_url", DEFAULT_OLLAMA_URL)
    now_time = now if now is not None else time.time()

    state = _load_state(state_path)
    vocab = journal.load_vocab()

    candidates = []
    for source_name, source_cfg in (job_cfg.get("sources") or {}).items():
        adapter = sources.get(source_name)
        for ref in adapter.discover(source_cfg):
            session_id = sources.session_id_for(source_name, ref)
            if session_id in state:
                continue
            mt = adapter.mtime(ref)
            if now_time - mt < quiet_seconds:
                continue
            candidates.append((mt, source_name, source_cfg, ref, session_id))

    # Oldest mtime first, so a backlog drains oldest-first across nightly
    # runs; session_id as a stable tiebreak (never filesystem/dict order).
    candidates.sort(key=lambda c: (c[0], c[4]))
    candidates = candidates[:cap]

    results = []
    for _mt, source_name, source_cfg, ref, session_id in candidates:
        adapter = sources.get(source_name)
        conv = f"conv:{session_id}"
        session = adapter.load(ref, source_cfg, session_id, conv)
        this_staging = staging_root / session["collection"]

        outcome, counts, wall, _errors = process_session(
            session, vocab, index_path, this_staging, quarantine_dir,
            model, ollama_url, promote_call=promote_call)

        _log_line(log_path, session_id, outcome, counts, wall)
        if outcome != "deferred":
            state[session_id] = {"ts": _now_iso(), "outcome": outcome}
            _save_state(state_path, state)
        results.append((session_id, outcome))

    return results
