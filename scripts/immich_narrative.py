#!/usr/bin/env python3
"""Render the Immich narrative from the adapter's journal events
(docs/design/immich-source.md Decision 7).

Deterministic: no LLM, no clock. Running it twice on the same journal writes
byte-identical files. Output is derived markdown, written only under --out.
--out must not sit inside the collection directory, so derived text can
never be mistaken for a person file.

    python3 scripts/immich_narrative.py --collection-dir ~/people/<coll> --out ~/derived/immich-narrative

Only the journal is read (the registered roots for this collection's journal/
directory), never the index.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from folk import immich_narrative, person  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the Immich narrative (derived, deterministic).")
    ap.add_argument("--collection-dir", required=True)
    ap.add_argument("--out", required=True, help="output directory, outside the collection dir")
    args = ap.parse_args(argv)

    coll = Path(args.collection_dir).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    if out == coll or coll in out.parents:
        print("error: --out must not be inside the collection directory", file=sys.stderr)
        return 2
    if not coll.is_dir():
        print(f"error: collection dir {coll} does not exist", file=sys.stderr)
        return 2

    roots = [{"path": coll / "journal", "collection": coll.name}]
    events = immich_narrative.load_events(roots)
    names = {fpath.stem: name for name, fpath in person.list_persons(coll)}
    files = immich_narrative.render(events, names=names)
    written = immich_narrative.write(out, files)
    print(f"events read: {len(events)}  files written: {len(written)} under {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
