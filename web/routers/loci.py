"""Locus endpoints: list, profile (docs/design/web-ui.md 2d's Map view reads
graph.py's /graph/locus/{slug} for its edges; this router's /loci/{slug}
supplies the Locus's own tiered profile the same way /people/{slug} does for
a person -- loci.md Decision 3: file curates cast, journal carries scope
tags, index derives the union, one rendering path for both entity kinds),
and /loci/{slug}/timeline (locus-scoped events sorted by date)."""
from fastapi import APIRouter, HTTPException

from folk import config, journal
from folk import locus as locus_mod

from serialize import tiered_index_json

router = APIRouter()


def _genius_loci(sections):
    """## Genius Loci is a locus-only free-text section (loci.md "What a
    Locus is") -- show_person/show_locus don't parse it as a named field
    (only archetype/voice are), so pull it the same way person._parse_free_text
    does: raw multi-line text under the heading, joined and stripped."""
    return "\n".join(sections.get("genius loci", [])).strip()


@router.get("/loci")
def list_loci():
    loci_roots = config.load_loci_roots()
    results = locus_mod.list_loci(loci_roots)
    return [
        {"slug": fpath.stem, "name": display_name, "collection": _root_collection(fpath, loci_roots)}
        for display_name, fpath in results
    ]


def _root_collection(fpath, loci_roots):
    """Which registered loci root (and therefore which collection) a Locus
    file came from -- list_loci() doesn't carry this through, so recover it
    by prefix match against the roots list, same containment check
    find_locus_file effectively does."""
    for root in loci_roots:
        try:
            fpath.relative_to(root["path"])
            return root["collection"]
        except ValueError:
            continue
    return None


@router.get("/loci/{slug}")
def get_locus(slug: str):
    bare_slug = slug[len("locus:"):] if slug.startswith("locus:") else slug
    loci_roots = config.load_loci_roots()
    fpath = locus_mod.find_locus_file(loci_roots, bare_slug)
    if not fpath:
        raise HTTPException(status_code=404, detail=f"'locus:{bare_slug}' not found")

    info = locus_mod.show_locus(fpath)
    locus_id = f"locus:{bare_slug}"
    grouped = journal.locus_profile(locus_id)

    return {
        "slug": bare_slug,
        "collection": _root_collection(fpath, loci_roots),
        "name": info["name"],
        "file": str(info["file"]),
        "genius_loci": _genius_loci(info["sections"]),
        "tags": info["tags"],
        "associations": info["associations"],
        "media": info["media"],
        "index": tiered_index_json(grouped),
    }


@router.get("/loci/{slug}/timeline")
def locus_timeline(slug: str):
    bare_slug = slug[len("locus:"):] if slug.startswith("locus:") else slug
    locus_id = f"locus:{bare_slug}"
    fpath = locus_mod.find_locus_file(config.load_loci_roots(), bare_slug)
    if not fpath:
        raise HTTPException(status_code=404, detail=f"'{locus_id}' not found")

    records = journal.locus_records(locus_id)
    # Timeline = dated events, not the (undated) curated cast edges the Map
    # view already covers -- a journal-sourced record always carries
    # last_reinforced (every indexable event requires ts, journal.py's lint);
    # `when` is the in-story/session date when the source adapter supplied
    # one, else last_reinforced (the mechanical observation time) is the
    # next best date to sort by.
    dated = [r for r in records if r.get("when") or r.get("last_reinforced")]
    dated.sort(key=lambda r: r.get("when") or r.get("last_reinforced") or "")
    return {"locus": locus_id, "events": dated}
