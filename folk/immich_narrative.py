"""Deterministic narrative renderer over the Immich adapter's journal events
(docs/design/immich-source.md Decision 7).

Reads only the journal (registered journal roots, via journal.iter_segments
and read_segment) filtered to ACTOR = import:immich:v1 -- never the index,
which is a deletable cache (invariant 1), and never a person file. Output is
derived markdown: per-person timelines and a summary roll-up by year and by
place. The rule is the same as folk render's (folk-render.md Decision 1): no
LLM, no clock, no randomness. Running it twice on the same journal yields
byte-identical files. The same bar holds for every deterministic path in
folk (invariant 4).

Event handling mirrors the adapter's dedupe rule: events are sorted by `ts`
(stable, so file order breaks ties) and a later event replaces an earlier one
for the same asset field. That makes a corrected Immich description, appended
as a later observation, win over the original.
"""

from collections import defaultdict
from pathlib import Path

from . import journal
from .sources.immich import ACTOR

UNDATED = "undated"


def load_events(roots):
    """Every ACTOR observation event across the given registered journal
    roots (journal.iter_segments' shape: [{"path", "collection"}, ...]),
    in deterministic segment order.
    """
    events = []
    for seg, _collection in journal.iter_segments(roots=roots):
        for e in journal.read_segment(seg):
            if e.get("actor") == ACTOR and e.get("kind") == "observation":
                events.append(e)
    return events


def _local(ref):
    """'person:abc' -> 'abc'. Refs without a prefix pass through unchanged."""
    return ref.split(":", 1)[1] if ":" in (ref or "") else (ref or "")


def assemble(events):
    """Fold events into one record per asset source:
    {src: {"when", "people": set(slugs), "place", "photo", "description"}}.
    Duplicates (same full dedupe key) are ignored; for scalar fields the last
    event in ts order wins.
    """
    ordered = sorted(enumerate(events), key=lambda pair: (pair[1].get("ts") or "", pair[0]))
    assets = {}
    seen = set()
    for _i, e in ordered:
        src = e.get("src") or ""
        key = (src, e.get("s"), e.get("p"), e.get("o"), e.get("note"))
        if key in seen:
            continue
        seen.add(key)
        a = assets.setdefault(src, {"when": None, "people": set(), "place": None,
                                    "photo": None, "description": None})
        if e.get("when"):
            a["when"] = e["when"]
        p = e.get("p")
        s, o = e.get("s") or "", e.get("o") or ""
        if p == "pictured_with":
            a["people"].update({_local(s), _local(o)})
        elif p == "pictured_at":
            a["people"].add(_local(s))
            a["place"] = _local(o)
        elif p == "described_in":
            a["people"].add(_local(s))
            a["photo"] = o
            a["description"] = e.get("note") or ""
    return assets


def _order_key(item):
    src, a = item
    return (a["when"] or "9999-99-99", src)


def _one_line(text):
    return " ".join((text or "").split())


def render(events, names=None):
    """{relative path: markdown text} for the whole journal slice.

    names: optional {person slug: display name}; a slug with no name is shown
    as the slug. Paths are "summary.md" and "people/<slug>.md".
    """
    names = names or {}
    assets = assemble(events)

    def label(slug):
        return names.get(slug) or slug

    by_person = defaultdict(list)
    for src, a in sorted(assets.items(), key=_order_key):
        for slug in a["people"]:
            by_person[slug].append((src, a))

    files = {}
    for slug in sorted(by_person):
        lines = [
            f"# {label(slug)}",
            "",
            "Derived from the Immich adapter's journal events (actor import:immich:v1). "
            "Generated output: not curated, not a person file. Regenerate; do not hand-edit.",
            "",
            "## Timeline",
            "",
        ]
        for src, a in by_person[slug]:
            when = a["when"] or UNDATED
            text = _one_line(a["description"]) or "(no description)"
            others = sorted(a["people"] - {slug})
            line = f"- {when} — {text}"
            if others:
                line += " — with " + ", ".join(label(o) for o in others)
            if a["place"]:
                line += f" — at {a['place']}"
            lines.append(f"{line} ({src})")
        files[f"people/{slug}.md"] = "\n".join(lines) + "\n"

    by_year = defaultdict(lambda: {"photos": 0, "people": set()})
    by_place = defaultdict(lambda: {"photos": 0, "people": set()})
    for _src, a in assets.items():
        year = (a["when"] or UNDATED)[:4] if a["when"] else UNDATED
        by_year[year]["photos"] += 1
        by_year[year]["people"].update(a["people"])
        if a["place"]:
            by_place[a["place"]]["photos"] += 1
            by_place[a["place"]]["people"].update(a["people"])

    summary = ["# Immich narrative summary", "",
               "Derived from the Immich adapter's journal events (actor import:immich:v1). "
               "Generated output: not curated. Regenerate; do not hand-edit.", "",
               "## By year", ""]
    for year in sorted(by_year, key=lambda y: (y == UNDATED, y)):
        info = by_year[year]
        summary.append(f"- {year}: {info['photos']} photo(s), people: "
                       + (", ".join(sorted(label(p) for p in info["people"])) or "none"))
    summary += ["", "## By place", ""]
    for place in sorted(by_place):
        info = by_place[place]
        summary.append(f"- {place}: {info['photos']} photo(s), people: "
                       + ", ".join(sorted(label(p) for p in info["people"])))
    if not by_place:
        summary.append("- none recorded")
    files["summary.md"] = "\n".join(summary) + "\n"
    return files


def write(out_dir, files):
    """Write rendered files under out_dir. Only files this renderer produces
    are written; any stale people/*.md no longer produced is removed, so the
    output directory always equals a fresh render.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    people_dir = out / "people"
    people_dir.mkdir(exist_ok=True)
    for rel, text in sorted(files.items()):
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    keep = {Path(rel).name for rel in files if rel.startswith("people/")}
    for stale in people_dir.glob("*.md"):
        if stale.name not in keep:
            stale.unlink()
    return sorted(files)
