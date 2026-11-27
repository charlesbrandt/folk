#!/usr/bin/env python3
"""Glue: Immich -> folk observations -> a collection's journal
(docs/design/immich-source.md).

Dry-run by default: fetches, parses, dedupes, runs the identity check, and
prints a plan. Nothing is written unless --confirm is given. Even then this
script never rebuilds the index; run `folk index --rebuild` once afterwards.

    python3 scripts/run_immich_import.py --collection-dir ~/people/<immich-collection>
    python3 scripts/run_immich_import.py --collection-dir ... --confirm

Config (flags win over env):
    --base-url        or FOLK_IMMICH_BASE_URL       e.g. http://<immich-host>:2283
    --api-key-file    or FOLK_IMMICH_KEY_FILE        an env file holding the key
    --api-key-var     default IMMICH_API_KEY         the variable name in that file
                      (with no key file, the variable is read from the environment)
    --since           optional YYYY-MM-DD; only assets taken on or after it

The key is never printed, logged, or written anywhere. Only counts and
display names reach stdout, and those names are the operator's own data.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from folk import bulk, graph  # noqa: E402
from folk.sources import immich  # noqa: E402

NEAR_MATCH_LOG = "near-matches.jsonl"


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--collection-dir", required=True,
                   help="the collection root; must hold COLLECTION.json {\"curation\": \"agent\"} to mint people")
    p.add_argument("--base-url", default=os.environ.get("FOLK_IMMICH_BASE_URL"))
    p.add_argument("--api-key-file", default=os.environ.get("FOLK_IMMICH_KEY_FILE"))
    p.add_argument("--api-key-var", default=immich.DEFAULT_KEY_VAR)
    p.add_argument("--page-size", type=int, default=immich.DEFAULT_PAGE_SIZE)
    p.add_argument("--since", default=None)
    p.add_argument("--writer", default="immich", help="journal segment writer name (per-writer segments)")
    p.add_argument("--confirm", action="store_true", help="actually append events and mint people")
    return p


def plan(raw_assets, collection_dir, ts):
    """Pure-ish planning step: events, dedupe, identity decisions. Reads the
    journal and the person index; writes nothing. Returns a dict the caller
    prints and, with --confirm, acts on.
    """
    root = Path(collection_dir) / "journal"
    built, malformed = [], 0
    for raw in raw_assets:
        try:
            built.extend(immich.parse(raw, ts))
        except KeyError:
            malformed += 1

    fresh, dropped = immich.dedupe(built, immich.existing_keys(root))

    names = immich.person_names(raw_assets)
    exact, near_by_slug, reuse_names = [], {}, {}
    for subject, display in sorted(names.items()):
        result = graph.find_person(display)
        if result["match"]:
            exact.append(subject)
        elif result["near_matches"]:
            near_by_slug[subject] = result["near_matches"]
        else:
            reuse_names[subject] = display
    # A subject that exists elsewhere is not re-minted here, and one with a
    # near match is held back (never auto-merged, never auto-created).
    to_write, held = immich.split_by_identity(fresh, near_by_slug)
    # Mint exactly the people the events to be written reference, as subject
    # or object: a pair event's object may have no subject event of its own.
    referenced = {ref for e in to_write for ref in (e.get("s"), e.get("o"))}
    mint_names = {s: n for s, n in reuse_names.items() if s in referenced and s not in near_by_slug}
    return {
        "root": root, "assets": len(raw_assets), "malformed": malformed,
        "built": len(built), "dropped_dupes": dropped, "to_write": to_write,
        "held": held, "exact": exact, "near_by_slug": near_by_slug,
        "mint_names": mint_names, "variants": immich.name_variants(raw_assets),
    }


def near_match_records(plan_result, ts):
    """One JSON-Lines record per held-back person (bulk-import.md lessons):
    the Immich name, its slug, what it was near-matched against, and how many
    events were held. Collection-local, never a substitute for a human decision.
    """
    records = []
    for subject, candidates in sorted(plan_result["near_by_slug"].items()):
        held_n = sum(1 for e in plan_result["held"] if subject in (e.get("s"), e.get("o")))
        records.append({"ts": ts, "slug": subject, "candidates": candidates, "events_held": held_n})
    return records


def append_near_matches(collection_dir, records):
    if not records:
        return None
    path = Path(collection_dir) / NEAR_MATCH_LOG
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.base_url:
        print("error: --base-url (or FOLK_IMMICH_BASE_URL) is required", file=sys.stderr)
        return 2
    collection_dir = Path(args.collection_dir).expanduser()
    if not collection_dir.is_dir():
        print(f"error: collection dir {collection_dir} does not exist", file=sys.stderr)
        return 2
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    cfg = {"base_url": args.base_url, "api_key_env_file": args.api_key_file,
           "api_key_var": args.api_key_var, "page_size": args.page_size, "since": args.since}
    try:
        raw_assets = immich.fetch(cfg)
    except immich.ImmichError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1

    p = plan(raw_assets, collection_dir, ts)
    mode = "CONFIRM (writing)" if args.confirm else "DRY RUN (nothing written)"
    print(f"mode: {mode}")
    print(f"assets fetched: {p['assets']}  malformed (no id): {p['malformed']}")
    print(f"events built: {p['built']}  already in journal (skipped): {p['dropped_dupes']}")
    print(f"people already known (exact match, reused, not minted): {len(p['exact'])}")
    print(f"people held for identity review (near match): {len(p['near_by_slug'])}  "
          f"events held: {len(p['held'])}")
    print(f"events to append: {len(p['to_write'])}  people to mint: {len(p['mint_names'])}")
    if p["variants"]:
        print(f"name spellings folding to one slug (not resolved here): {len(p['variants'])}")
        for slug, names in sorted(p["variants"].items()):
            print(f"  {slug}: {' | '.join(names)}")

    if not args.confirm:
        print("\nDry run only. Re-run with --confirm to write. Nothing was appended.")
        return 0

    p["root"].mkdir(parents=True, exist_ok=True)
    outcomes = bulk.import_batch(p["root"], args.writer, p["to_write"],
                                 collection_dir=collection_dir, person_names=p["mint_names"])
    appended = sum(1 for o in outcomes if o["status"] == "appended")
    skipped = [o for o in outcomes if o["status"] == "skipped"]
    minted = sum(1 for o in outcomes if o["minted"])
    log_path = append_near_matches(collection_dir, near_match_records(p, ts))

    print(f"\nappended: {appended}  lint-skipped: {len(skipped)}  people minted: {minted}")
    for o in skipped[:10]:
        print(f"  skipped {o['src']}: {o['reason']}")
    if log_path:
        print(f"near matches logged: {log_path}")
    print("\nVerify against ground truth, not this tally: spot-check a few people with "
          "`folk show person:<slug>` and count the journal segments in the collection's journal/.")
    print("Then run `folk index --rebuild` once (this script never rebuilds the index).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
