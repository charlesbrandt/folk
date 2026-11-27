"""Immich source adapter -- docs/design/immich-source.md.

Reads photo assets from an Immich server's v3 metadata search and turns the
named people, human-written descriptions, dates, and places on each asset
into mechanical `kind: observation` events under the actor `import:immich:v1`.

Same shape as folk/sources/directory_scrape.py: this is a bulk/mechanical
source, deliberately NOT registered in folk/sources/__init__.py's ADAPTERS
(that registry is the conversational transcript contract feeding the LLM
promotion pipeline). No LLM anywhere in this path, so the events earn the
observed trust tier (journal-schema.md "Source adapters").

Contract:

    fetch(cfg, request_fn=None, api_key=None, opener=None) -> list of raw asset dicts
    parse(raw_asset, ts, actor=ACTOR) -> list of observation event dicts
        (missing only `id`, which journal.append_event computes)
    person_names(raw_assets) -> {"person:<slug>": display name}, named people only
    existing_keys(journal_root) -> set of dedupe keys already in that root
    dedupe(events, existing) -> (fresh events, count of duplicates dropped)
    split_by_identity(events, near_by_slug) -> (kept events, held events)

Credentials: the API key is read from an env file (a `VAR=value` line, the
same shape ~/.config/homelab/*.env uses) or from the environment, sent only
in the `x-api-key` header, and never placed in any exception message, log
line, or return value. Errors from the HTTP layer are re-raised as
ImmichError with a status code or host only.

Immich v3 gotchas this module encodes (see the immich skill): GET
/api/albums/{id} no longer returns assets, so the search endpoint is the
only source; people come from asset.people[].name (unnamed clusters have an
empty or missing name and are ignored); the description lives at
asset.exifInfo.description; the date is asset.localDateTime; the place is
asset.exifInfo.city, falling back to exifInfo.country.
"""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from .. import journal
from ..slug import slugify

ACTOR = "import:immich:v1"
DEFAULT_KEY_VAR = "IMMICH_API_KEY"
DEFAULT_PAGE_SIZE = 250
SEARCH_PATH = "/api/search/metadata"
HTTP_TIMEOUT = 60

DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


class ImmichError(Exception):
    """An operational failure talking to Immich. Messages never contain the
    API key; they name a status code, a host, or a missing setting."""


# ----------------------------------------------------------------- config --

def load_api_key(env_file=None, var=DEFAULT_KEY_VAR, environ=None):
    """Return the API key from `env_file` (a `VAR=value` line) or, when no
    file is given, from the environment. Raises ImmichError naming the
    variable or file, never the value.
    """
    if env_file:
        path = Path(env_file).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            raise ImmichError(f"cannot read api key file {path}") from None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == var:
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
        raise ImmichError(f"no non-empty {var} line in {path}")
    environ = os.environ if environ is None else environ
    value = (environ.get(var) or "").strip()
    if not value:
        raise ImmichError(f"environment variable {var} is not set")
    return value


# ------------------------------------------------------------------ fetch --

