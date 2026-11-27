"""Person file operations.

Person files live in collection directories with the structure:
  {collection}/{initial}/{slug}/{slug}.md

Currently they're free-form markdown. This module adds conventions
on top: ## Associations, ## Tags, ## Media sections that folk commands
manage.
"""

import hashlib
import random
import re
from pathlib import Path

from . import config

# Unicode-aware (Python 3's \w already matches any script's letters/digits
# plus underscore, not just ASCII) so a slug from graph.slugify() -- which
# preserves non-Latin glyphs that survive NFKD folding intact rather than
# stripping them, docs/design/collection-curation.md -- validates the same
# way it's generated. The `(?!_)` keeps the existing rule that a slug may
# not *start* with underscore; underscore stays allowed mid-slug.
PERSON_FILE = re.compile(r"^(?!_)\w[\w-]*\.md$")
SLUG_RE = re.compile(r"^(?!_)\w[\w-]*$")
HEADING_RE = re.compile(r"^#\s+(.+)$")
SECTION_RE = re.compile(r"^##\s+(.+)$")
ASSOC_ENTRY_RE = re.compile(r"^-\s+\[(.+?)\](?:\(([^)]*)\))?\s*[—–-]?\s*(.+)$")
# An association href of the form "type:slug" (e.g. "work:norwegian-wood").
# The type prefix (before the colon) is folk's own vocabulary, always
# ASCII-lowercase; the slug half follows the same unicode-aware rule as
# SLUG_RE above.
TYPED_REF_RE = re.compile(r"^[a-z][a-z0-9_]*:(?!_)\w[\w-]*$")
TAG_LINE_RE = re.compile(r"^([a-zA-Z0-9_-]+(?:\s+[a-zA-Z0-9_-]+)*)$")
MEDIA_ENTRY_RE = re.compile(r"^-\s+(.+?)\s*[—–-]\s*(.+)$")
# "- birthday: 03-14" or "- anniversary: 2019-06-02" -- month-day required,
# year optional (docs/design/web-ui.md Decision 4).
DATE_ENTRY_RE = re.compile(r"^-\s+(.+?):\s*(?:(\d{4})-)?(\d{2}-\d{2})\s*$")
# "- build: tall, narrow through the shoulders" (docs/design/appearance.md
# Decision 2). The label is a short display key -- letters/digits/space/
# _-/ only, <= 40 chars -- deliberately NOT validated against a list of
# allowed labels: no label name may appear in folk's code (Decision 2).
APPEARANCE_ENTRY_RE = re.compile(r"^-\s+([A-Za-z][A-Za-z0-9 _/-]{0,39}?):\s*(.+)$")
# "## Appearance: <checkpoint>" -- a generic heading-suffix split, any
# "## Name: qualifier" heading (docs/design/appearance-checkpoints.md Decision 2,
# open question 1: parse this now as a reusable convention, not an
# Appearance-only one, so a second consumer like "## Voice: <checkpoint>"
# needs no parser rework). Matched against an already-lowercased section
# key from _parse_sections.
SECTION_QUALIFIER_RE = re.compile(r"^(.+?)\s*:\s*(.+)$")


EXCLUDED_DIRS = frozenset({"meta", "person-template", ".git", "__pycache__", "loci"})
EXCLUDED_FILES = frozenset({"about.md", "index.md", "instances-people.md", "journal-nuc.md", "todo.md", "prompts.md", "processing.log", "convert_to_slug.py", "rename-as-clipboard.sh"})


