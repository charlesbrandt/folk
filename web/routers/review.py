"""Review queue GUI (docs/design/web-ui.md Decision 2e): a second front-end
to `folk review`'s exact queue, never a parallel mechanism. GET /review wraps
review.pending_items() unchanged. POST /review/action mirrors folk/cli.py's
cmd_review/_run_interactive_review accept/reject branches exactly, item type
by item type, so the same action taken here or at the terminal produces
byte-identical journal `review` events and person-file diffs (an explicit
web-ui.md exit criterion).

The containment rule (Decision 2e: "'Select all -> accept' is forbidden for
counterparty-sourced items by construction") is enforced by the request body
shape itself, not a check: ReviewAction.item is typed as a single object, so
there is no array-of-items code path to bypass in the first place. This
module never defines an endpoint that accepts a list of items.
"""
from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from folk import config
from folk import review as review_mod
from folk import triples

router = APIRouter()


@router.get("/review")
def get_review_queue():
    """review.pending_items(), reshaped only by attaching a computed-not-written
    diff preview to each bedrock item (review.preview_bedrock_edit -- read-only,
    writes nothing) so the UI can show the exact diff before a human accepts,
    the same "typist, not author" discipline `folk review --interactive`
    enforces by printing the diff before its [y/N] prompt."""
    roots = config.load_journal_roots()
    items = review_mod.pending_items(roots=roots)

    for item in items.get("bedrock", []):
        try:
            fpath, section, line, diff = review_mod.preview_bedrock_edit(item)
            item["preview"] = {"file": str(fpath), "section": section, "line": line, "diff": diff}
        except ValueError as e:
            item["preview"] = {"error": str(e)}

    for group in items.values():
        for item in group:
            item["description"] = review_mod.describe_item(item)

    return items


class ReviewAction(BaseModel):
    # A single item dict, exactly as returned inside one of GET /review's
    # four arrays (echoed back by the caller) -- never a list. This is the
    # structural half of the containment rule: the endpoint has no shape
    # that could accept more than one item per call.
    item: Dict[str, Any]
    verdict: Literal["accept", "reject"]


@router.post("/review/action")
def review_action(body: ReviewAction):
    item = dict(body.item)
    item_type = item.get("type")
    if item_type not in ("bedrock", "vocab", "entity", "lint_failure"):
        raise HTTPException(status_code=400, detail=f"unknown item type {item_type!r}")

    roots = config.load_journal_roots()

    # lint_failure: folk review's own CLI only ever offers [r]eject(discard)
    # for this item type (folk/cli.py's _run_interactive_review, lint_failure
    # branch) -- there is no accept action, and reject means discarding the
    # quarantine files, not a journal review event (the batch never entered
    # the journal, so there's nothing for a review event to resolve).
    if item_type == "lint_failure":
        if body.verdict != "reject":
            raise HTTPException(
                status_code=400,
                detail="lint_failure items can only be rejected (discarded) -- matches folk review's CLI, which offers no accept for this item type",
            )
        review_mod.discard_quarantine(item)
        return {"outcome": "discarded"}

    if body.verdict == "reject":
        review_mod.record_review(item, "reject", roots=roots)
        triples.index_rebuild()
        return {"outcome": "rejected"}

    # accept, branching on item type exactly like cmd_review's accept branch.
    if item_type == "vocab":
        review_mod.accept_vocab(item)
        review_mod.record_review(item, "accept", roots=roots)
        triples.index_rebuild()
        return {"outcome": "accepted"}

    if item_type == "entity":
        review_mod.accept_entity(item)
        review_mod.record_review(item, "accept", roots=roots)
        triples.index_rebuild()
        return {"outcome": "accepted"}

    # bedrock: the diff the caller saw (via GET /review's attached "preview")
    # is what they confirmed against -- recompute it fresh here rather than
    # trust anything the caller could have sent back, and apply only when
    # there's an actual change to make (mirrors the CLI's "(already present)"
    # no-op branch, which still records the accept without touching the file).
    try:
        fpath, section, line, diff = review_mod.preview_bedrock_edit(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if diff:
        review_mod.apply_bedrock_edit(fpath, section, line)
    review_mod.record_review(item, "accept", roots=roots)
    triples.index_rebuild()
    return {"outcome": "accepted", "diff": diff, "file": str(fpath)}
