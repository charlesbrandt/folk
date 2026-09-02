"""Bulk/mechanical import batch runner (docs/design/bulk-import.md).

Not a transcript source adapter -- folk/sources/'s discover/mtime/load
contract and folk/promotion.py's extract/LLM-promote/lint/quarantine
pipeline are for conversational sources. A bulk import (e.g. a scraped
directory export) has no conversation and no LLM step: it is already-shaped
`kind: observation` events going straight through journal.append_event's own
lint (invariant 6 is satisfied per-event, nothing extra needed here).

The one real gap this module fills: journal.append_event raises LintError
and writes nothing on a hard failure, which is correct for a single event,
but a caller importing many independent scraped rows does not want one bad
row to abort the whole run (docs/design/bulk-import.md Decision 1 -- unlike
folk/promotion.py's all-or-nothing session quarantine, a bulk import's rows
share no authorship and no reasoning chain, so one bad row says nothing
about its siblings). import_batch() is the four-line try/except loop this
reasoning implies, written once so no caller reimplements it slightly
differently each time.

Deliberately NOT here: any call to triples.index_rebuild() (docs/design/
bulk-import.md Decision 2 -- rebuild once, externally, after the batch, the
same two-step pattern deploy/README.md already documents for folk promote);
any identity-resolution logic (Decision 4 -- deferred to
docs/design/identity-resolution.md); any retry or batching policy.

One thing that *is* here, added after the rest of this module: best-effort
person-file minting, now that the maintainer has confirmed a mechanical
importer may create `person:` files directly (docs/design/
identity-resolution.md Open Questions, 2026-08-30). The creation path
itself -- validating the slug, checking the target collection's curation
policy, refusing to overwrite -- is entirely person.create_person_file_as_agent
(docs/design/collection-curation.md); import_batch only decides *when* to
call it and never loosens what it refuses.
"""

from . import journal
from . import person


def import_batch(root_path, writer, events, vocab=None, collection_dir=None, person_names=None):
    """Append an iterable of already-shaped `kind: observation` event dicts
    to one journal root, one at a time, skip-and-report on a per-event lint
    failure rather than raising (docs/design/bulk-import.md Decision 1).

    Returns a list of outcome dicts, one per input event, in input order:
      {"src": event.get("src"), "status": "appended" | "skipped",
       "event": <appended event with id/v filled in> | None,
       "reason": <lint error text> | None,
       "minted": <path to a newly created person file, as str> | None}

    journal.append_event's lint is unchanged and still runs per event
    (invariant 6) -- this wraps its LintError, it does not loosen it. A
    non-lint exception (e.g. an unwritable root_path) is not caught here
    and propagates, since that is an operational failure affecting the
    whole batch, not a single record's data quality.

    collection_dir and person_names together enable person-file minting for
    an event's subject, when it is a `person:<slug>` this call hasn't
    already minted: person_names maps the subject ref (e.g.
    "person:priya-anand") to the display name to write as the file's `#`
    heading -- bulk.py has no record shape of its own to pull a name from
    (that's the caller's raw record, already gone by the time it built the
    event), so it asks for the name explicitly rather than guessing one
    back out of the slug. Minting is attempted only for an event that
    actually appended (a lint-skipped event mints nothing) and is itself
    best-effort, never a reason to fail the batch or the record: a subject
    missing from person_names, a collection whose COLLECTION.json isn't
    `curation: "agent"` (person.CurationRefused), an invalid slug
    (ValueError), or a file that already exists (FileExistsError -- a
    person seen earlier in this same batch, or one a human already wrote by
    hand) all fall through to "minted": None rather than raising. Without
    collection_dir, minting is skipped entirely -- unchanged behavior for
    every existing caller.

    This says nothing about identity resolution -- docs/design/
    bulk-import.md Decision 4 still puts `folk lookup` before minting on the
    caller, upstream of the events and person_names this function receives;
    import_batch mints whatever subject it's handed, once, and trusts the
    caller already decided it was new.
    """
    vocab = vocab if vocab is not None else journal.load_vocab()
    person_names = person_names or {}
    minted_subjects = set()
    outcomes = []
    for event in events:
        src = event.get("src")
        try:
            appended = journal.append_event(root_path, writer, event, run_lint=True, vocab=vocab)
        except journal.LintError as ex:
            outcomes.append({"src": src, "status": "skipped", "event": None,
                              "reason": "; ".join(ex.errors), "minted": None})
            continue

        minted = None
        subject = event.get("s") or ""
        if collection_dir is not None and subject.startswith("person:") and subject not in minted_subjects:
            minted_subjects.add(subject)
            display_name = person_names.get(subject)
            if display_name:
                try:
                    fpath = person.create_person_file_as_agent(
                        collection_dir, subject.split(":", 1)[1], display_name)
                except (person.CurationRefused, FileExistsError, ValueError):
                    pass
                else:
                    minted = str(fpath)

        outcomes.append({"src": src, "status": "appended", "event": appended,
                          "reason": None, "minted": minted})
    return outcomes
