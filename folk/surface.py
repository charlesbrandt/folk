"""folk surface -- cross-context relevance for session-start assembly
(docs/design/folk-surface.md, Phase 2). Given a focus set (a Locus's cast
plus any explicitly named participants), returns a bounded, ranked slice of
cross-context candidate triples: facts adjacent to the focus set but not
already part of it. No model call anywhere -- four deterministic rankers
(tier, recency, recurrence, gravity) over index triples, combined by
Reciprocal Rank Fusion (Decision 1). Read-only: this module only reads the
index, it never writes anything (Decision 3).
"""

from datetime import datetime

from . import journal as journal_mod

DEFAULT_BUDGET = 12
RRF_K = 60


def _focus_set(locus_id, person_ids, index_path):
    """Entities the session is about (Decision 2), and the triple keys
    already reachable inside that focus (never re-surfaced as candidates).

    entities maps entity_id -> origin_label, the focus anchor that pulled
    that entity into scope: the person's own id when named explicitly via
    --person, or the locus id when the entity was drawn in as a cast member
    / locus-tagged participant -- used to name "shared entity with ..." in
    a candidate's reason line without just restating the candidate's own
    subject. tag: entities are excluded from expansion -- they're the
    Locus's own classification metadata, not participants the session is
    "about".
    """
    entities = {}
    in_slice = set()

    for pid in person_ids:
        entities[pid] = pid

    if locus_id:
        for r in journal_mod.locus_records(locus_id, index_path=index_path):
            s, p, o = r.get("s"), r.get("p"), r.get("o")
            if not (s and p and o):
                continue
            in_slice.add((s, p, o))
            for entity in (s, o):
                if entity == locus_id or entity.startswith("tag:"):
                    continue
                entities.setdefault(entity, locus_id)

    return entities, in_slice


def _candidates(index_path, entities, in_slice):
    """Index triples that touch the focus set but aren't already in-slice --
    superseded and unresolved (candidate-tier) records never qualify.
    Returns a list of augmented triple dicts carrying a temporary "_far" (the
    non-focus endpoint, for the gravity ranker) and "_origin" (for the
    reason line), stripped again before output.
    """
    seen = set()
    out = []
    for r in journal_mod.load_index(index_path):
        s, p, o = r.get("s"), r.get("p"), r.get("o")
        if not (s and p and o):
            continue
        if r.get("tier") == "candidate" or r.get("superseded_by"):
            continue
        key = (s, p, o)
        if key in in_slice or key in seen:
            continue
        if s in entities:
            touch = s
        elif o in entities:
            touch = o
        else:
            continue
        seen.add(key)
        rec = dict(r)
        rec["_far"] = o if touch == s else s
        rec["_origin"] = entities[touch]
        out.append(rec)
    return out


def _degree_index(index_path):
    """entity -> number of non-candidate, non-superseded triples touching
    it, across the whole index -- entities many triples touch are pillars
    (Decision 1, ranker 4).
    """
    degree = {}
    for r in journal_mod.load_index(index_path):
        if r.get("tier") == "candidate" or r.get("superseded_by"):
            continue
        for entity in (r.get("s"), r.get("o")):
            if entity:
                degree[entity] = degree.get(entity, 0) + 1
    return degree


def _rank(records, score_fn, tiebreak=None):
    """1-based rank per record (best score = rank 1). Ties are broken by
    `tiebreak` ascending -- defaults to (s, p, o), surface()'s triples --
    every ranker must be a total order so RRF fusion is reproducible;
    Python's sort is stable, so sorting by the tiebreak first and then
    (stably) by score descending yields "score desc, then tiebreak asc"
    without needing to negate non-numeric scores. focus() passes an
    id-based tiebreak since containers have no (s, p, o) of their own.
    """
    tiebreak = tiebreak or (lambda r: (r["s"], r["p"], r["o"]))
    order = list(range(len(records)))
    order.sort(key=lambda i: tiebreak(records[i]))
    order.sort(key=lambda i: score_fn(records[i]), reverse=True)
    ranks = [0] * len(records)
    for pos, i in enumerate(order, 1):
        ranks[i] = pos
    return ranks


