"""folk review -- the queue of pending human decisions over journal events.

Design: docs/design/review-queue.md. The queue is derived, never stored: an
item is pending iff it exists in the journal (or the quarantine dir, for
lint failures) and no `kind: review` event resolves it (matched by `ref` ==
the event's `id`, via journal.resolved_refs -- the same lookup replay() uses,
so "leaves the queue" and "drops from the index" agree by construction).

Four item types (review-queue.md "What queues here"):
  - bedrock   -- promotion events with level: bedrock, unresolved.
  - vocab     -- promotion events that coined a predicate or entity type not
                 in vocab.json (journal.lint_events_detailed's proposals),
                 plus decay-and-supersession.md Decision 4's functional-
                 classification proposals (proposal_kind
                 "functional_classification" -- same item type, reusing the
                 existing vocab-proposal machinery rather than adding a new
                 queue item type, per that decision's closing line).
  - entity    -- promotion events whose object slug looks like a near-dup of
                 an already-known entity slug (same proposal machinery).
  - lint_failure -- whole-session promotion batches quarantined by the
                 session-promotion job (session-promotion-job.md step 4).
                 Never entered the journal, so there is no event id to
                 resolve via a review event -- resolution is an operational
                 action (discard the quarantine files), not a journal write.

Accept side effects (review-queue.md "Accept side-effects by item type"):
  vocab   -> vocab.json predicates/types gain the coined term (or, for a
             functional_classification proposal, the predicate gains
             functional: true -- the next rebuild then supersedes).
  entity  -> vocab.json aliases gains slug -> dup_of.
  bedrock -> a line is appended to the relevant person-file section, shown
             as a diff and confirmed interactively first (typist, not
             author -- HANDOFF.md task 3 guidance).
Reject (any type) writes a review event only, per the spec -- no vocab.json
or person-file change; replay() drops the event's triples via the same
resolved_refs lookup. For functional_classification specifically, a reject
only resolves the one anchor event a given call picked (docstring on
_classification_candidates) -- if other still-unresolved conflicting
promotions remain, the same predicate can propose again under a new anchor
next time. This mirrors the existing imperfect recurrence of predicate/type
proposals (accepting is what actually silences a predicate, by updating
vocab.json) rather than inventing a new persistence mechanism.
"""

import difflib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config
from . import journal
from . import person

QUARANTINE_DIR = Path.home() / ".folk" / "quarantine"


# ------------------------------------------------------------- collection --

def _load_journal_events(roots):
    events = []
    for seg_path, coll_name in journal.iter_segments(roots):
        for e in journal.read_segment(seg_path):
            e = dict(e)
            e["_col"] = coll_name
            events.append(e)
    return events


def _session_counterparties(events):
    out = {}
    for e in events:
        if e.get("kind") == "session" and e.get("session"):
            cps = e.get("counterparty") or []
            if cps:
                out[e["session"]] = cps
    return out


def _known_object_slugs(index_path):
    records = journal.load_index(index_path)
    slugs = {r.get("o") for r in records if r.get("o")}
    slugs |= {r.get("s") for r in records if r.get("s")}
    return slugs


