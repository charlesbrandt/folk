#!/usr/bin/env python3
"""One-shot: convert pre-journal index triples into observation journal events.

Before journal-in-folk.md landed, some external tools wrote directly into
the shared ~/.folk/triples.ndjson cache (invariant 1/2 violation -- the
index is supposed to be rebuild-only output, never a write target). Per
journal-schema.md's noted intentional divergence ("If any pre-journal
machine-suggested triples exist that are worth keeping, convert them into
journal events with a one-shot script; anything not derivable from person
files or journal is deliberately lost"), this script does that conversion
so the data survives the switch to journal-backed rebuild, properly scoped
to whichever collection's journal root you point it at (domain isolation
is the whole reason this script exists -- see journal-in-folk.md).

Triples are deduplicated by (s, p, o) before conversion: an external tool
re-scanning the same source data multiple times without clearing old rows
first produces exact duplicate lines in the legacy index, and the journal
lint rejects duplicate (s, p, o) within a segment.

Usage:
    python3 scripts/migrate_legacy_index_triples.py \\
        --index ~/.folk/triples.ndjson \\
        --prov-prefix "index:" \\
        --root ~/other/people/journal \\
        --collection other \\
        --writer legacy-migration \\
        --actor "extract:legacy-adapter" \\
        --dry-run

Drop --dry-run to actually write the segment. Nothing here touches
~/.folk/triples.ndjson itself -- that's a separate, deliberate step
(delete + `folk index --rebuild`) once the converted segment looks right.
"""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from folk import journal  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", required=True, type=Path, help="legacy index file to read triples from")
    ap.add_argument("--prov-prefix", default="index:", help="only convert rows whose prov starts with this")
    ap.add_argument("--root", required=True, type=Path, help="journal root to write the segment into")
    ap.add_argument("--collection", required=True, help="collection the root is scoped to (for the printed summary)")
    ap.add_argument("--writer", required=True, help="writer suffix for the segment filename")
    ap.add_argument("--actor", required=True, help="actor to stamp on the converted events, e.g. extract:legacy-adapter")
    ap.add_argument("--dry-run", action="store_true", help="print a summary and sample without writing anything")
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    session = f"conv:legacy-index-migration-{date.today().isoformat()}"

    seen = set()
    kept, skipped, deduped = [], 0, 0
    for lineno, line in enumerate(args.index.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            print(f"line {lineno}: invalid JSON, skipping", file=sys.stderr)
            continue
        prov = t.get("prov", "")
        if not prov.startswith(args.prov_prefix):
            skipped += 1
            continue
        s, p, o = t.get("s"), t.get("p"), t.get("o")
        if not (s and p and o):
            skipped += 1
            continue
        key = (s, p, o)
        if key in seen:
            deduped += 1
            continue
        seen.add(key)

        event = {
            "v": 1, "ts": ts, "actor": args.actor, "kind": "observation",
            "s": s, "p": p, "o": o, "session": session,
            "note": f"migrated from pre-journal index (orig prov={prov!r})",
        }
        event["id"] = journal.compute_id(ts, args.actor, s, p, o)
        kept.append(event)

    print(f"{args.index}: {len(kept)} unique triples to migrate "
          f"({deduped} exact-duplicate (s,p,o) rows dropped, {skipped} rows left in place -- wrong prov prefix)")

    if args.dry_run:
        print("\ndry run -- nothing written. Sample of converted events:")
        for e in kept[:5]:
            print(" ", json.dumps(e, sort_keys=True))
        return

    args.root.mkdir(parents=True, exist_ok=True)
    seg = args.root / f"{date.today().isoformat()[:7]}.{args.writer}.ndjson"
    with open(seg, "a", encoding="utf-8") as f:
        for e in kept:
            f.write(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {len(kept)} observation events to {seg} (collection={args.collection!r})")
    print(f"next: register '{args.collection}' -> {args.root.parent} in ~/.config/folk/collections if not already, "
          f"then delete ~/.folk/triples.ndjson and run `folk index --rebuild`")


if __name__ == "__main__":
    main()
