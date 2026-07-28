"""Shared JSON-shaping helpers used by more than one router.

Nothing here computes anything folk's library doesn't already compute --
these functions only reshape folk.journal's tiered-profile dicts and
folk.graph's edge tuples into the JSON the frontend consumes, the same way
folk/cli.py's _print_tiered_index and cmd_graph reshape them into text.
Keeping this reshaping in one place (rather than duplicated per router)
is what keeps a person page and a Locus page's tiered rendering identical.
"""
from datetime import datetime

from folk import journal


def tiered_index_json(grouped, now=None, vocab=None):
    """journal.person_profile()/journal.locus_profile()'s {tier: [records]}
    dict -> the JSON shape web/ui renders: current records per tier (each
    annotated with a read-time `staleness` the same way cli.py's
    _print_tiered_index computes it, via journal.staleness -- never written
    back, always recomputed), plus a flat superseded list rendered as its
    own collapsed section, exactly as folk show groups them.
    """
    now = now if now is not None else datetime.now()
    vocab = vocab if vocab is not None else journal.load_vocab()

    tiers = []
    superseded = []
    for tier in journal.TIER_ORDER:
        group = grouped.get(tier) or []
        current = [r for r in group if not r.get("superseded_by")]
        superseded.extend(r for r in group if r.get("superseded_by"))
        if not current:
            continue
        records = []
        for r in current:
            rec = dict(r)
            rec["staleness"] = journal.staleness(r, now, vocab)
            records.append(rec)
        tiers.append({"tier": tier, "label": journal.TIER_LABELS[tier], "records": records})

    return {"tiers": tiers, "superseded": superseded}


def entity_label(entity_id, person_index):
    """entity id ('person:toru-watanabe', 'work:norwegian-wood', 'tag:friend')
    -> a display label. Same logic as graph._label -- reimplemented here
    (rather than importing that underscore-prefixed helper across the
    folk-core/web boundary) so web/ stays a pure consumer of folk's public
    surface; folk.graph.ego_edges/locus_edges already return the edge list
    itself as plain tuples, which is the JSON data web-ui.md asks for, so
    nothing needed adding to graph.py for this pass.
    """
    kind, sep, slug = entity_id.partition(":")
    if sep and kind == "person" and slug in person_index:
        return person_index[slug]
    if sep:
        return slug.replace("-", " ").replace("_", " ").strip() or entity_id
    return entity_id


def edge_list_json(edges, person_index):
    """(s, p, o) tuples -> {"nodes": [...], "edges": [...]} for the Map view's
    graph library (Decision 1) -- the same edge list folk.graph.render_mermaid
    renders as text, structured as JSON instead.
    """
    from folk import graph as graph_mod

    nodes = graph_mod.nodes_from_edges(edges)
    return {
        "nodes": [{"id": n, "label": entity_label(n, person_index)} for n in sorted(nodes)],
        "edges": [
            {"source": s, "predicate": p, "target": o}
            for s, p, o in sorted(set(edges))
        ],
    }
