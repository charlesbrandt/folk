"""
folk web API -- run with: uvicorn api:app --reload (from this directory)

Entry point only: creates the FastAPI app, wires up CORS, and includes each
feature router (collections, people, graph, loci -- see routers/ for the
per-area split, mirroring digger's api.py -> routers/ convention described
in that project's module docstring).

This is a pure consumer of folk-the-library: it imports `folk` (the same
package the CLI ships, installed from ../pyproject.toml) in-process, per
docs/design/web-ui.md Decision 1. It reads person files, journal-derived
index records, and Locus files through folk's existing library functions.

Wave 1 (this file's original form) was read-only end to end. Wave 2 adds the
three sanctioned write paths (Decision 1): person-file edit -> staged diff ->
git commit -> index rebuild (routers/edit.py), and review-queue accept/reject
-> journal review event / person-file diff -> index rebuild (routers/review.py).
Nothing here writes the index directly (invariant 2) -- every write path ends
by calling folk.triples.index_rebuild(), the only thing that may.

Run against a folk collection that has had at least one `folk index
--rebuild` -- see README.md for the seeded characters/authors collections
this ships proofed against (zero personal data).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.collections import router as collections_router
from routers.people import router as people_router
from routers.graph import router as graph_router
from routers.loci import router as loci_router
from routers.agenda import router as agenda_router
from routers.focus import router as focus_router
from routers.review import router as review_router
from routers.edit import router as edit_router

app = FastAPI(title="folk web", version="0.1.0")

# Local-network, single-user, unauthenticated (docs/design/web-ui.md Decision
# 5) -- same posture as digger/transcript, wide open on purpose. This is a
# write surface (git commits, lint-gated journal appends) precisely because
# of that posture -- see Decision 5: not meant for exposure beyond the
# homelab network.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(collections_router)
app.include_router(people_router)
app.include_router(graph_router)
app.include_router(loci_router)
app.include_router(agenda_router)
app.include_router(focus_router)
app.include_router(review_router)
app.include_router(edit_router)


@app.get("/status")
def status():
    return {"status": "ok"}
