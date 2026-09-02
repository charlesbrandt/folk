"""folk graph -- Mermaid graph over the triple index.

v1 scope (docs/design/collections-and-graph.md): human-tier association
edges only. Edge collection takes a `tiers` filter parameter rather than
being rewritten later, so a --tier flag can add observed/stated/interpreted
tiers without touching this module's structure.
"""

import re
from collections import defaultdict
from pathlib import Path

from . import config
from . import journal as journal_mod
from . import triples as triples_mod
from .person import _person_files, _read_heading
from .slug import slugify

NODE_LIMIT = 75
DEFAULT_TIERS = ("human",)

_NODE_ID_RE = re.compile(r"[^a-zA-Z0-9_]")


def build_person_index():
    """slug -> display name, across every configured collection."""
    index = {}
    for _name, coll_dir in config.load_collections().items():
        coll_path = Path(coll_dir)
        if not coll_path.is_dir():
            continue
        for slug, fpath in _person_files(coll_path):
            index[slug] = _read_heading(fpath)
    return index


def find_person(name, threshold=0.6):
    """Does a person matching `name` already exist? -- the scriptable
    lookup source adapters need before minting a `person:{slug}` (ask 3,
    ~/repos/digger/docs/design/community-layer.md decision 2: "consult
    folk's index before minting; exact match reuses, ambiguous match must
    never be silently merged"). Checks every configured collection, not
    just the active one -- identity is collection-agnostic (collections are
    memberships, not identities, per decision 2).

    Returns {"query_slug": str, "match": {"slug","name"} | None,
    "near_matches": [{"slug","name"}, ...]}. `match` is set only on an
    exact slug or display-name match -- safe for a caller to reuse
    silently. `near_matches` uses the same token-overlap heuristic
    journal.lint_events_detailed() applies to promotion events at review
    time (journal-schema.md "Source adapters"), surfaced here so an adapter
    can flag ambiguity itself rather than only discovering it later in
    `folk review`; a near match is never something to auto-reuse or merge.
    """
    index = build_person_index()
    query_slug = slugify(name)

    if query_slug in index:
        return {"query_slug": query_slug, "match": {"slug": query_slug, "name": index[query_slug]}, "near_matches": []}
    for slug, display_name in index.items():
        if display_name.lower() == (name or "").lower():
            return {"query_slug": query_slug, "match": {"slug": slug, "name": display_name}, "near_matches": []}

    known_slugs = {f"person:{s}" for s in index}
    dup = journal_mod._near_duplicate(f"person:{query_slug}", known_slugs, threshold=threshold)
    near_matches = []
    if dup:
        dup_slug = dup.split(":", 1)[1]
        near_matches.append({"slug": dup_slug, "name": index.get(dup_slug, dup_slug)})
    return {"query_slug": query_slug, "match": None, "near_matches": near_matches}


def _label(entity_id, person_index):
    kind, sep, slug = entity_id.partition(":")
    if sep and kind == "person" and slug in person_index:
        return person_index[slug]
    if sep:
        return slug.replace("-", " ").replace("_", " ").strip() or entity_id
    return entity_id


def _node_id(entity_id):
    return _NODE_ID_RE.sub("_", entity_id)


def _all_edges(tiers=DEFAULT_TIERS):
    """(s, p, o, col) for every triple in the given tiers."""
    edges = []
    for t in triples_mod.query():
        if t.get("tier") not in tiers:
            continue
        s, p, o = t.get("s"), t.get("p"), t.get("o")
        if not (s and p and o):
            continue
        edges.append((s, p, o, t.get("col", "")))
    return edges


def collection_edges(col_name, tiers=DEFAULT_TIERS):
    """Edges written by person files in the given collection.

    Cross-collection edges (e.g. a character's appears_in a work whose
    author lives in a different collection) render automatically, because
    each side writes its own outbound edge scoped to its own collection --
    no special-casing needed here.
    """
    return sorted({(s, p, o) for s, p, o, col in _all_edges(tiers) if col == col_name})


def context_edges(tag, tiers=DEFAULT_TIERS):
    """Edges touching any person tagged `tag`."""
    all_edges = _all_edges(tiers)
    tag_id = f"tag:{tag}"
    tagged = {s for s, p, o, _col in all_edges if p == "tagged" and o == tag_id}
    return sorted({(s, p, o) for s, p, o, _col in all_edges if s in tagged or o in tagged})


def locus_edges(locus_id, tiers=DEFAULT_TIERS):
    """Edges inside a Locus's barrier, cast-list view (loci.md Decision 1):
    curated associations naming the Locus directly (s or o == locus_id).
    Locus-tagged journal events never surface here even though they're in
    scope for folk show/list -- they're never tier: human (only person
    files and Locus files write that tier), so the default tiers filter
    already keeps the ephemeral wormhole out of the cast list.
    """
    edges = []
    for t in triples_mod.query():
        if t.get("tier") not in tiers:
            continue
        s, p, o = t.get("s"), t.get("p"), t.get("o")
        if not (s and p and o):
            continue
        if s == locus_id or o == locus_id:
            edges.append((s, p, o))
    return sorted(set(edges))


def ego_edges(person_id, depth=2, tiers=DEFAULT_TIERS):
    """BFS out from person_id over undirected edges, up to `depth` hops."""
    all_edges = [(s, p, o) for s, p, o, _col in _all_edges(tiers)]
    adjacency = defaultdict(list)
    for s, p, o in all_edges:
        adjacency[s].append((o, s, p, o))
        adjacency[o].append((s, s, p, o))

    visited = {person_id}
    frontier = {person_id}
    included = set()
    for _ in range(depth):
        next_frontier = set()
        for node in frontier:
            for neighbor, s, p, o in adjacency.get(node, []):
                included.add((s, p, o))
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    return sorted(included)


def nodes_from_edges(edges):
    nodes = set()
    for s, _p, o in edges:
        nodes.add(s)
        nodes.add(o)
    return nodes


def render_mermaid(edges, person_index):
    nodes = nodes_from_edges(edges)
    lines = ["graph TD"]
    for n in sorted(nodes):
        lines.append(f'    {_node_id(n)}["{_label(n, person_index)}"]')
    for s, p, o in sorted(set(edges)):
        lines.append(f"    {_node_id(s)} -->|{p}| {_node_id(o)}")
    return "\n".join(lines) + "\n"
