"""Configuration management for folk.

Collections are stored in ~/.config/folk/collections as a JSON mapping:
  {"personal": "~/people/personal", "work": "~/people/work"}

State is stored in ~/.config/folk/state as JSON:
  {"active_collection": "personal"}

A collection may additionally describe itself with a COLLECTION.json file in
its own root directory (docs/design/collection-curation.md):
  {"curation": "agent"}
"""

import json
import os
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "folk"
COLLECTIONS_FILE = CONFIG_DIR / "collections"
STATE_FILE = CONFIG_DIR / "state"
JOURNAL_ROOTS_FILE = CONFIG_DIR / "journal-roots"
LOCI_ROOTS_FILE = CONFIG_DIR / "loci-roots"
VOCAB_FILE = CONFIG_DIR / "vocab.json"

COLLECTION_DESCRIPTOR_FILE = "COLLECTION.json"
CURATION_AGENT = "agent"
CURATION_HUMAN = "human"


class CollectionMissing(ValueError):
    """A collection was explicitly requested but its directory does not exist.

    An integrity error (the registry entry or path is out of date, or the repo
    isn't cloned here), distinct from the config error "unknown collection".
    Subclasses ValueError so existing CLI/web handlers report it and exit nonzero.
    (docs/design/collection-registry-integrity.md, Decision 2.)
    """


_WARNED_MISSING = set()


def warn_missing_collection(path):
    """Tolerant-mode notice: a registered collection directory is absent.

    Iterating every registered collection skips an absent one rather than
    failing, but says so on stderr (once per path per process); stdout stays
    clean so the tolerant path remains pipeable.
    """
    key = str(path)
    if key in _WARNED_MISSING:
        return
    _WARNED_MISSING.add(key)
    print(f"folk: warning: collection directory not found, skipping: {key}", file=sys.stderr)


def _require_dir(path, label):
    if not Path(path).is_dir():
        raise CollectionMissing(f"collection {label!r}: directory does not exist: {path}")


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _default_collections():
    return {}


def load_collections():
    ensure_config_dir()
    if not COLLECTIONS_FILE.exists():
        return _default_collections()
    try:
        data = json.loads(COLLECTIONS_FILE.read_text())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return _default_collections()


def save_collections(collections):
    ensure_config_dir()
    COLLECTIONS_FILE.write_text(json.dumps(collections, indent=2) + "\n")


def load_state():
    ensure_config_dir()
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state):
    ensure_config_dir()
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def resolve_collection_dir(collection_name=None, explicit_dir=None):
    """Resolve the single collection a command operates on.

    A collection named here was explicitly requested (-C, -d, $FOLK_DIR, or the
    active context), so a missing directory is a hard error (CollectionMissing),
    not "no residents". Iterate-all callers don't come through here; they skip
    absent collections with warn_missing_collection.
    """
    if explicit_dir:
        _require_dir(explicit_dir, explicit_dir)
        return Path(explicit_dir), explicit_dir

    if collection_name:
        collections = load_collections()
        if collection_name in collections:
            _require_dir(collections[collection_name], collection_name)
            return Path(collections[collection_name]), collection_name
        raise ValueError(f"unknown collection: {collection_name}")

    env_dir = os.environ.get("FOLK_DIR")
    if env_dir:
        _require_dir(env_dir, os.path.basename(env_dir))
        return Path(env_dir), os.path.basename(env_dir)

    state = load_state()
    active = state.get("active_collection")
    if active:
        collections = load_collections()
        if active in collections:
            _require_dir(collections[active], active)
            return Path(collections[active]), active

    raise ValueError("no collection configured -- run 'folk context <name>' or set FOLK_DIR")


def load_collection_descriptor(collection_dir):
    """Return a collection's own descriptor, read from COLLECTION.json in its
    root directory (docs/design/collection-curation.md).

    The only key this pass understands is `curation`, and the returned value is
    always already resolved to exactly "agent" or "human" -- never None, never
    anything else -- so no caller has to re-derive "was the file missing or
    malformed" for itself. **Fail closed:** absent file, unreadable file,
    malformed JSON, a non-object document, or any `curation` value other than
    the literal string "agent" all resolve to "human", which is today's
    behavior, unchanged, for every collection that does not opt in.

    A collection is config, never code (invariant 7): which collections are
    agent-curated is a fact stated on disk by the collection itself, and no
    collection name appears here.
    """
    path = Path(collection_dir) / COLLECTION_DESCRIPTOR_FILE
    data = None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
        data = None

    curation = data.get("curation") if isinstance(data, dict) else None
    if curation != CURATION_AGENT:
        curation = CURATION_HUMAN
    return {"curation": curation}


def load_journal_roots():
    """Return list of {"path": Path, "collection": name} for every registered journal root.

    Two registration mechanisms (journal-in-folk.md): (a) automatic — any
    configured collection directory that contains a journal/ subdirectory is
    a root scoped to that collection; (b) explicit —
    ~/.config/folk/journal-roots, a JSON list of {"path": ..., "collection": ...}
    for adapter-side roots that live next to their producer.
    """
    roots = []
    seen = set()

    for name, coll_dir in load_collections().items():
        candidate = Path(coll_dir) / "journal"
        if candidate.is_dir():
            key = str(candidate.resolve())
            if key not in seen:
                seen.add(key)
                roots.append({"path": candidate, "collection": name})

    if JOURNAL_ROOTS_FILE.exists():
        try:
            entries = json.loads(JOURNAL_ROOTS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            entries = []
        for entry in entries:
            path = Path(entry["path"])
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            roots.append({"path": path, "collection": entry["collection"]})

    return sorted(roots, key=lambda r: str(r["path"]))


def load_loci_roots():
    """Return list of {"path": Path, "collection": name} for every registered
    loci root. Near-literal copy of load_journal_roots() (loci.md Decision 4):
    the same two registration mechanisms -- automatic (a collection dir's
    loci/ subdirectory) and explicit (~/.config/folk/loci-roots) -- applied
    to Locus files instead of journal segments.
    """
    roots = []
    seen = set()

    for name, coll_dir in load_collections().items():
        candidate = Path(coll_dir) / "loci"
        if candidate.is_dir():
            key = str(candidate.resolve())
            if key not in seen:
                seen.add(key)
                roots.append({"path": candidate, "collection": name})

    if LOCI_ROOTS_FILE.exists():
        try:
            entries = json.loads(LOCI_ROOTS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            entries = []
        for entry in entries:
            path = Path(entry["path"])
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            roots.append({"path": path, "collection": entry["collection"]})

    return sorted(roots, key=lambda r: str(r["path"]))
