"""Attention ranking for the Home dashboard's Focus panel (docs/design/
web-ui.md 2a + Decision 3, the Focus Engine). Wraps folk.surface.focus()
with the same query-resolution logic folk/cli.py's cmd_focus uses for the
terminal: a --locus slug gets 'locus:' prefixed if missing, a --person
value is treated as a slug if already prefixed 'person:' else slugified
via graph.slugify -- mirrored here rather than passing raw query strings
straight through to focus(). No new ranking logic; the four-signal RRF
fusion is entirely surface.py's, reused unchanged. Pure read, no writes,
no LLM."""
from fastapi import APIRouter, Query

from folk import graph as graph_mod
from folk import surface

router = APIRouter()


@router.get("/focus")
def get_focus(
    locus: str = Query(None, description="Locus slug (with or without 'locus:') defining the focus set"),
    person: list[str] = Query(default=[], description="explicit participant (name or slug); repeatable"),
    collection: str = Query(None, description="restrict to containers with at least one triple in this collection"),
    budget: int = Query(surface.DEFAULT_BUDGET, description=f"max items to return (default {surface.DEFAULT_BUDGET})"),
):
    locus_id = None
    if locus:
        locus_id = locus if locus.startswith("locus:") else f"locus:{locus}"
    person_ids = [p if p.startswith("person:") else f"person:{graph_mod.slugify(p)}" for p in person]

    return surface.focus(locus_id=locus_id, person_ids=person_ids, collection=collection, budget=budget)
