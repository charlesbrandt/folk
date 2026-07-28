"""Ego-graph edge lists as JSON -- the Map view (docs/design/web-ui.md 2d)
and a person page's association graph (2c). folk.graph.ego_edges/locus_edges
already return the same edge list folk/cli.py's cmd_graph (347-374) feeds to
render_mermaid; this router reshapes that list into {nodes, edges} JSON via
serialize.edge_list_json instead of Mermaid text -- no new data model, per
web-ui.md Decision 1's "the same edge list the backend already returns as
JSON, not a new data model."."""
from fastapi import APIRouter, HTTPException, Query

from folk import config
from folk import graph as graph_mod
from folk import locus as locus_mod

from serialize import edge_list_json

router = APIRouter()


@router.get("/graph/person/{slug}")
def graph_person(slug: str, depth: int = Query(2, ge=1, le=5)):
    person_id = slug if slug.startswith("person:") else f"person:{graph_mod.slugify(slug)}"
    person_index = graph_mod.build_person_index()
    bare_slug = person_id.split(":", 1)[1]
    if bare_slug not in person_index:
        raise HTTPException(status_code=404, detail=f"'{person_id}' not found")

    edges = graph_mod.ego_edges(person_id, depth=depth)
    if len(graph_mod.nodes_from_edges(edges)) > graph_mod.NODE_LIMIT:
        raise HTTPException(
            status_code=413,
            detail=f"graph would have more than {graph_mod.NODE_LIMIT} nodes -- narrow with a smaller depth",
        )
    return edge_list_json(edges, person_index)


@router.get("/graph/locus/{slug}")
def graph_locus(slug: str):
    bare_slug = slug[len("locus:"):] if slug.startswith("locus:") else slug
    locus_id = f"locus:{bare_slug}"
    fpath = locus_mod.find_locus_file(config.load_loci_roots(), bare_slug)
    if not fpath:
        raise HTTPException(status_code=404, detail=f"'{locus_id}' not found")

    person_index = graph_mod.build_person_index()
    edges = graph_mod.locus_edges(locus_id)
    return edge_list_json(edges, person_index)
