"""Template/example bulk-import adapter for a scraped public directory (an
org chart, an employee directory, a lab roster) -- docs/design/
bulk-import.md.

This is deliberately NOT one of the pluggable transcript source adapters
registered in this package's __init__.py ADAPTERS dict, and is intentionally
left out of that registry: __init__.py's discover/mtime/load contract is for
conversational transcript sources that feed the LLM promotion pipeline
(folk/promotion.py). A bulk directory import is a different shape entirely
(journal-schema.md's "Source adapters" section): no LLM anywhere in its
path, kind: observation events only, no session/conversation field, and no
promotion/review-queue involvement -- events go straight through
journal.append_event's own lint. See folk/bulk.py for the batch runner that
wraps repeated calls to append_event with skip-and-report semantics.

Contract a real bulk-import adapter implements:

    fetch(profile_cfg) -> list of raw record dicts, adapter-specific shape
    parse(raw_record, ts, actor=ACTOR) -> list of kind: observation event
        dicts, missing only `id` (journal.append_event computes and lints
        that at append time)

fetch() is a documented stub here on purpose: actually reaching a real site
needs an HTTP client and (usually) an HTML or JSON parser, folk is
stdlib-only (CLAUDE.md invariant 8), and this repo has no maintainer sign-off
to add either dependency. Wiring up a live fetch is the extension point a
real deployment supplies for itself.

parse() is real and tested: given one already-fetched raw record shaped like
{"name": ..., "title": ..., "department": ..., "profile_url": ...}, it
produces well-formed observation events with a correctly namespaced `src`
pointer and a locus:<slug> target for the organizational edge (docs/design/
locus-type.md: the org gets a real, showable, taggable file, rather than an
unaddressable bare "org:<slug>" association string).

What a real deployment still has to supply:
  - an actual HTTP fetch (or local file read, if scraping via an export)
    inside fetch(), with whatever pagination/auth/rate-limiting the real
    site needs
  - actual field extraction from the real HTML/JSON shape the real site
    returns -- the raw_record shape here is illustrative, not a contract
    any real site follows
  - a `folk lookup "<name>" --json` check (folk/graph.py's find_person)
    before minting a new person:<slug> for a name this hasn't seen before --
    this skeleton's parse() always mints from the record's own name; a real
    caller runs that check itself, upstream of calling parse(), per
    docs/design/bulk-import.md's identity-resolution guidance (Decision 4)
  - vocab.json registration for whatever predicates/types it writes
    (works_at, holds_title, the "title" and "locus" types) before the first
    real run (journal-schema.md's "Source adapters" registration commitment)
  - minting the locus:<slug> department/org files themselves -- that is a
    human/file-authoring step (person and Locus files are Bedrock, human
    tier), not something this module or import_batch() does; see
    docs/design/bulk-import.md's worked example
"""

from ..slug import slugify

ACTOR = "import:directory-scrape:v1"


def fetch(profile_cfg):
    """Stub. A real adapter fetches raw records from profile_cfg (e.g. a
    base URL, page size, auth) and returns a list of raw record dicts.
    Not implemented here -- see the module docstring.
    """
    raise NotImplementedError(
        "fetch() is a template stub -- a real deployment supplies its own "
        "HTTP/HTML or JSON extraction here (see module docstring)"
    )


def _slug(text):
    """Lowercase-hyphen slug from free text, via the same folk.slug.slugify()
    used for person display names -- department/org names and title strings
    go through it too, so a punctuation-bearing string (credentials riding
    along in a name, "Radiation Oncology, Practice") produces the same
    well-formed slug journal.append_event's lint requires. A prior local
    reimplementation only collapsed whitespace and left other punctuation
    (commas, parens) in place, producing malformed slugs that failed lint
    on every event.
    """
    return slugify(text or "")


def parse(raw_record, ts, actor=ACTOR):
    """One raw scraped record -> a list of kind: observation event dicts.

    Expected raw_record shape (illustrative -- not any real site's actual
    shape): {"name": str, "title": str, "department": str,
    "profile_url": str}. "title" and "department" are optional -- an empty
    or missing field is absent data, not a malformed record, so parse()
    simply omits the corresponding event rather than emitting a bad one.
    A record missing "name" is malformed and raises KeyError, which a
    caller's loop (or folk/bulk.py's import_batch, for the events that do
    get built) is expected to treat as a skip alongside a lint-time one.
    """
    name = raw_record["name"]
    person_slug = f"person:{_slug(name)}"
    src_base = f"directory-scrape:profile:{raw_record.get('profile_url') or _slug(name)}"

    events = []
    title = raw_record.get("title")
    if title:
        events.append({
            "v": 1, "ts": ts, "actor": actor, "kind": "observation",
            "s": person_slug, "p": "holds_title", "o": f"title:{_slug(title)}",
            "note": title,
            "src": f"{src_base}#title",
        })
    department = raw_record.get("department")
    if department:
        events.append({
            "v": 1, "ts": ts, "actor": actor, "kind": "observation",
            "s": person_slug, "p": "works_at", "o": f"locus:{_slug(department)}",
            "src": f"{src_base}#department",
        })
    return events