def _classification_candidates(pending_promotions, vocab):
    """decay-and-supersession.md Decision 4: same-(s,p,col) promotion events
    with differing o on a predicate not yet classified functional is the
    signal "the classification question is live" -- surfaced as a
    vocab-shaped proposal, not a new item type. Bedrock-level promotions are
    excluded: identity-level predicates (values, believes, defining_moment)
    are inherently many-valued, so flagging them would just be noise the
    spec's opt-in framing is meant to avoid -- a scoping call made here, not
    stated explicitly in the spec text.

    One item per conflicting (s, p, col) group, anchored on the event with
    the latest ts among the group's still-unresolved members -- that event's
    id is what record_review's ref resolves. Accepting adds functional: true
    to vocab.json globally (silencing every occurrence of the predicate, the
    same way accepting a coined-predicate proposal does); see the module
    docstring for what a reject does and doesn't guarantee.
    """
    functional = set(vocab.get("functional") or [])
    groups = {}
    for e in pending_promotions:
        if e.get("level") == "bedrock":
            continue
        p = e.get("p")
        s, o = e.get("s"), e.get("o")
        if not (p and s and o) or p in functional:
            continue
        groups.setdefault((s, p, e.get("_col")), {}).setdefault(o, []).append(e)

    items = []
    for (s, p, col), by_o in groups.items():
        if len(by_o) < 2:
            continue
        all_events = [e for evs in by_o.values() for e in evs]
        anchor = max(all_events, key=lambda e: e.get("ts", ""))
        items.append({
            "type": "vocab", "proposal_kind": "functional_classification",
            "event_id": anchor.get("id"), "ts": anchor.get("ts", ""),
            "s": s, "p": p, "col": col, "values": sorted(by_o.keys()),
        })
    return items


def _base_item(e, counterparties):
    return {
        "event_id": e.get("id"),
        "ts": e.get("ts", ""),
        "s": e.get("s"), "p": e.get("p"), "o": e.get("o"),
        "evidence": e.get("evidence"), "level": e.get("level"),
        "note": e.get("note", ""), "src": e.get("src", ""), "when": e.get("when"),
        "session": e.get("session"), "col": e.get("_col"),
        "counterparty": counterparties.get(e.get("session"), []),
    }


def pending_items(collections=None, roots=None, index_path=None, quarantine_dir=None, vocab=None):
    """Compute the review queue fresh from the journal (+ quarantine dir for
    lint failures). Nothing is cached: this is the queue's whole design.
    Returns {"bedrock": [...], "vocab": [...], "entity": [...],
    "lint_failure": [...]}, each a list of plain dicts, oldest (by ts) first.
    """
    roots = roots if roots is not None else config.load_journal_roots()
    vocab = vocab if vocab is not None else journal.load_vocab()

    events = _load_journal_events(roots)
    redacted = journal.redacted_ids(events)
    events = [e for e in events if e.get("kind") != "redaction" and e.get("id") not in redacted]
    reviews = journal.resolved_refs(events)
    counterparties = _session_counterparties(events)

    pending_promotions = [
        e for e in events
        if e.get("kind") == "promotion" and e.get("id") and reviews.get(e["id"]) is None
    ]

    bedrock_items = []
    for e in pending_promotions:
        if e.get("level") != "bedrock":
            continue
        item = _base_item(e, counterparties)
        item["type"] = "bedrock"
        bedrock_items.append(item)

    known_object_slugs = _known_object_slugs(index_path)
    _errors, proposals = journal.lint_events_detailed(
        pending_promotions, vocab=vocab, known_object_slugs=known_object_slugs)

    vocab_items, entity_items = [], []
    for p in proposals:
        e = p["event"]
        item = _base_item(e, counterparties)
        if p["kind"] == "entity_alias":
            item["type"] = "entity"
            item["slug"] = p["slug"]
            item["dup_of"] = p["dup_of"]
            entity_items.append(item)
        else:
            item["type"] = "vocab"
            item["proposal_kind"] = p["kind"]  # "predicate" | "type"
            item["value"] = p["value"]
            if p["kind"] == "predicate":
                item["p_def"] = p.get("p_def")
            else:
                item["slug"] = p["slug"]
            vocab_items.append(item)

    vocab_items.extend(_classification_candidates(pending_promotions, vocab))

    lint_failure_items = _load_quarantine_items(quarantine_dir)

    groups = {"bedrock": bedrock_items, "vocab": vocab_items,
              "entity": entity_items, "lint_failure": lint_failure_items}
    for group in groups.values():
        group.sort(key=lambda it: it.get("ts") or "")
    return groups


# ---------------------------------------------------------------- display --

