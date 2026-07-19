"""Journal: append-only NDJSON event segments, lint, and replay.

Event shape is normative in docs/design/journal-schema.md — this module is
its executable form (per CLAUDE.md: "Lint is the executable form of this
document; if they disagree, fix whichever is wrong"). Ported from
prototypes/journal-promotion/{replay,lint,extract_observations}.py; see
that prototype's README.md and COMPARISON.md for why each check exists.

Three read paths share this module:
  - replay()       -> the index (folk index --rebuild). Pure, no lint.
  - lint_events()   -> gate run before any programmatic append (invariant 6).
  - append_event()  -> computes id, lints, writes to a per-writer segment.
"""

import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from . import config

SLUG_RE = re.compile(r"^[a-z]+:[a-z0-9][a-z0-9-]*$")
MSG_SRC_RE = re.compile(r"^msg:.+#(\d+)$")
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
SHINGLE = 5  # consecutive words that must match, in order, to verify a quote

KNOWN_KINDS = frozenset({"session", "observation", "promotion", "review", "redaction"})
INDEXABLE_KINDS = frozenset({"session", "observation", "promotion"})
SUPPORTED_V = frozenset({1})

INDEX_PATH = Path.home() / ".folk" / "triples.ndjson"


class LintError(Exception):
    """Raised by append_event when a hard lint error blocks the append."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


# ---------------------------------------------------------------- identity --

def compute_id(ts, actor, s="", p="", o=""):
    """12 hex chars of sha256 over ts|actor|s|p|o (journal-schema.md)."""
    material = f"{ts}|{actor}|{s or ''}|{p or ''}|{o or ''}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


# -------------------------------------------------------------------- vocab --

def load_vocab():
    if not config.VOCAB_FILE.exists():
        return {"types": [], "predicates": {}, "aliases": {}, "stability": {}, "functional": [], "decay": {}}
    try:
        data = json.loads(config.VOCAB_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("types", [])
    data.setdefault("predicates", {})
    data.setdefault("aliases", {})
    # decay-and-supersession.md Decision 2/3: per-predicate attributes, config
    # only, opt-in. `stability`: predicate -> "identity" | "situational"
    # (unclassified predicates never decay). `functional`: list of predicates
    # that can hold only one value at a time (drives rebuild-time
    # supersession). `decay`: {"aging_days": N, "stale_days": M} thresholds
    # for the "situational" class -- see DEFAULT_DECAY when this is absent.
    data.setdefault("stability", {})
    data.setdefault("functional", [])
    data.setdefault("decay", {})
    return data


def save_vocab(vocab):
    config.ensure_config_dir()
    config.VOCAB_FILE.write_text(json.dumps(vocab, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ decay --

DEFAULT_DECAY = {"aging_days": 90, "stale_days": 365}


def staleness(record, now, vocab=None):
    """fresh | aging | stale -- a pure read-time lens (decay-and-supersession.md
    Decision 1), never called from the rebuild/write path and never persisted:
    `now` is always injected, so this is testable with a fixed clock and adds
    nothing to the index. Decision 2's safe default: a predicate with no
    `stability` entry in vocab.json, or classified `identity`, never goes
    stale -- only `situational` predicates age, measured from
    `last_reinforced` against vocab.json's `decay` thresholds (falling back
    to DEFAULT_DECAY when that block is absent or a predicate is unclassified
    but still marked situational without custom thresholds).
    """
    vocab = vocab if vocab is not None else load_vocab()
    stability = (vocab.get("stability") or {}).get(record.get("p"))
    if stability != "situational":
        return "fresh"

    last = record.get("last_reinforced")
    if not last:
        return "fresh"
    try:
        last_dt = datetime.fromisoformat(last)
    except (ValueError, TypeError):
        return "fresh"

    age_days = (now - last_dt).total_seconds() / 86400
    decay = vocab.get("decay") or {}
    aging_days = decay.get("aging_days", DEFAULT_DECAY["aging_days"])
    stale_days = decay.get("stale_days", DEFAULT_DECAY["stale_days"])
    if age_days >= stale_days:
        return "stale"
    if age_days >= aging_days:
        return "aging"
    return "fresh"


# ---------------------------------------------------------- segments/roots --

def iter_segments(roots=None):
    """Yield (segment_path, collection) for every *.ndjson file directly inside
    a registered journal root, sorted for determinism (never filesystem order).
    """
    if roots is None:
        roots = config.load_journal_roots()
    found = []
    for root in roots:
        root_path = Path(root["path"])
        if not root_path.is_dir():
            continue
        for f in root_path.iterdir():
            if f.is_file() and f.suffix == ".ndjson":
                found.append((f, root["collection"]))
    return sorted(found, key=lambda pair: str(pair[0]))


def read_segment(path):
    """Parse one NDJSON segment. Malformed lines are skipped with a stderr warning."""
    events = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError as ex:
            print(f"journal: {path}:{lineno}: invalid JSON, skipping ({ex})", file=sys.stderr)
            continue
        events.append(e)
    return events


def _current_segment_name(ts, writer):
    month = (ts or "")[:7]
    if not re.match(r"^\d{4}-\d{2}$", month):
        month = date.today().isoformat()[:7]
    return f"{month}.{writer}.ndjson"


def append_event(root_path, writer, event, run_lint=True, transcript_texts=None, vocab=None):
    """Compute id (and v if absent), lint, then append to the writer's current
    per-writer monthly segment in root_path. Raises LintError on a hard failure
    -- nothing is written when that happens (invariant 6: lint before append).
    """
    root_path = Path(root_path)
    event = dict(event)
    event.setdefault("v", 1)
    event["id"] = compute_id(event.get("ts", ""), event.get("actor", ""),
                              event.get("s", ""), event.get("p", ""), event.get("o", ""))

    if run_lint:
        errors, _proposals = lint_events([event], transcript_texts=transcript_texts, vocab=vocab)
        if errors:
            raise LintError(errors)

    root_path.mkdir(parents=True, exist_ok=True)
    seg_path = root_path / _current_segment_name(event.get("ts", ""), writer)
    with open(seg_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
    return event


# --------------------------------------------------------------------- lint --

def _words(text):
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def quote_found(note, msg_words):
    """True if any SHINGLE consecutive words of note appear in order in msg_words."""
    nw = _words(note)
    if len(nw) < SHINGLE:
        return True  # too short to verify meaningfully
    msg_join = " " + " ".join(msg_words) + " "
    return any(
        " " + " ".join(nw[i:i + SHINGLE]) + " " in msg_join
        for i in range(len(nw) - SHINGLE + 1)
    )


def _self_contained_transcript_texts(events):
    """Best-effort {idx: (speaker_slug, words)} built from uttered observation
    events in the same batch. Notes are drill-down snippets (may be truncated),
    so this is a fallback -- pass transcript_texts explicitly (from the raw
    source transcript) for authoritative quote verification.
    """
    texts = {}
    for e in events:
        if e.get("kind") != "observation" or e.get("p") != "uttered":
            continue
        m = MSG_SRC_RE.match(e.get("o", ""))
        if not m:
            continue
        texts[int(m.group(1))] = (e.get("s", ""), _words(e.get("note", "")))
    return texts


def build_transcript_texts(transcript_path, user_slug, agent_slug):
    """Parse a raw source transcript (Hermes session JSONL shape: one {role,
    content} object per line) into {idx: (speaker_slug, words)} for authoritative
    quote verification -- the transcript-file mode of the prototype's lint.py.
    """
    texts = {}
    for idx, line in enumerate(Path(transcript_path).read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        role = e.get("role")
        if role not in ("user", "assistant"):
            continue
        content = e.get("content")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
        content = THINK_RE.sub("", content or "")
        speaker = user_slug if role == "user" else agent_slug
        texts[idx] = (speaker, _words(content))
    return texts


def _slug_tokens(slug):
    return set(re.split(r"[-:]", slug)) - {""}


def _near_duplicate(slug, known_slugs, threshold=0.6):
    st = _slug_tokens(slug)
    if not st:
        return None
    prefix = slug.split(":")[0]
    best = None
    for k in known_slugs:
        if k == slug or k.split(":")[0] != prefix:
            continue
        kt = _slug_tokens(k)
        if not kt:
            continue
        overlap = len(st & kt) / len(st | kt)
        if overlap >= threshold and (best is None or overlap > best[1]):
            best = (k, overlap)
    return best[0] if best else None


def lint_events_detailed(events, transcript_texts=None, vocab=None, known_object_slugs=None):
    """Same checks as lint_events, but proposals are structured dicts rather
    than pre-formatted strings -- {"kind": "predicate"|"type"|"entity_alias",
    "event_id", "index", "event", ...}. This is what folk review (review.py)
    groups into vocab/entity queue items without re-parsing lint's text
    output; lint_events() below is a thin formatter on top for CLI/text use
    (folk journal lint), unchanged from before this split.
    """
    vocab = vocab if vocab is not None else load_vocab()
    known_types = set(vocab.get("types") or [])
    known_preds = set((vocab.get("predicates") or {}).keys())
    known_object_slugs = set(known_object_slugs or [])
    texts = transcript_texts if transcript_texts is not None else _self_contained_transcript_texts(events)

    errors, proposals = [], []
    seen_triples = set()

    for i, e in enumerate(events, 1):
        eid = e.get("id", "?")
        label = f"#{i} ({eid})"
        kind = e.get("kind")

        if kind not in KNOWN_KINDS:
            print(f"journal lint: {label}: unknown kind {kind!r}, skipping", file=sys.stderr)
            continue
        v = e.get("v")
        if v is not None and v not in SUPPORTED_V:
            print(f"journal lint: {label}: unknown schema version v={v!r}, skipping", file=sys.stderr)
            continue
        if kind not in INDEXABLE_KINDS:
            continue  # review/redaction: nothing to lint here

        for field in ("ts", "actor", "kind"):
            if not e.get(field):
                errors.append(f"{label}: missing field {field!r}")

        expected_id = compute_id(e.get("ts", ""), e.get("actor", ""), e.get("s", ""), e.get("p", ""), e.get("o", ""))
        if "id" not in e:
            errors.append(f"{label}: missing id")
        elif e["id"] != expected_id:
            errors.append(f"{label}: id mismatch (stored {e['id']!r}, recomputed {expected_id!r})")

        if kind == "promotion":
            if e.get("evidence") not in ("stated", "interpreted"):
                errors.append(f"{label}: evidence must be stated|interpreted, got {e.get('evidence')!r}")
            if e.get("level") not in ("core", "bedrock"):
                errors.append(f"{label}: level must be core|bedrock, got {e.get('level')!r}")
            if not e.get("note"):
                errors.append(f"{label}: promotion missing note")
            if e.get("evidence") == "stated" and not e.get("src"):
                errors.append(f"{label}: stated promotion missing src")

        for field in ("s", "o"):
            slug = e.get(field) or ""
            if not slug:
                continue
            if slug.split(":", 1)[0] in ("conv", "msg"):
                continue  # session/message pointers (external ids), not curated entity slugs
            if not SLUG_RE.match(slug):
                errors.append(f"{label}: malformed slug {slug!r} in {field} (want type:lower-hyphen)")
                continue
            slug_type = slug.split(":")[0]
            if slug_type not in known_types:
                proposals.append({"kind": "type", "event_id": eid, "index": i, "event": e,
                                   "value": slug_type, "slug": slug})
            elif field == "o" and slug not in known_object_slugs:
                dup = _near_duplicate(slug, known_object_slugs)
                if dup:
                    proposals.append({"kind": "entity_alias", "event_id": eid, "index": i, "event": e,
                                       "slug": slug, "dup_of": dup})

        pred = e.get("p") or ""
        if pred and pred not in known_preds:
            proposals.append({"kind": "predicate", "event_id": eid, "index": i, "event": e,
                               "value": pred, "p_def": e.get("p_def")})

        # Duplicate (s,p,o) is a hard error for promotions only: a repeated
        # observation with its own src is a legitimate re-observation (it
        # refreshes last_reinforced at replay) -- see journal-schema.md
        # "Source adapters".
        s, p, o = e.get("s"), e.get("p"), e.get("o")
        if kind == "promotion" and s and p and o:
            key = (s, p, o)
            if key in seen_triples:
                errors.append(f"{label}: duplicate triple {key}")
            seen_triples.add(key)

        if kind == "promotion":
            src = e.get("src", "")
            m = MSG_SRC_RE.match(src) if src else None
            if src and not m:
                if e.get("evidence") == "stated":
                    errors.append(f"{label}: unparseable src {src!r}")
            elif m:
                idx = int(m.group(1))
                if idx not in texts:
                    if e.get("evidence") == "stated":
                        errors.append(f"{label}: src points at message #{idx}, which has no known utterance")
                else:
                    speaker, msg_words = texts[idx]
                    if e.get("evidence") == "stated":
                        if not quote_found(e.get("note", ""), msg_words):
                            errors.append(
                                f"{label}: stated evidence not found in msg #{idx} -- no {SHINGLE}-word run of the note appears there")
                        if speaker and e.get("s") != speaker:
                            errors.append(
                                f"{label}: stated fact about {e.get('s')} cites a message spoken by {speaker!r} "
                                f"(#{idx}) -- the subject didn't say this here; downgrade to interpreted or re-source")

    return errors, proposals


def _format_proposal(p):
    label = f"#{p['index']} ({p['event_id']})"
    if p["kind"] == "type":
        return f"{label}: new type {p['value']!r} in {p['slug']!r}"
    if p["kind"] == "entity_alias":
        return f"{label}: {p['slug']!r} looks like a near-duplicate of existing {p['dup_of']!r}"
    # predicate
    suffix = f" -- def: {p['p_def']}" if p.get("p_def") else " (no p_def given)"
    return f"{label}: new predicate {p['value']!r}" + suffix


def lint_events(events, transcript_texts=None, vocab=None, known_object_slugs=None):
    """Deterministic, no-LLM lint. Returns (errors, proposals) -- both lists of
    human-readable strings. Hard errors should block an append; proposals are
    soft output (vocab/type coinages, entity near-duplicates) that queue for
    `folk review`, per journal-schema.md and journal-in-folk.md. See
    lint_events_detailed for the structured form folk review builds on.
    """
    errors, proposals = lint_events_detailed(events, transcript_texts, vocab, known_object_slugs)
    return errors, [_format_proposal(p) for p in proposals]


def lint_paths(paths, transcript_path=None, user_slug=None, agent_slug=None, vocab=None, known_object_slugs=None):
    """Lint one or more segment files together (segments mix kinds in folk-proper,
    so a promotion's src is usually resolvable against an observation event in
    the same or a sibling file). Returns (errors, proposals, n_events).
    """
    events = []
    for p in paths:
        events.extend(read_segment(p))
    transcript_texts = None
    if transcript_path:
        transcript_texts = build_transcript_texts(transcript_path, user_slug, agent_slug)
    errors, proposals = lint_events(events, transcript_texts=transcript_texts, vocab=vocab,
                                     known_object_slugs=known_object_slugs)
    return errors, proposals, len(events)


# ------------------------------------------------------------- review refs --

def redacted_ids(events):
    """Ids expunged by a kind: redaction event in this batch."""
    return {e["ref"] for e in events if e.get("kind") == "redaction" and e.get("ref")}


def resolved_refs(events):
    """Map event id -> (verdict, ts) for the most recent kind: review event
    referencing it. Shared by replay() and folk review (review.py) so
    "pending iff no resolving review event" is computed identically
    everywhere -- review-queue.md's queue derivation.
    """
    reviews = {}
    for e in events:
        if e.get("kind") != "review" or not e.get("ref"):
            continue
        prev = reviews.get(e["ref"])
        if prev is None or e.get("ts", "") >= prev[1]:
            reviews[e["ref"]] = (e.get("verdict"), e.get("ts", ""))
    return reviews


# ------------------------------------------------------------------ replay --

def _person_triples(collection_dir, collection_name):
    from .person import _person_files, _parse_sections, _parse_tags, _parse_associations

    triples = []
    for slug, fpath in _person_files(collection_dir):
        sid = f"person:{slug}"
        content = fpath.read_text(encoding="utf-8", errors="replace")
        sections = _parse_sections(content)
        for tag in _parse_tags(sections):
            triples.append({"s": sid, "p": "tagged", "o": f"tag:{tag}",
                             "tier": "human", "col": collection_name, "src": fpath.name})
        for assoc in _parse_associations(sections):
            ref = assoc.get("ref")
            if ref:
                target_id = ref
            else:
                target_name = assoc.get("name", "")
                target_id = "person:" + re.sub(r"[^a-z0-9]+", "-", target_name.lower()).strip("-")
            rel = assoc.get("type") or "associated"
            triples.append({"s": sid, "p": rel, "o": target_id,
                             "tier": "human", "col": collection_name, "src": fpath.name})
    return triples


def _journal_record(e, collection_name, tier):
    rec = {"s": e["s"], "p": e["p"], "o": e["o"], "tier": tier, "col": collection_name,
           "src": e.get("src") or e.get("session", "")}
    if e.get("note"):
        rec["note"] = e["note"]
    if e.get("when"):
        rec["when"] = e["when"]
    if e.get("locus"):
        rec["locus"] = e["locus"]
    rec["_ts"] = e.get("ts", "")
    # Internal only -- the source event's id, needed to point a losing
    # triple's superseded_by at its winner (_apply_supersession). Stripped
    # before the index is written, same lifecycle as _ts.
    rec["_id"] = e.get("id", "")
    return rec


def _locus_triples(loci_root_dir, collection_name):
    from .locus import _locus_files
    from .person import _parse_sections, _parse_tags, _parse_associations

    triples = []
    for slug, fpath in _locus_files(loci_root_dir):
        sid = f"locus:{slug}"
        content = fpath.read_text(encoding="utf-8", errors="replace")
        sections = _parse_sections(content)
        for tag in _parse_tags(sections):
            triples.append({"s": sid, "p": "tagged", "o": f"tag:{tag}",
                             "tier": "human", "col": collection_name, "src": fpath.name})
        for assoc in _parse_associations(sections):
            ref = assoc.get("ref")
            if ref:
                target_id = ref
            else:
                target_name = assoc.get("name", "")
                target_id = "person:" + re.sub(r"[^a-z0-9]+", "-", target_name.lower()).strip("-")
            rel = assoc.get("type") or "associated"
            triples.append({"s": sid, "p": rel, "o": target_id,
                             "tier": "human", "col": collection_name, "src": fpath.name})
    return triples


# -------------------------------------------------------------- supersession --

TIER_RANK = {"human": 3, "observed": 2, "stated": 1, "interpreted": 0}


def _apply_supersession(all_triples, vocab):
    """Rebuild-time projection (decay-and-supersession.md Decision 3): among
    triples sharing (s, p, col) where p is functional: true in vocab, the
    distinct-object value with the latest time anchor (`when`, else the
    source event's `ts`; person-file triples carry no anchor at all) wins
    its slot. Every other, non-human-tier value of equal-or-lower trust tier
    gets a superseded_by pointer at the winner's event id ("human" when the
    winner is a person-file triple). Exact anchor ties leave the whole slot
    untouched entirely -- ambiguity is preserved, never hash-tiebroken --
    and human-tier triples are never marked as losers regardless of tier
    rank ("the person file is ended only by the human editing it"), which a
    plain tier-rank comparison alone would not guarantee since two
    human-tier values would otherwise tie in rank against each other.
    Mutates all_triples in place. Must run before _ts/_id are stripped and
    after alias resolution, so slots key off canonical slugs.
    """
    functional_preds = set(vocab.get("functional") or [])
    if not functional_preds:
        return

    groups = {}
    for t in all_triples:
        p = t.get("p")
        if p not in functional_preds:
            continue
        groups.setdefault((t["s"], p, t["col"]), []).append(t)

    for members in groups.values():
        by_o = {}
        for t in members:
            o = t["o"]
            anchor = t.get("when") or t.get("_ts") or ""
            rank = TIER_RANK.get(t.get("tier"), -1)
            best = by_o.get(o)
            if best is None or (anchor, rank) > (best["anchor"], best["rank"]):
                by_o[o] = {"anchor": anchor, "rank": rank, "id": t.get("_id") or "human"}
        if len(by_o) < 2:
            continue

        top_anchor = max(v["anchor"] for v in by_o.values())
        winners = [o for o, v in by_o.items() if v["anchor"] == top_anchor]
        if len(winners) != 1:
            continue  # exact tie: ambiguity preserved, never hash-tiebroken

        winner_o = winners[0]
        winner = by_o[winner_o]
        for t in members:
            if t["o"] == winner_o or t.get("tier") == "human":
                continue
            if TIER_RANK.get(t.get("tier"), -1) > winner["rank"]:
                continue  # guard: only equal-or-higher trust can supersede
            t["superseded_by"] = winner["id"]


def replay(collections=None, roots=None, loci_roots=None):
    """Parse person files (human tier) + replay all journal segments (observed/
    stated/interpreted tiers; bedrock -> suggestions) into (triples, suggestions).
    Pure and deterministic: no LLM, no wall-clock, sorted segment order. Review
    events resolve pending items; redaction events expunge their ref'd event
    entirely, before anything else is processed. Locus files (loci.md Decision 3)
    contribute curated cast/tag edges the same way person files do, keyed off
    locus:<slug> instead of person:<slug>.
    """
    collections = collections if collections is not None else config.load_collections()
    roots = roots if roots is not None else config.load_journal_roots()
    loci_roots = loci_roots if loci_roots is not None else config.load_loci_roots()
    vocab = load_vocab()
    aliases = vocab.get("aliases", {})

    all_triples = []
    for name, coll_dir in sorted(collections.items()):
        all_triples.extend(_person_triples(Path(coll_dir), name))
    for root in loci_roots:
        all_triples.extend(_locus_triples(Path(root["path"]), root["collection"]))

    all_events = []
    for seg_path, coll_name in iter_segments(roots):
        for e in read_segment(seg_path):
            e = dict(e)
            e["_col"] = coll_name
            all_events.append(e)

    redacted = redacted_ids(all_events)
    all_events = [e for e in all_events if e.get("kind") != "redaction" and e.get("id") not in redacted]

    reviews = resolved_refs(all_events)

    suggestions = []
    for e in all_events:
        kind = e.get("kind")
        if kind not in KNOWN_KINDS:
            print(f"journal replay: unknown kind {kind!r}, skipping", file=sys.stderr)
            continue
        v = e.get("v")
        if v is not None and v not in SUPPORTED_V:
            print(f"journal replay: unknown schema version v={v!r}, skipping", file=sys.stderr)
            continue
        if kind not in INDEXABLE_KINDS:
            continue
        s, p, o = e.get("s"), e.get("p"), e.get("o")
        if not (s and p and o):
            continue

        eid = e.get("id")
        verdict = reviews.get(eid, (None, None))[0] if eid else None
        if verdict == "reject":
            continue

        if kind == "promotion" and e.get("level") == "bedrock":
            if verdict is None:
                suggestions.append(_journal_record(e, e["_col"], "candidate"))
            continue

        if kind == "promotion":
            tier = "stated" if e.get("evidence") == "stated" else "interpreted"
        else:  # session/observation
            if p == "uttered":
                continue  # journal-only, drill-down; never indexed
            tier = "observed"
        all_triples.append(_journal_record(e, e["_col"], tier))

    def _alias(slug):
        return aliases.get(slug, slug)

    for t in all_triples + suggestions:
        t["s"] = _alias(t["s"])
        t["o"] = _alias(t["o"])

    _apply_supersession(all_triples, vocab)

    reinforced = {}
    event_counts = {}
    for t in all_triples:
        ts = t.pop("_ts", "")
        t.pop("_id", None)
        key = (t["s"], t["p"], t["o"])
        if ts:
            event_counts[key] = event_counts.get(key, 0) + 1
            if key not in reinforced or ts > reinforced[key]:
                reinforced[key] = ts
    for t in all_triples:
        key = (t["s"], t["p"], t["o"])
        if key in reinforced:
            t["last_reinforced"] = reinforced[key]
            # reinforce_count (folk-surface.md's recurrence ranker): how many
            # distinct journal events asserted this exact triple. Present
            # alongside last_reinforced only -- a human-only triple has
            # neither, same as today.
            t["reinforce_count"] = event_counts[key]

    for t in suggestions:
        t.pop("_ts", None)

    return all_triples, suggestions


def rebuild_index(collections=None, roots=None, index_path=None, loci_roots=None):
    """Replay everything and write the deterministic index to disk. Run twice:
    byte-identical (sorted by each record's canonical JSON string, fixed
    separators, no wall-clock fields). Returns (n_triples, n_suggestions,
    n_superseded) -- the supersession count is surfaced so a surprising jump
    is visible (decay-and-supersession.md Decision 4's closing line).
    """
    index_path = Path(index_path) if index_path else INDEX_PATH
    triples, suggestions = replay(collections, roots, loci_roots)
    n_superseded = sum(1 for t in triples if t.get("superseded_by"))
    lines = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in triples + suggestions]
    lines.sort()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    return len(triples), len(suggestions), n_superseded


TIER_LABELS = {
    "human": "Curated (you wrote this)",
    "observed": "Observed (mechanical record)",
    "stated": "Stated (direct statement, agent-recorded -- quote + src)",
    "interpreted": "Interpreted (agent inference -- verify via src pointer)",
    "candidate": "Bedrock suggestions (awaiting your decision -- not fact)",
}
TIER_ORDER = ("human", "observed", "stated", "interpreted", "candidate")


def load_index(index_path=None):
    index_path = Path(index_path) if index_path else INDEX_PATH
    if not index_path.exists():
        return []
    records = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _group_by_tier(records):
    grouped = {tier: [] for tier in TIER_ORDER}
    for r in records:
        tier = r.get("tier")
        if tier in grouped:
            grouped[tier].append(r)
    return grouped


def person_profile(person_id, index_path=None):
    """Group every index record touching person_id by trust tier, in tier order.

    Excludes a Locus's own curated cast edges (s: locus:X) even when they
    name this person as object -- loci.md Decision 1: the barrier is
    enforced on the Locus side, so a guest_of edge curated in a Locus's
    file must not widen the person's own default profile. A guest_of edge
    the person curated in their *own* file (s: person_id) still counts.
    """
    records = load_index(index_path)
    mine = [r for r in records
            if r.get("s") == person_id
            or (r.get("o") == person_id and not (r.get("s") or "").startswith("locus:"))]
    return _group_by_tier(mine)


def locus_records(locus_id, index_path=None):
    """Every index record inside a Locus's barrier (loci.md Decision 1):
    journal events whose locus field matches (the ephemeral tunnel --
    drill-down only), plus curated associations naming the Locus directly,
    from either the Locus's own file or a participant's file (the durable
    tunnel, guest_of). A triple that is neither is out of scope, even if it
    involves someone who also appears in this Locus elsewhere.
    """
    records = load_index(index_path)
    return [r for r in records
            if r.get("locus") == locus_id or r.get("s") == locus_id or r.get("o") == locus_id]


def locus_profile(locus_id, index_path=None):
    """Group a Locus's barrier-scoped records by trust tier, same rendering
    path as person_profile -- folk show locus:X reuses folk show person:X's
    tiered display.
    """
    return _group_by_tier(locus_records(locus_id, index_path))
