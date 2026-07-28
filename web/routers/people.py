"""Single-person detail: docs/design/web-ui.md 2c, the Person page. The full
`journal.person_profile` tiered read model, merged with the file-derived
fields from `person.show_person` -- the same composition folk/cli.py's
cmd_show (lines 106-171) does for the terminal, JSON instead of printed
text, so a person page and `folk show <name>` can never disagree (the
exit criterion web-ui.md names for Decision 1's read model)."""
from fastapi import APIRouter, HTTPException, Query

from folk import config, journal, person

from serialize import tiered_index_json

router = APIRouter()


@router.get("/people/{slug}")
def get_person(slug: str, collection: str = Query(..., description="collection name, e.g. characters")):
    try:
        collection_dir, coll_name = config.resolve_collection_dir(collection_name=collection)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    fpath = person._find_person_file(collection_dir, slug)
    if not fpath:
        raise HTTPException(status_code=404, detail=f"'{slug}' not found in collection '{collection}'")

    info = person.show_person(fpath)
    person_id = f"person:{fpath.stem}"
    grouped = journal.person_profile(person_id)

    return {
        "slug": fpath.stem,
        "collection": coll_name,
        "name": info["name"],
        "file": str(info["file"]),
        "bio": info["bio"],
        "archetype": info["archetype"],
        "voice": info["voice"],
        "appearance": info["appearance"],
        "appearance_checkpoints": info["appearance_checkpoints"],
        "tags": info["tags"],
        "associations": info["associations"],
        "media": info["media"],
        "dates": info["dates"],
        "defining_moments": info["defining_moments"],
        "journal_file": str(info["journal"]) if info["journal"] else None,
        "index": tiered_index_json(grouped),
    }