def _reason(r):
    parts = [r.get("tier", "")]
    count = r.get("reinforce_count")
    if count:
        parts.append(f"reinforced {count}×")
    last = r.get("last_reinforced")
    if last:
        parts.append(f"last {last[:10]}")
    origin = r.get("_origin")
    if origin:
        parts.append(f"shared entity with {origin}")
    return f"{r['s']} — {r['p']} {r['o']} ({', '.join(parts)})"


def surface(locus_id=None, person_ids=(), budget=DEFAULT_BUDGET, now=None, vocab=None, index_path=None):
    """The query: focus set in, bounded cross-context slice out (Decision 2).

    Returns a list of at most `budget` dicts (index-record fields plus a
    "reason" one-liner), ranked by RRF over the four deterministic rankers,
    with stale records (per journal.staleness) demoted to the bottom rather
    than excluded (Decision 1). Empty input -> empty output, never an error.
    `now`/`vocab`/`index_path` are all injectable so this is testable
    without touching the wall clock or the live vocab.json.
    """
    entities, in_slice = _focus_set(locus_id, set(person_ids), index_path)
    if not entities:
        return []

    candidates = _candidates(index_path, entities, in_slice)
    if not candidates:
        return []

    now = now if now is not None else datetime.now()
    vocab = vocab if vocab is not None else journal_mod.load_vocab()
    degree = _degree_index(index_path)

    tier_ranks = _rank(candidates, lambda r: journal_mod.TIER_RANK.get(r.get("tier"), -1))
    recency_ranks = _rank(candidates, lambda r: r.get("last_reinforced") or "")
    recurrence_ranks = _rank(candidates, lambda r: r.get("reinforce_count") or 0)
    gravity_ranks = _rank(candidates, lambda r: degree.get(r["_far"], 0))

    scores = [
        sum(1.0 / (RRF_K + ranks[i])
            for ranks in (tier_ranks, recency_ranks, recurrence_ranks, gravity_ranks))
        for i in range(len(candidates))
    ]

    order = list(range(len(candidates)))
    order.sort(key=lambda i: (candidates[i]["s"], candidates[i]["p"], candidates[i]["o"]))
    order.sort(key=lambda i: scores[i], reverse=True)
    ranked = [candidates[i] for i in order]

    # Stable partition: stale records move to the bottom without disturbing
    # RRF order within either group (Decision 1's "dropped to the bottom
    # rather than excluded").
    ranked.sort(key=lambda r: journal_mod.staleness(r, now, vocab) == "stale")

    result = []
    for r in ranked[:budget]:
        out = {k: v for k, v in r.items() if k not in ("_far", "_origin")}
        out["reason"] = _reason(r)
        result.append(out)
    return result


# ------------------------------------------------------------------ focus --
# folk focus (docs/design/web-ui.md Decision 3): "a thin second caller of
# this engine that ranks containers rather than triples." Same four
# rankers, same RRF fusion, same RRF_K -- no new signal is invented here.
# The unit being ranked is a container (person:*/locus:*), not a triple, so
# each ranker is redefined over per-container aggregates instead of
# per-triple fields, but the fusion machinery (_rank, RRF_K) is identical.

def _container_candidates(index_path):
    """Every person:*/locus:* id touching a non-candidate-tier,
    non-superseded index record, as subject or object -- same filter
    _degree_index already applies, reused here to build the per-container
    aggregates the four rankers score against: `tier` (the best/highest-
    trust tier among its own triples), `last_reinforced` (the most recent
    across its triples), and `reinforce_count` (summed across its triples).
    Degree itself (ranker 4, gravity) is _degree_index()'s existing count,
    looked up separately by focus() so it isn't duplicated here.
    """
    containers = {}
    for r in journal_mod.load_index(index_path):
        if r.get("tier") == "candidate" or r.get("superseded_by"):
            continue
        for entity in (r.get("s"), r.get("o")):
            if not entity or not (entity.startswith("person:") or entity.startswith("locus:")):
                continue
            c = containers.setdefault(entity, {"id": entity, "tier": None,
                                                 "last_reinforced": "", "reinforce_count": 0})
            rank = journal_mod.TIER_RANK.get(r.get("tier"), -1)
            if c["tier"] is None or rank > journal_mod.TIER_RANK.get(c["tier"], -1):
                c["tier"] = r.get("tier")
            last = r.get("last_reinforced") or ""
            if last > c["last_reinforced"]:
                c["last_reinforced"] = last
            c["reinforce_count"] += r.get("reinforce_count") or 0
    return containers