def describe_item(item, verbose=False):
    if item["type"] == "lint_failure":
        lines = [f"[lint_failure] session {item['session']}  "
                 f"({item['n_events']} events quarantined, {len(item['errors'])} lint errors)"]
        if verbose:
            for err in item["errors"]:
                lines.append(f"    {err}")
        return "\n".join(lines)

    if item.get("proposal_kind") == "functional_classification":
        values = ", ".join(item["values"])
        return (f"[vocab] {item['p']!r} has conflicting values for {item['s']} ({values}) "
                f"-- classify as functional: true?")

    tier = item.get("evidence") or ("bedrock candidate" if item["type"] == "bedrock" else "")
    lines = [f"[{item['type']}] {item.get('s', '')} --{item.get('p', '')}--> {item.get('o', '')}"
             + (f"  ({tier})" if tier else "")]
    if item.get("note"):
        lines.append(f"  note: {item['note'][:160]}")
    if item.get("src"):
        lines.append(f"  src: {item['src']}")
    if item.get("when"):
        lines.append(f"  when: {item['when']}")
    if item["type"] == "vocab":
        if item["proposal_kind"] == "predicate":
            lines.append(f"  proposed predicate: {item['value']!r} -- def: {item.get('p_def') or '(none given)'}")
        else:
            lines.append(f"  proposed type: {item['value']!r} (from slug {item.get('slug')!r})")
    if item["type"] == "entity":
        lines.append(f"  {item['slug']!r} looks like a near-duplicate of existing {item['dup_of']!r}")
    if item.get("counterparty"):
        lines.append(f"  ** external counterparty: {', '.join(item['counterparty'])} -- review individually **")
    return "\n".join(lines)


# ----------------------------------------------------------------- accept --

def accept_vocab(item, vocab=None):
    vocab = vocab if vocab is not None else journal.load_vocab()
    if item["proposal_kind"] == "predicate":
        vocab.setdefault("predicates", {})[item["value"]] = item.get("p_def") or "(no definition given)"
    elif item["proposal_kind"] == "functional_classification":
        functional = vocab.setdefault("functional", [])
        if item["p"] not in functional:
            functional.append(item["p"])
    else:  # "type"
        types = vocab.setdefault("types", [])
        if item["value"] not in types:
            types.append(item["value"])
    journal.save_vocab(vocab)
    return vocab


def accept_entity(item, vocab=None):
    vocab = vocab if vocab is not None else journal.load_vocab()
    vocab.setdefault("aliases", {})[item["slug"]] = item["dup_of"]
    journal.save_vocab(vocab)
    return vocab


def _bedrock_target_section(predicate):
    if predicate == "tagged":
        return "tags"
    if predicate and predicate.startswith("associat"):
        return "associations"
    return "defining moments"


def preview_bedrock_edit(item, collections=None):
    """Compute (without writing) the person-file edit a bedrock accept would
    make. Returns (fpath, section, line, diff_text); diff_text is '' when the
    line is already present (nothing to add, safe to record accept as a
    no-op edit).
    """
    collections = collections if collections is not None else config.load_collections()
    coll_dir = collections.get(item["col"])
    if not coll_dir:
        raise ValueError(f"no registered collection {item['col']!r}")

    subject = item["s"] or ""
    slug = subject.split(":", 1)[-1] if subject.startswith("person:") else subject
    fpath = person._find_person_file(Path(coll_dir), slug)
    if not fpath:
        raise ValueError(f"no person file for {subject!r}")

    section = _bedrock_target_section(item["p"])
    if section == "tags":
        line = item["o"].split(":", 1)[-1] if ":" in item["o"] else item["o"]
    elif section == "associations":
        label = item["o"].split(":", 1)[-1].replace("-", " ")
        line = f"- [{label}]({item['o']}) — {item['p']}"
    else:
        line = f"- {item['o']}" + (f" — {item['note']}" if item.get("note") else "")

    before = fpath.read_text(encoding="utf-8", errors="replace")
    sections = person._parse_sections(before)

    if section == "tags":
        tags = person._parse_tags(sections)
        if line in tags:
            return fpath, section, line, ""
        new_sections = dict(sections)
        new_sections[section] = [" ".join(tags + [line])]
    else:
        existing = sections.get(section, [])
        cleaned = [] if existing == [""] else existing
        if line.strip() in [l.strip() for l in cleaned]:
            return fpath, section, line, ""
        new_sections = dict(sections)
        new_sections[section] = cleaned + [line]

    after = person._build_content(new_sections)
    diff = "\n".join(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=str(fpath), tofile=str(fpath), lineterm=""))
    return fpath, section, line, diff