def _person_files(collection_dir):
    """Yield (slug, filepath) for every person file in a collection.

    Directory structure: {collection}/{initial}/{slug}/{slug}.md

    A missing collection_dir yields nothing and warns on stderr (once per
    path): this is the tolerant iterate-all path, so one registered collection
    that is absent on this machine doesn't break every command that sweeps all
    collections (agenda.upcoming, rebuild, graph). A collection the caller
    explicitly requested never reaches here missing -- config.resolve_collection_dir
    raises CollectionMissing first (docs/design/collection-registry-integrity.md,
    Decision 2).
    """
    if not collection_dir.is_dir():
        config.warn_missing_collection(collection_dir)
        return
    for entry in sorted(collection_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in EXCLUDED_DIRS:
            continue
        for slug_dir in sorted(entry.iterdir()):
            if not slug_dir.is_dir():
                continue
            for f in sorted(slug_dir.iterdir()):
                if f.name in EXCLUDED_FILES:
                    continue
                if f.name.endswith("-journal.md"):
                    continue
                if PERSON_FILE.match(f.name):
                    slug = f.stem
                    yield slug, f


def _read_heading(filepath):
    """Return the first # heading text, or the filename stem."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        m = HEADING_RE.match(line)
        if m:
            return m.group(1).strip()
    return filepath.stem


def _parse_sections(content):
    """Split content into {section_name: body_lines} including __main__."""
    lines = content.splitlines()
    sections = {}
    current = "__main__"
    current_lines = []
    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            sections[current] = current_lines
            current = m.group(1).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)
    sections[current] = current_lines
    return sections


def _build_content(sections, first_line_is_h1=True):
    """Reassemble sections back into markdown."""
    parts = []
    main_lines = sections.get("__main__", [])
    if main_lines:
        parts.append("\n".join(main_lines).strip())

    for name, lines in sections.items():
        if name == "__main__":
            continue
        section_text = "\n".join(lines).strip()
        if section_text:
            block = f"\n## {name.title()}\n{section_text}"
        else:
            block = f"\n## {name.title()}"
        parts.append(block)

    return "\n".join(parts) + "\n"


def _find_person_file(collection_dir, name):
    """Find a person file by name (matching heading or filename). Return Path or None."""
    name_lower = name.lower().replace(" ", "-").replace("_", "-")
    for slug, fpath in _person_files(collection_dir):
        if slug.lower().replace("_", "-") == name_lower:
            return fpath
        heading = _read_heading(fpath)
        if heading.lower() == name.lower():
            return fpath
    for slug, fpath in _person_files(collection_dir):
        if name_lower in slug.lower() or name_lower in _read_heading(fpath).lower():
            return fpath
    return None


def list_persons(collection_dir, context_tag=None):
    """Return list of (display_name, filepath) for people in a collection."""
    results = []
    for slug, fpath in _person_files(collection_dir):
        name = _read_heading(fpath)
        if context_tag:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            sections = _parse_sections(content)
            tags = _parse_tags(sections)
            if context_tag not in tags:
                continue
        results.append((name, fpath))
    return results


def show_person(fpath):
    """Parse and return a structured representation of a person file.

    Returns dict with name, file, content, sections, bio, archetype, voice,
    tags, associations, media, defining_moments. Also carries `locus_type`
    (docs/design/locus-type.md), a single free-text value under
    `## Locus Type` -- parsed the same way as archetype/voice, empty string
    when absent. Meaningful only on a Locus file (`show_locus` delegates
    here, per docs/design/loci.md); an ordinary person file will simply
    never have this section, the same way a Locus rarely has ## Archetype.
    """
    content = fpath.read_text(encoding="utf-8", errors="replace")
    name = _read_heading(fpath)
    sections = _parse_sections(content)
    other_files = list(fpath.parent.glob("*.md"))
    journal = None
    for f in other_files:
        if f.name.endswith("-journal.md"):
            journal = f
            break

    return {
        "name": name,
        "file": fpath,
        "content": content,
        "sections": sections,
        "bio": _parse_bio(sections),
        "archetype": _parse_free_text(sections, "archetype"),
        "voice": _parse_free_text(sections, "voice"),
        "locus_type": _parse_free_text(sections, "locus type"),
        "tags": _parse_tags(sections),
        "appearance": _parse_appearance(sections),
        "appearance_checkpoints": _parse_appearance_checkpoints(sections),
        "associations": _parse_associations(sections),
        "media": _parse_media(sections),
        "dates": _parse_dates(sections),
        "defining_moments": _parse_defining_moments(sections),
        "journal": journal,
    }


def _parse_bio(sections):
    """Body text before the first ## heading, excluding the # H1 line itself."""
    main_lines = sections.get("__main__", [])
    body = [l for l in main_lines if not HEADING_RE.match(l)]
    return "\n".join(body).strip()


def _parse_free_text(sections, key):
    """Raw multi-line text under a `##` heading (## Archetype, ## Voice)."""
    return "\n".join(sections.get(key, [])).strip()


def _parse_defining_moments(sections):
    lines = sections.get("defining moments", [])
    results = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        results.append(stripped.lstrip("- ").strip())
    return results


def _parse_tags(sections):
    tags_section = sections.get("tags", [])
    for line in tags_section:
        stripped = line.strip()
        if stripped and not stripped.startswith("-"):
            return stripped.split()
    return []


def _parse_associations(sections):
    assocs = sections.get("associations", [])
    results = []
    for line in assocs:
        m = ASSOC_ENTRY_RE.match(line)
        if m:
            name, href, rel = m.group(1).strip(), m.group(2), m.group(3).strip()
            ref = href.strip() if href and TYPED_REF_RE.match(href.strip()) else None
            results.append({"name": name, "type": rel, "ref": ref})
        else:
            stripped = line.strip().lstrip("- ")
            if stripped:
                results.append({"name": stripped, "type": "", "ref": None})
    return results


def _parse_media(sections):
    media_lines = sections.get("media", [])
    results = []
    for line in media_lines:
        m = MEDIA_ENTRY_RE.match(line)
        if m:
            results.append({"ref": m.group(1).strip(), "note": m.group(2).strip() if m.group(2) else ""})
    return results


def _parse_dates(sections):
    """Parse `## Dates` (birthday, anniversary, "met on", ...) -- a Bedrock,
    human-curated section (docs/design/web-ui.md Decision 4), same parsing
    convention as ## Tags/## Media: one `- label: MM-DD` or
    `- label: YYYY-MM-DD` per line (year optional -- most recurring dates
    like birthdays are month-day only). Malformed lines are silently
    skipped, the same tolerance _parse_media already gives a non-matching
    line. Returns a list of {"label", "month_day", "year"} dicts,
    JSON-serializable as-is -- this is what folk/agenda.py's upcoming()
    rolls forward against an injected `now`.
    """
    date_lines = sections.get("dates", [])
    results = []
    for line in date_lines:
        m = DATE_ENTRY_RE.match(line.strip())
        if not m:
            continue
        label, year, month_day = m.group(1).strip(), m.group(2), m.group(3)
        results.append({"label": label, "month_day": month_day, "year": int(year) if year else None})
    return results


def _parse_appearance_lines(lines):
    """Parse a list of `- label: value` lines (docs/design/appearance.md
    Decision 2) into {"labels": [{"label", "value"}, ...], "note": str} --
    always both keys, never None, JSON-serializable as-is. Shared by the base
    `## Appearance` section and every `## Appearance: <name>` checkpoint
    section (docs/design/appearance-checkpoints.md), since both use
    identical line syntax.

    One `- label: value` per line, order-preserving. The label set is open:
    folk never validates against a list of allowed labels, and no label name
    appears anywhere in folk's code -- invariant 7's reasoning one level down,
    since the alternative is folk appointing itself the owner of a taxonomy of
    bodies. The consumer decides which labels it reads.

    Tolerant in the way _parse_media already is: a line that isn't
    `- label: value` is not an error, it joins the free-text `note` in file
    order, so a section someone wrote as a paragraph still round-trips and
    still reaches consumers -- it just isn't addressable by field until
    someone labels it. (A prose line that happens to contain a colon may be
    read as a label; that mislabels nothing that matters, since the content
    survives verbatim into appearance_text either way.)
    """
    labels = []
    note_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        m = APPEARANCE_ENTRY_RE.match(stripped)
        if m:
            labels.append({"label": m.group(1).strip(), "value": m.group(2).strip()})
        else:
            note_lines.append(stripped.lstrip("- ").strip())
    return {"labels": labels, "note": "\n".join(note_lines).strip()}


def _parse_appearance(sections):
    """Parse the base `## Appearance` section. See _parse_appearance_lines."""
    return _parse_appearance_lines(sections.get("appearance", []))


def _section_qualifiers(sections, base):
    """Every `## {base}: <name>` section's raw lines, keyed by qualifier
    name, in file order -- the generic heading-suffix split (docs/design/
    appearance-checkpoints.md Decision 2), scoped to one base section name so
    it can be reused for a future `## Voice: <checkpoint>` without rework.
    folk never enumerates checkpoint names (Decision 3): this only reports
    whichever qualifiers exist in the file, in the order they appear --
    `sections` is itself insertion-ordered (_parse_sections), so no sort is
    needed or performed.
    """
    result = {}
    for key, lines in sections.items():
        if key == base:
            continue
        m = SECTION_QUALIFIER_RE.match(key)
        if m and m.group(1).strip() == base:
            result[m.group(2).strip()] = lines
    return result


def _parse_appearance_checkpoints(sections):
    """Parse every `## Appearance: <name>` section (docs/design/
    appearance-checkpoints.md Decision 2), in file order. Returns
    {name: {"labels", "note"}} -- each checkpoint's own content in isolation,
    not merged with the base here (that's merge_appearance_checkpoint's job,
    called by render at selection time), so a bare parse is what `folk show`
    lists as available checkpoint names.
    """
    return {
        name: _parse_appearance_lines(lines)
        for name, lines in _section_qualifiers(sections, "appearance").items()
    }


def merge_appearance_checkpoint(appearance, checkpoint):
    """Merge one checkpoint's parsed section over the base `## Appearance`
    section (docs/design/appearance-checkpoints.md Decision 2): base labels
    first in file order; a label the checkpoint also states overrides the
    base value in place, keeping the base's position; a label new to the
    checkpoint appends in the checkpoint's own file order. Notes concatenate,
    base then checkpoint. Pure and order-preserving -- no sorting, no set
    arithmetic, the same determinism discipline as every other render path.
    """
    labels = [dict(item) for item in appearance["labels"]]
    index_by_label = {item["label"]: i for i, item in enumerate(labels)}
    for item in checkpoint["labels"]:
        if item["label"] in index_by_label:
            labels[index_by_label[item["label"]]] = dict(item)
        else:
            labels.append(dict(item))
            index_by_label[item["label"]] = len(labels) - 1
    note = "\n".join(part for part in (appearance["note"], checkpoint["note"]) if part)
    return {"labels": labels, "note": note}


def appearance_text(appearance):
    """Flatten a parsed appearance into the one-line brief consumers fold into
    a prompt (docs/design/appearance.md Decision 4).

    Labeled pairs as `label: value`, joined with `; `, then the free-text note
    appended as its own clause. Empty when there is nothing to say -- never
    None. Deterministic, and deliberately the *only* implementation: a
    consumer that invents its own join drifts from every other consumer's,
    which is the failure this whole section exists to prevent.
    """
    clauses = [f"{item['label']}: {item['value']}" for item in appearance["labels"]]
    if appearance["note"]:
        clauses.append(appearance["note"])
    return "; ".join(clauses)


def appearance_fingerprint(appearance):
    """Short stable hash of the flattened brief -- first 12 hex chars of
    sha256, the same width and construction journal event ids use.

    This is what a render adapter records in its observation event's `note`
    (docs/design/appearance.md Decision 9), so a graded render can be
    attributed to the exact version of the brief that produced it. Exposed
    here rather than left to the adapter for the same reason appearance_text
    is: one implementation, no drift. Empty brief -> empty fingerprint, so an
    undescribed figure is distinguishable from a described one rather than
    hashing to a constant.
    """
    text = appearance_text(appearance)
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def add_association(collection_dir, name_a, name_b, link_type):
    """Add bidirectional link between two persons. Returns message string."""
    fa = _find_person_file(collection_dir, name_a)
    fb = _find_person_file(collection_dir, name_b)
    if not fa:
        raise ValueError(f"'{name_a}' not found")
    if not fb:
        raise ValueError(f"'{name_b}' not found")

    name_a_display = _read_heading(fa)
    name_b_display = _read_heading(fb)

    _append_association(fa, name_b_display, link_type)
    _append_association(fb, name_a_display, link_type)

    return f"linked {name_a_display} —{link_type}→ {name_b_display}"


def add_entity_association(collection_dir, person_name, entity_ref, entity_label, link_type):
    """Link a person to a non-person entity (e.g. "work:norwegian-wood"),
    one-directional -- the entity has no file of its own to carry the
    reverse edge. Returns message string.
    """
    if not TYPED_REF_RE.match(entity_ref):
        raise ValueError(f"'{entity_ref}' is not a typed entity ref (expected 'type:slug')")
    fpath = _find_person_file(collection_dir, person_name)
    if not fpath:
        raise ValueError(f"'{person_name}' not found")
    display = _read_heading(fpath)
    _append_association(fpath, entity_label, link_type, ref=entity_ref)
    return f"linked {display} —{link_type}→ {entity_ref}"


def _append_association(fpath, target_name, link_type, ref=None):
    content = fpath.read_text(encoding="utf-8", errors="replace")
    sections = _parse_sections(content)

    href = f"({ref})" if ref else ""
    entry = f"- [{target_name}]{href} — {link_type}"
    assoc_lines = sections.get("associations", [])
    if assoc_lines == [""]:
        assoc_lines = []

    stripped = entry.strip()
    if stripped not in [l.strip() for l in assoc_lines]:
        assoc_lines.append(entry)

    sections["associations"] = assoc_lines
    fpath.write_text(_build_content(sections))


def append_line_to_section(fpath, section, line):
    """Append `line` to `## {section}` (creating it if absent), unless an
    equivalent line (stripped) is already there. Returns True if appended,
    False if it was already present. Generalizes _append_association/add_tag
    for sections review.py's bedrock accept writes to (## Defining moments).
    """
    content = fpath.read_text(encoding="utf-8", errors="replace")
    sections = _parse_sections(content)
    lines = sections.get(section, [])
    if lines == [""]:
        lines = []
    if line.strip() in [l.strip() for l in lines]:
        return False
    lines.append(line)
    sections[section] = lines
    fpath.write_text(_build_content(sections))
    return True


def add_tag(collection_dir, name, tag):
    """Add a tag to a person's ## Tags section."""
    fpath = _find_person_file(collection_dir, name)
    if not fpath:
        raise ValueError(f"'{name}' not found")

    content = fpath.read_text(encoding="utf-8", errors="replace")
    sections = _parse_sections(content)
    tags = _parse_tags(sections)
    if tag not in tags:
        tags.append(tag)
        sections["tags"] = [" ".join(tags)]

    fpath.write_text(_build_content(sections))
    return f"tagged {_read_heading(fpath)} with '{tag}'"


class CurationRefused(Exception):
    """Raised when an automated caller tries to create a person file in a
    collection whose curation policy is `human` (docs/design/collection-curation.md).
    """


def create_person_file_as_agent(collection_dir, slug, display_name, body=""):
    """Create a new person file on behalf of an automated process.

    This is the *agent* creation path (docs/design/collection-curation.md) and
    the only one gated by the collection's curation policy: it reads the target
    collection's COLLECTION.json and refuses with CurationRefused unless that
    collection declares `{"curation": "agent"}`. Absent, unreadable, malformed,
    or any other value means `human` and means refusal -- fail closed, so every
    existing collection is protected without being touched.

    The gate is on *creation by a machine* only. It restricts nothing a human
    does: person files stay plain markdown in git, a human may create or edit
    any file in any collection by any means, and no folk code path checks this
    policy on an edit.

    Once a human edits an agent-curated file, the file is theirs and the agent
    should stop rewriting it. That is a documented convention, deliberately not
    enforced in code -- the same posture as appearance.md Decision 6 and
    folk-render.md Decision 5, "documented convention over code-enforced
    restriction."

    Writes {collection}/{initial}/{slug}/{slug}.md and returns its Path.
    Raises FileExistsError if that file already exists -- creation never
    overwrites; an update to an existing file is a different act with a
    different owner.
    """
    if not SLUG_RE.match(slug or ""):
        raise ValueError(f"'{slug}' is not a valid person slug")

    collection_dir = Path(collection_dir)
    descriptor = config.load_collection_descriptor(collection_dir)
    if descriptor["curation"] != config.CURATION_AGENT:
        raise CurationRefused(
            f"collection at {collection_dir} has curation policy "
            f"'{descriptor['curation']}': only a human creates person files there"
        )

    fpath = collection_dir / slug[0].lower() / slug / f"{slug}.md"
    if fpath.exists():
        raise FileExistsError(f"person file already exists: {fpath}")

    fpath.parent.mkdir(parents=True, exist_ok=True)
    text = f"# {display_name}\n"
    if body:
        text += f"\n{body.rstrip()}\n"
    fpath.write_text(text, encoding="utf-8")
    return fpath


def random_person(collection_dir, context_tag=None):
    """Return a random person (name, filepath) or None."""
    people = list_persons(collection_dir, context_tag)
    if not people:
        return None
    return random.choice(people)


def collection_stats(collection_dir):
    """Return dict of stats for a collection."""
    all_files = list(_person_files(collection_dir))
    total = len(all_files)
    tagged = 0
    linked = 0
    described = 0
    tag_counts = {}
    for slug, fpath in all_files:
        content = fpath.read_text(encoding="utf-8", errors="replace")
        sections = _parse_sections(content)
        tags = _parse_tags(sections)
        if tags:
            tagged += 1
            for t in tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        assocs = _parse_associations(sections)
        if assocs:
            linked += 1
        # Appearance coverage (docs/design/appearance.md Decision 10) -- the
        # one part of the eval harness worth having outside it. A low count is
        # information, never a problem: most people in most collections have
        # no reason to carry a physical description.
        if appearance_text(_parse_appearance(sections)):
            described += 1

    return {
        "total": total,
        "tagged": tagged,
        "linked": linked,
        "described": described,
        "tags": tag_counts,
    }
