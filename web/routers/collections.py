"""Collection listing and the people grid (docs/design/web-ui.md 2b, the
Collection browser). GET /people lives here rather than in routers/people.py
because it's the collection-scoped list ("browse collection X, filter by
tag Y") -- routers/people.py owns the single-person detail endpoint."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from folk import config, person

router = APIRouter()


@router.get("/collections")
def list_collections():
    """Every collection folk knows about -- config.load_collections() is a
    name -> directory mapping, no other authority (invariant 7: collections
    are config, never code)."""
    collections = config.load_collections()
    return [
        {"name": name, "dir": str(coll_dir)}
        for name, coll_dir in sorted(collections.items())
    ]


@router.get("/people")
def list_people(
    collection: str = Query(..., description="collection name, e.g. characters"),
    tag: Optional[str] = Query(None, description="filter to people carrying this tag"),
):
    """The people grid -- wraps person.list_persons exactly as `folk list
    --context` does, JSON instead of printed lines."""
    try:
        collection_dir, name = config.resolve_collection_dir(collection_name=collection)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not collection_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"collection directory not found: {collection_dir}")

    people = person.list_persons(collection_dir, context_tag=tag)
    return [
        {"slug": fpath.stem, "name": display_name, "collection": name}
        for display_name, fpath in people
    ]