def apply_bedrock_edit(fpath, section, line):
    """Actually write the edit preview_bedrock_edit computed. Call only after
    the human has seen the diff and confirmed -- the person file remains
    human-owned; this is a typist, not an author.
    """
    if section == "tags":
        content = fpath.read_text(encoding="utf-8", errors="replace")
        sections = person._parse_sections(content)
        tags = person._parse_tags(sections)
        if line in tags:
            return False
        tags.append(line)
        sections["tags"] = [" ".join(tags)]
        fpath.write_text(person._build_content(sections))
        return True
    return person.append_line_to_section(fpath, section, line)


# ------------------------------------------------------------ review event --

def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _root_for_collection(col, roots):
    for r in roots:
        if r["collection"] == col:
            return Path(r["path"])
    raise ValueError(f"no registered journal root for collection {col!r}")


def record_review(item, verdict, roots=None):
    """Append a kind: review event resolving item['event_id']. actor is
    always human (journal-schema.md). Runs through append_event, so it gets
    id/v and (harmlessly, since review isn't an INDEXABLE_KIND) a lint pass.
    """
    roots = roots if roots is not None else config.load_journal_roots()
    root_path = _root_for_collection(item["col"], roots)
    event = {"kind": "review", "actor": "human", "ts": _now_iso(),
              "verdict": verdict, "ref": item["event_id"]}
    return journal.append_event(root_path, "human", event, run_lint=True)


# ------------------------------------------------------------- quarantine --

def write_quarantine(session_id, events, errors, quarantine_dir=None):
    """Write a session's failed promotion batch to the quarantine dir, with
    its lint report alongside -- the shape session-promotion-job.md's step 4
    ("Append or quarantine") produces on a hard lint failure. folk review
    reads this format as lint_failure items; this is the writer side, used
    by that job (task 4, not yet built) and by tests exercising the queue
    against a quarantined batch.
    """
    qdir = Path(quarantine_dir) if quarantine_dir else QUARANTINE_DIR
    qdir.mkdir(parents=True, exist_ok=True)
    seg = qdir / f"{session_id}.ndjson"
    with open(seg, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n")
    (qdir / f"{session_id}.errors.txt").write_text("\n".join(errors) + "\n", encoding="utf-8")
    return seg


def _load_quarantine_items(quarantine_dir=None):
    qdir = Path(quarantine_dir) if quarantine_dir else QUARANTINE_DIR
    items = []
    if not qdir.is_dir():
        return items
    for f in sorted(qdir.glob("*.ndjson")):
        session_id = f.stem
        events = journal.read_segment(f)
        errors_path = f.with_name(f"{session_id}.errors.txt")
        errors = [l for l in errors_path.read_text(encoding="utf-8").splitlines() if l.strip()] \
            if errors_path.exists() else []
        ts = max((e.get("ts", "") for e in events), default="")
        items.append({
            "type": "lint_failure",
            "session": session_id,
            "ts": ts,
            "n_events": len(events),
            "errors": errors,
            "path": str(f),
        })
    return items


def discard_quarantine(item):
    """Delete a quarantined batch's files -- the usual triage outcome per
    review-queue.md ("the fix is usually editing nothing and discarding").
    No journal event: the batch never entered the journal, so there is
    nothing for a review event to resolve.
    """
    path = Path(item["path"])
    path.unlink(missing_ok=True)
    path.with_name(f"{item['session']}.errors.txt").unlink(missing_ok=True)