def _container_collections(index_path):
    """entity -> set of collection names ("col") of any triple touching it
    -- backs focus()'s --collection scope filter."""
    cols = {}
    for r in journal_mod.load_index(index_path):
        col = r.get("col")
        if not col:
            continue
        for entity in (r.get("s"), r.get("o")):
            if entity:
                cols.setdefault(entity, set()).add(col)
    return cols


def _scope_containers(containers, index_path, locus_id, person_ids, collection):
    """Optional --locus/--person/--collection narrowing, mirroring how
    cmd_surface resolves scope before calling surface() -- a convenience
    over ranking the whole index, not a new ranking signal. --locus
    restricts to that Locus's own id plus its cast/focus set (loci.md's
    barrier machinery, via _focus_set -- reused, not reimplemented).
    --person restricts to an explicit include-list of container ids.
    --collection restricts to containers with at least one triple recorded
    under that collection. Filters compose (AND) when more than one is given.
    """
    allowed = set(containers)
    if locus_id:
        entities, _in_slice = _focus_set(locus_id, set(), index_path)
        locus_allowed = {e for e in entities if e.startswith("person:") or e.startswith("locus:")}
        locus_allowed.add(locus_id)
        allowed &= locus_allowed
    if person_ids:
        allowed &= set(person_ids)
    if collection:
        cols = _container_collections(index_path)
        allowed &= {cid for cid in containers if collection in cols.get(cid, set())}
    return {cid: c for cid, c in containers.items() if cid in allowed}


def _container_reason(r, degree):
    parts = [r.get("tier") or ""]
    count = r.get("reinforce_count")
    if count:
        parts.append(f"reinforced {count}×")
    last = r.get("last_reinforced")
    if last:
        parts.append(f"last {last[:10]}")
    d = degree.get(r["id"], 0)
    if d:
        parts.append(f"{d} connections")
    return f"{r['id']} ({', '.join(p for p in parts if p)})"


def focus(locus_id=None, person_ids=(), collection=None, budget=DEFAULT_BUDGET, index_path=None):
    """folk focus -- the Focus Engine (docs/design/web-ui.md Decision 3): the
    same RRF query as surface(), reused to rank containers (people/loci
    worth attending to) rather than triples (facts to brief a session
    with). No new signals -- the same four rankers (tier, recency,
    recurrence, gravity) fused by the same RRF_K=60, over per-container
    aggregates instead of per-triple fields (see _container_candidates).
    Optionally scoped to a Locus's cast, an explicit set of containers, or
    a collection (_scope_containers); with none given, ranks across the
    whole index. Deterministic, no writes, no LLM: `index_path` is the only
    injectable dependency, same testing pattern as surface(). Returns at
    most `budget` dicts, `{"id", "tier", "reason"}`, ranked best first.
    Empty input -> empty output, never an error.
    """
    containers = _container_candidates(index_path)
    if locus_id or person_ids or collection:
        containers = _scope_containers(containers, index_path, locus_id, set(person_ids), collection)
    if not containers:
        return []

    records = sorted(containers.values(), key=lambda r: r["id"])
    degree = _degree_index(index_path)
    id_tiebreak = lambda r: (r["id"],)  # noqa: E731 -- containers have no (s, p, o) of their own

    tier_ranks = _rank(records, lambda r: journal_mod.TIER_RANK.get(r.get("tier"), -1), tiebreak=id_tiebreak)
    recency_ranks = _rank(records, lambda r: r.get("last_reinforced") or "", tiebreak=id_tiebreak)
    recurrence_ranks = _rank(records, lambda r: r.get("reinforce_count") or 0, tiebreak=id_tiebreak)
    gravity_ranks = _rank(records, lambda r: degree.get(r["id"], 0), tiebreak=id_tiebreak)

    scores = [
        sum(1.0 / (RRF_K + ranks[i])
            for ranks in (tier_ranks, recency_ranks, recurrence_ranks, gravity_ranks))
        for i in range(len(records))
    ]

    order = list(range(len(records)))
    order.sort(key=lambda i: records[i]["id"])
    order.sort(key=lambda i: scores[i], reverse=True)
    ranked = [records[i] for i in order]

    return [{"id": r["id"], "tier": r["tier"], "reason": _container_reason(r, degree)}
            for r in ranked[:budget]]
