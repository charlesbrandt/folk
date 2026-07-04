"""NDJSON triple index -- a derived, deletable cache.

Each line: {"s": "subject:id", "p": "predicate", "o": "object:id|string",
            "tier": "human|observed|stated|interpreted|candidate",
            "col": "collection-name", "src": "...", "when": "...",
            "last_reinforced": "...", "reinforce_count": N, "note": "...",
            "superseded_by": "event-id|human"}

`reinforce_count` and `superseded_by` are optional, rebuild-derived fields
added by decay-and-supersession.md (Decision 3 / Scope) -- present only on
journal-sourced triples that were re-observed or lost a functional-predicate
slot, respectively. Never written by anything but journal.rebuild_index().

Nothing writes this file directly (CLAUDE.md invariant 2) -- it is written
only by journal.rebuild_index(), which replays person files (human tier)
and journal segments (everything else). See folk/journal.py.
"""

from . import journal

DEFAULT_INDEX = journal.INDEX_PATH


def query(subject=None, predicate=None, obj=None, tier=None, col=None):
    """Query the index. Any parameter can be None to wildcard."""
    records = journal.load_index(DEFAULT_INDEX)
    results = []
    for t in records:
        if subject and t.get("s") != subject:
            continue
        if predicate and t.get("p") != predicate:
            continue
        if obj and t.get("o") != obj:
            continue
        if tier and t.get("tier") != tier:
            continue
        if col and t.get("col") != col:
            continue
        results.append(t)
    return results


def index_rebuild():
    """Replay all configured collections' person files + all registered journal
    roots into the index. Returns (n_triples, n_suggestions, n_superseded).
    """
    return journal.rebuild_index()


def verify(collection_dir):
    """Check for broken references in the triple index. Returns list of issues."""
    from pathlib import Path
    from . import config
    from .person import _person_files, _read_heading

    known_persons = {}
    for _name, coll_dir in config.load_collections().items():
        for slug, fpath in _person_files(Path(coll_dir)):
            known_persons[slug] = _read_heading(fpath)
    for slug, fpath in _person_files(collection_dir):
        known_persons[slug] = _read_heading(fpath)

    issues = []
    for t in query():
        target = t.get("o", "")
        if not target.startswith("person:"):
            continue
        target_slug = target[len("person:"):]
        if target_slug not in known_persons:
            issues.append(f"{t.get('s')} --{t.get('p')}--> {target}: no such person file")

    return issues
