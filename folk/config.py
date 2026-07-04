"""Configuration management for folk.

Collections are stored in ~/.config/folk/collections as a JSON mapping:
  {"personal": "~/people/personal", "work": "~/people/work"}

State is stored in ~/.config/folk/state as JSON:
  {"active_collection": "personal"}
"""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "folk"
COLLECTIONS_FILE = CONFIG_DIR / "collections"
STATE_FILE = CONFIG_DIR / "state"
JOURNAL_ROOTS_FILE = CONFIG_DIR / "journal-roots"
LOCI_ROOTS_FILE = CONFIG_DIR / "loci-roots"
VOCAB_FILE = CONFIG_DIR / "vocab.json"


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
    if explicit_dir:
        return Path(explicit_dir), explicit_dir

    if collection_name:
        collections = load_collections()
        if collection_name in collections:
            return Path(collections[collection_name]), collection_name
        raise ValueError(f"unknown collection: {collection_name}")

    env_dir = os.environ.get("FOLK_DIR")
    if env_dir:
        return Path(env_dir), os.path.basename(env_dir)

    state = load_state()
    active = state.get("active_collection")
    if active:
        collections = load_collections()
        if active in collections:
            return Path(collections[active]), active

    raise ValueError("no collection configured -- run 'folk context <name>' or set FOLK_DIR")


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
