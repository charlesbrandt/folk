#!/usr/bin/env python3
"""Rebuild the index from person files + journal segments, then show a person.

Pure script, no LLM. Demonstrates the three-record model:
person files = curated, journal = what happened, index = derived cache.

    python3 replay.py rebuild          # fixtures/ + journal/ -> index.ndjson
    python3 replay.py show <id>        # tiered profile from the index
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
INDEX = HERE / "index.ndjson"

# Trust tier is derived from actor + kind + evidence + level, never stored
# as a number.
# human      — from a curated person file
# observed   — mechanically extracted record of what happened (extract:v1)
# stated     — agent-recorded direct statement, with quote + src pointer
# interpreted — an LLM's inference or judgment
# candidate  — level=bedrock proposal; surfaced to the human, never indexed as fact


def person_file_triples(path: Path):
    """Parse a folk person file into human-tier triples."""
    slug = "person:" + path.stem
    triples = []
    section = None
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
        elif section == "tags" and line.strip() and not line.startswith("#"):
            for tag in line.split():
                triples.append({"s": slug, "p": "tagged", "o": "tag:" + tag, "tier": "human", "src": str(path.name)})
        elif section == "associations" and line.strip().startswith("- "):
            m = re.match(r"- \[(.+?)\](?: — (.+))?", line.strip())
            if m:
                other = "person:" + m.group(1).lower().replace(" ", "-")
                rel = m.group(2) or "associated"
                triples.append({"s": slug, "p": rel, "o": other, "tier": "human", "src": str(path.name)})
    return triples


def journal_triples(path: Path):
    """Replay one journal segment into index triples + bedrock suggestions."""
    triples, suggestions = [], []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        kind = e.get("kind")
        base = {"s": e["s"], "p": e["p"], "o": e["o"],
                "src": e.get("src") or e.get("session", ""), "note": e.get("note", "")}
        if e.get("when"):
            base["when"] = e["when"]
        if kind == "promotion":
            if e.get("level") == "bedrock":
                suggestions.append({**base, "tier": "candidate"})
            else:
                tier = "stated" if e.get("evidence") == "stated" else "interpreted"
                triples.append({**base, "tier": tier})
        elif kind in ("observation", "session"):
            # Only relational observations are indexed; utterances stay
            # journal-only (drill-down via the msg: pointer).
            if e["p"] != "uttered":
                triples.append({**base, "tier": "observed"})
    return triples, suggestions


def rebuild():
    triples, suggestions = [], []
    for f in sorted((HERE / "fixtures").glob("*.md")):
        triples.extend(person_file_triples(f))
    for f in sorted((HERE / "journal").glob("*.ndjson")):
        t, s = journal_triples(f)
        triples.extend(t)
        suggestions.extend(s)
    with open(INDEX, "w") as out:
        for t in sorted(triples + suggestions, key=lambda x: json.dumps(x, sort_keys=True)):
            json.dump(t, out, ensure_ascii=False, sort_keys=True)
            out.write("\n")
    print(f"rebuilt {INDEX.name}: {len(triples)} triples, {len(suggestions)} bedrock suggestions")


def show(ident):
    if not str(ident).startswith(("person:", "agent:", "conv:")):
        ident = "person:" + ident
    rows = [json.loads(l) for l in INDEX.read_text().splitlines() if l.strip()]
    mine = [r for r in rows if r["s"] == ident or r["o"] == ident]
    tiers = {"human": "Curated (you wrote this)",
             "observed": "Observed (mechanical record)",
             "stated": "Stated (direct statement, agent-recorded — quote + src)",
             "interpreted": "Interpreted (agent inference — verify via src pointer)",
             "candidate": "Bedrock suggestions (awaiting your decision — not fact)"}
    print(ident)
    for tier, label in tiers.items():
        group = [r for r in mine if r["tier"] == tier]
        if not group:
            continue
        print(f"\n  {label}")
        for r in group:
            line = f"    {r['s']} —{r['p']}→ {r['o']}"
            if r.get("note"):
                line += f"\n        {r['note'][:120]}"
            if r.get("src"):
                line += f"\n        src: {r['src']}"
            print(line)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("rebuild", "show"):
        sys.exit(__doc__)
    if sys.argv[1] == "rebuild":
        rebuild()
    else:
        show(sys.argv[2])