def _default_request(url, body, api_key, opener=None):
    """POST a JSON body and return the decoded JSON response. `opener`
    defaults to urllib.request.urlopen; tests inject a fake one."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"x-api-key": api_key, "Content-Type": "application/json",
                 "Accept": "application/json"})
    opener = opener or urllib.request.urlopen
    try:
        with opener(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        raise ImmichError(f"Immich {SEARCH_PATH} returned HTTP {ex.code}") from None
    except urllib.error.URLError as ex:
        raise ImmichError(f"Immich server unreachable at {url.split('/api/')[0]}: {ex.reason}") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ImmichError(f"Immich {SEARCH_PATH} returned a non-JSON body") from None


def fetch(cfg, request_fn=None, api_key=None, opener=None):
    """Page through POST /api/search/metadata and return every IMAGE asset
    (with people and exif) as raw dicts.

    cfg keys: base_url (required), api_key_env_file (optional; else the
    environment), api_key_var (default IMMICH_API_KEY), page_size (default
    250), since (optional YYYY-MM-DD, assets taken on or after that date).

    request_fn(url, body, api_key) -> dict is the injection point for tests;
    the default posts with urllib. Pagination follows `assets.nextPage`
    and stops with an error if the server repeats a page, so a misbehaving
    server cannot loop forever.
    """
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise ImmichError("base_url is required")
    key = api_key if api_key is not None else load_api_key(
        cfg.get("api_key_env_file"), cfg.get("api_key_var") or DEFAULT_KEY_VAR)
    if request_fn is None:
        def request_fn(url, body, k):
            return _default_request(url, body, k, opener=opener)

    body = {"withPeople": True, "withExif": True, "type": "IMAGE",
            "size": int(cfg.get("page_size") or DEFAULT_PAGE_SIZE)}
    since = cfg.get("since")
    if since:
        try:
            date.fromisoformat(since)
        except (TypeError, ValueError):
            raise ImmichError("since must be YYYY-MM-DD") from None
        body["takenAfter"] = f"{since}T00:00:00.000Z"

    url = base + SEARCH_PATH
    assets, page, pages_seen = [], 1, set()
    while True:
        pages_seen.add(page)
        resp = request_fn(url, dict(body, page=page), key)
        block = resp.get("assets") if isinstance(resp, dict) else None
        if not isinstance(block, dict) or not isinstance(block.get("items"), list):
            raise ImmichError("unexpected search response shape (no assets.items list)")
        assets.extend(a for a in block["items"] if _is_live(a))
        nxt = block.get("nextPage")
        if nxt in (None, "", 0):
            break
        nxt = int(nxt)
        if nxt in pages_seen:
            raise ImmichError("Immich pagination repeated a page; stopping")
        page = nxt
    return assets


def _is_live(asset):
    """Immich's default search returns hidden/locked, trashed and offline
    assets (live survey, v3.4.2: ~21% of a 10k sample was hidden). They are
    not part of the curated timeline, so they are dropped client-side.
    Archived assets are kept: archiving is a timeline-decluttering choice,
    not a statement that the photo is not part of the story.
    """
    if not isinstance(asset, dict):
        return False
    if asset.get("visibility") in ("hidden", "locked"):
        return False
    return not (asset.get("isTrashed") or asset.get("isOffline"))


# ------------------------------------------------------------------ parse --

def named_people(raw_asset):
    """[(slug, display name)] for the asset's named people, deduplicated by
    slug, in the order Immich returns them. Unnamed face clusters (missing,
    empty, or whitespace-only name) and names that slugify to nothing are
    ignored -- they carry no identity folk can mint.
    """
    out, seen = [], set()
    for person in raw_asset.get("people") or []:
        name = ((person or {}).get("name") or "").strip()
        slug = slugify(name) if name else ""
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append((slug, name))
    return out


def _asset_date(raw_asset):
    m = DATE_PREFIX_RE.match(raw_asset.get("localDateTime") or "")
    return m.group(1) if m else None


def parse(raw_asset, ts, actor=ACTOR):
    """One raw Immich asset -> observation event dicts.

    Granularity (immich-source.md Decision 3): an asset produces events only
    when it has at least one named person AND (a human description OR two or
    more named people). A lone unannotated face is not worth a journal line.
    Events per emitted asset, in order:

      - pictured_with  person<->person, once per unordered pair, note=description
      - pictured_at    person -> locus:<place>, one per named person, when a place exists
      - described_in   person -> photo:<asset id>, note=description, one per named person

    Every event carries `when` (the local date) when Immich has one, and
    `src` = immich:asset:<id>, the drill-down pointer and dedupe identity.
    An asset with no named people yields []. A missing `id` raises KeyError
    (malformed; the caller counts it as a skip).
    """
    asset_id = raw_asset["id"]
    src = f"immich:asset:{asset_id}"
    exif = raw_asset.get("exifInfo") or {}
    description = " ".join(((exif.get("description") or "").split()))
    people = named_people(raw_asset)
    place_text = (exif.get("city") or "").strip() or (exif.get("country") or "").strip()
    if not people or (not description and len(people) < 2 and not place_text):
        return []

    when = _asset_date(raw_asset)
    place_slug = slugify(place_text) if place_text else ""
    photo_ref = f"photo:{slugify(asset_id)}"

    def event(s, p, o, **extra):
        e = {"v": 1, "ts": ts, "actor": actor, "kind": "observation",
             "s": s, "p": p, "o": o, "src": src}
        if when:
            e["when"] = when
        e.update(extra)
        return e

    events = []
    slugs = [slug for slug, _name in people]
    if len(slugs) >= 2:
        for i, a in enumerate(slugs):
            for b in slugs[i + 1:]:
                lo, hi = sorted((a, b))
                extra = {"note": description} if description else {}
                events.append(event(f"person:{lo}", "pictured_with", f"person:{hi}", **extra))
    if place_slug:
        for slug in slugs:
            events.append(event(f"person:{slug}", "pictured_at", f"locus:{place_slug}"))
    if description:
        for slug in slugs:
            events.append(event(f"person:{slug}", "described_in", photo_ref, note=description))
    return events


def person_names(raw_assets):
    """{"person:<slug>": display name} for every named person across the
    assets. The first display name seen for a slug wins, in fetch order.
    Used as bulk.import_batch's person_names, for minting.
    """
    names = {}
    for raw in raw_assets:
        for slug, name in named_people(raw):
            names.setdefault(f"person:{slug}", name)
    return names


def name_variants(raw_assets):
    """{"person:<slug>": sorted distinct display names} where more than one
    spelling folds to the same slug. Reported in the import summary, never
    resolved here -- two spellings are a human's call (identity-resolution.md).
    """
    variants = {}
    for raw in raw_assets:
        for person in raw.get("people") or []:
            name = ((person or {}).get("name") or "").strip()
            slug = slugify(name) if name else ""
            if slug:
                variants.setdefault(f"person:{slug}", set()).add(name)
    return {k: sorted(v) for k, v in variants.items() if len(v) > 1}


# ----------------------------------------------------------------- dedupe --

def dedupe_key(event):
    """Re-run identity: src + s/p/o + note. Keyed on the note too, so an
    edited Immich description appends a later observation instead of being
    silently dropped; an unchanged one is skipped on re-run. Keyed on more
    than `src` alone because one asset yields several events sharing a src.
    """
    return (event.get("src"), event.get("s"), event.get("p"), event.get("o"), event.get("note"))


def existing_keys(journal_root):
    """Dedupe keys of every ACTOR event already in journal_root's segments."""
    root = Path(journal_root)
    keys = set()
    if not root.is_dir():
        return keys
    for seg in sorted(root.glob("*.ndjson")):
        for e in journal.read_segment(seg):
            if e.get("actor") == ACTOR:
                keys.add(dedupe_key(e))
    return keys


def dedupe(events, existing):
    """(fresh events, duplicates dropped). Within-batch repeats count too
    (a page boundary can return the same asset twice)."""
    seen = set(existing)
    fresh, dropped = [], 0
    for e in events:
        key = dedupe_key(e)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        fresh.append(e)
    return fresh, dropped


# --------------------------------------------------------------- identity --

def split_by_identity(events, near_by_slug):
    """Hold back every event that references a person whose name had an
    unresolved near match (immich-source.md Decision 6). `near_by_slug` maps
    "person:<slug>" -> the candidates list. Returns (kept, held); an event
    is held if either its subject or its object is a flagged person.
    """
    kept, held = [], []
    for e in events:
        refs = {e.get("s"), e.get("o")}
        (held if refs & set(near_by_slug) else kept).append(e)
    return kept, held
