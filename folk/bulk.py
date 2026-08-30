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
"""

from . import journal


def import_batch(root_path, writer, events, vocab=None):
    """Append an iterable of already-shaped `kind: observation` event dicts
    to one journal root, one at a time, skip-and-report on a per-event lint
    failure rather than raising (docs/design/bulk-import.md Decision 1).

    Returns a list of outcome dicts, one per input event, in input order:
      {"src": event.get("src"), "status": "appended" | "skipped",
       "event": <appended event with id/v filled in> | None,
       "reason": <lint error text> | None}

    journal.append_event's lint is unchanged and still runs per event
    (invariant 6) -- this wraps its LintError, it does not loosen it. A
    non-lint exception (e.g. an unwritable root_path) is not caught here
    and propagates, since that is an operational failure affecting the
    whole batch, not a single record's data quality.
    """
    vocab = vocab if vocab is not None else journal.load_vocab()
    outcomes = []
    for event in events:
        src = event.get("src")
        try:
            appended = journal.append_event(root_path, writer, event, run_lint=True, vocab=vocab)
        except journal.LintError as ex:
            outcomes.append({"src": src, "status": "skipped", "event": None,
                              "reason": "; ".join(ex.errors)})
        else:
            outcomes.append({"src": src, "status": "appended", "event": appended, "reason": None})
    return outcomes
