"""Upcoming dated events across collections (docs/design/web-ui.md 2a's Home
region, "Upcoming reminders" -- the flagship "don't forget the birthday"
view). Wraps folk.agenda.upcoming() with the same collection-resolution
logic folk/cli.py's cmd_agenda uses for the terminal: an explicit collection
scans just that one directory, omitting it scans every configured
collection. `now` is only ever read at this HTTP boundary and passed in --
upcoming() itself never touches the wall clock, the same discipline
journal.staleness/surface.surface hold. Pure read, no writes, no LLM."""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from folk import agenda as agenda_mod
from folk import config

router = APIRouter()


def _collection_for_file(file_path, dir_to_name):
    """Which configured collection a person file belongs to, by prefix
    match against the directories scanned -- the same pattern
    routers/loci.py's _root_collection uses to recover a collection name
    that upcoming()'s return shape doesn't carry. Needed so the dashboard
    can link a reminder row to that person's page (Person.svelte's route
    requires a collection name, not just a slug)."""
    fpath = Path(file_path)
    for coll_dir, name in dir_to_name.items():
        try:
            fpath.relative_to(coll_dir)
            return name
        except ValueError:
            continue
    return None


@router.get("/agenda")
def get_agenda(
    within: int = Query(30, description="look-ahead window in days (default 30)"),
    collection: str = Query(None, description="restrict to this collection; omit to scan every configured collection"),
    now: str = Query(None, description="ISO date/datetime override, for reproducibility/testing"),
):
    if collection:
        try:
            collection_dir, coll_name = config.resolve_collection_dir(collection_name=collection)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        collection_dirs = [collection_dir]
        dir_to_name = {collection_dir: coll_name}
    else:
        all_collections = config.load_collections()
        dir_to_name = {Path(p): name for name, p in all_collections.items()}
        collection_dirs = list(dir_to_name.keys())

    now_dt = None
    if now:
        try:
            now_dt = datetime.fromisoformat(now)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid 'now' ISO timestamp: {now!r}")

    items = agenda_mod.upcoming(collection_dirs, within_days=within, now=now_dt)
    for it in items:
        it["collection"] = _collection_for_file(it["file"], dir_to_name)
    return items
