"""folk CLI — remember the people you know."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from . import agenda
from . import config
from . import context
from . import graph
from . import journal
from . import locus
from . import person
from . import promotion
from . import render
from . import review
from . import surface
from . import triples


def _resolve(args):
    return config.resolve_collection_dir(args.collection, args.dir)


def cmd_list(args):
    if args.locus:
        locus_id = args.locus if args.locus.startswith("locus:") else f"locus:{args.locus}"
        records = journal.locus_records(locus_id)
        if not records:
            print(f"(no records scoped to '{locus_id}')")
            return
        for r in sorted(records, key=lambda r: (r["s"], r["p"], r["o"], r.get("tier", ""))):
            line = f"{r['s']} --{r['p']}--> {r['o']}  [{r.get('tier')}]"
            print(line)
        return

    collection_dir, name = _resolve(args)
    people = person.list_persons(collection_dir, context_tag=args.context)
    if not people:
        print(f"(no people in '{name}')")
        return
    for display_name, fpath in people:
        print(f"{display_name}  ({fpath})")


def _print_tiered_index(grouped, now=None, vocab=None):
    """Superseded triples (decay-and-supersession.md Decision 3) are pulled
    out of their tier's list and shown only in a collapsed section at the
    end, so they never read as current; the "current" ones still get a
    read-time staleness annotation (Decision 1 -- computed here, at display
    time, never written back). `now`/`vocab` are injectable for tests; real
    callers leave them to default to the wall clock and live vocab.json.
    """
    if not any(grouped.values()):
        return
    now = now if now is not None else datetime.now()
    vocab = vocab if vocab is not None else journal.load_vocab()

    print()
    print("Index (tiered):")
    superseded = []
    for tier in journal.TIER_ORDER:
        group = grouped.get(tier) or []
        current = [r for r in group if not r.get("superseded_by")]
        superseded.extend(r for r in group if r.get("superseded_by"))
        if not current:
            continue
        print(f"\n  {journal.TIER_LABELS[tier]}")
        for r in current:
            state = journal.staleness(r, now, vocab)
            marker = f"  [{state}]" if state != "fresh" else ""
            line = f"    {r['s']} --{r['p']}--> {r['o']}{marker}"
            if r.get("note"):
                line += f"\n        {r['note'][:120]}"
            if r.get("src"):
                line += f"\n        src: {r['src']}"
            if r.get("when"):
                line += f"\n        when: {r['when']}"
            print(line)

    if superseded:
        print("\n  Superseded (not current)")
        for r in superseded:
            print(f"    {r['s']} --{r['p']}--> {r['o']}  (superseded by {r['superseded_by']})")


def cmd_lookup(args):
    """"Does this person already exist?" for source adapters minting
    person: slugs (ask 3, digger's community-layer.md decision 2) --
    checks every configured collection, not just the active one."""
    result = graph.find_person(args.name)
    if args.json:
        print(json.dumps(result))
        return
    if result["match"]:
        print(f"match: person:{result['match']['slug']}  ({result['match']['name']})")
    elif result["near_matches"]:
        for nm in result["near_matches"]:
            print(f"near-match: person:{nm['slug']}  ({nm['name']})  -- ambiguous, do not auto-reuse or merge")
    else:
        print(f"no match -- person:{result['query_slug']} would be new")


def cmd_show(args):
    if args.name.startswith("locus:"):
        _show_locus(args.name[len("locus:"):])
        return

    collection_dir, _ = _resolve(args)
    fpath = person._find_person_file(collection_dir, args.name)
    if not fpath:
        print(f"'{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    info = person.show_person(fpath)
    print(f"# {info['name']}")
    print()
    print(f"File: {info['file']}")
    if info["journal"]:
        print(f"Journal: {info['journal']}")
    print()

    if info["tags"]:
        print(f"Tags: {' '.join(info['tags'])}")
        print()

    if info["dates"]:
        print("Dates:")
        for d in info["dates"]:
            line = f"  - {d['label']}: {d['month_day']}"
            if d["year"]:
                line = f"  - {d['label']}: {d['year']}-{d['month_day']}"
            print(line)
        print()

    if info["archetype"]:
        print(f"Archetype: {info['archetype']}")
        print()

    if info["voice"]:
        print(f"Voice: {info['voice']}")
        print()

    if info["appearance"]["labels"] or info["appearance"]["note"]:
        print("Appearance:")
        for item in info["appearance"]["labels"]:
            print(f"  - {item['label']}: {item['value']}")
        if info["appearance"]["note"]:
            print(f"  {info['appearance']['note']}")
        print()

    if info["appearance_checkpoints"]:
        # Base-only default, never an implicit merge (docs/design/
        # appearance-checkpoints.md Decision 4/open question 2) -- `show`
        # lists names, not contents; `folk render --checkpoint` shows one.
        print(f"Appearance checkpoints: {', '.join(info['appearance_checkpoints'].keys())}")
        print()

    if info["associations"]:
        print("Associations:")
        for a in info["associations"]:
            line = f"  - {a['name']}"
            if a["type"]:
                line += f" ({a['type']})"
            print(line)
        print()

    if info["media"]:
        print("Media:")
        for m in info["media"]:
            line = f"  - {m['ref']}"
            if m["note"]:
                line += f"  — {m['note']}"
            print(line)
        print()

    if info["defining_moments"]:
        print("Defining moments:")
        for dm in info["defining_moments"]:
            print(f"  - {dm}")
        print()

    lines = info["content"].splitlines()
    main_lines = [l for l in lines if not l.startswith("## ") and not l.startswith("# ")]
    main_lines = [l for l in main_lines if l.strip()]
    if main_lines:
        for l in main_lines[:15]:
            print(l)
        if len(main_lines) > 15:
            print(f"... ({len(main_lines) - 15} more lines)")

    person_id = f"person:{fpath.stem}"
    _print_tiered_index(journal.person_profile(person_id))


def _show_locus(slug):
    fpath = locus.find_locus_file(config.load_loci_roots(), slug)
    if not fpath:
        print(f"'locus:{slug}' not found", file=sys.stderr)
        sys.exit(1)

    info = locus.show_locus(fpath)
    print(f"# {info['name']}")
    print()
    print(f"File: {info['file']}")
    print()

    if info["locus_type"]:
        print(f"Locus Type: {info['locus_type']}")
        print()

    if info["tags"]:
        print(f"Tags: {' '.join(info['tags'])}")
        print()

    # Provisional for a Locus (appearance.md open question 2): the parsing is
    # generic because show_locus delegates to show_person, so a Locus that
    # wants to separate its physical fabric from ## Genius Loci's mood and
    # rules can, and one that doesn't loses nothing.
    if info["appearance"]["labels"] or info["appearance"]["note"]:
        print("Appearance:")
        for item in info["appearance"]["labels"]:
            print(f"  - {item['label']}: {item['value']}")
        if info["appearance"]["note"]:
            print(f"  {info['appearance']['note']}")
        print()

    if info["appearance_checkpoints"]:
        print(f"Appearance checkpoints: {', '.join(info['appearance_checkpoints'].keys())}")
        print()

    if info["associations"]:
        print("Cast:")
        for a in info["associations"]:
            line = f"  - {a['name']}"
            if a["type"]:
                line += f" ({a['type']})"
            print(line)
        print()

    lines = info["content"].splitlines()
    main_lines = [l for l in lines if not l.startswith("## ") and not l.startswith("# ")]
    main_lines = [l for l in main_lines if l.strip()]
    if main_lines:
        for l in main_lines[:15]:
            print(l)
        if len(main_lines) > 15:
            print(f"... ({len(main_lines) - 15} more lines)")

    _print_tiered_index(journal.locus_profile(f"locus:{slug}"))


def cmd_render(args):
    if args.name.startswith("locus:"):
        fpath = locus.find_locus_file(config.load_loci_roots(), args.name[len("locus:"):])
        is_locus = True
    else:
        collection_dir, _ = _resolve(args)
        name = args.name[len("person:"):] if args.name.startswith("person:") else args.name
        fpath = person._find_person_file(collection_dir, name)
        is_locus = False
    if not fpath:
        print(f"'{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    checkpoint = args.checkpoint

    if args.format == "dream" and args.json:
        try:
            text = render.render_dream_json(fpath, is_locus=is_locus, checkpoint=checkpoint)
        except render.UnknownCheckpoint as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        if args.out:
            Path(args.out).write_text(text)
            print(f"wrote {args.out}")
        else:
            print(text, end="")
        return

    try:
        text = render.render(args.format, fpath, out=args.out, is_locus=is_locus, checkpoint=checkpoint)
    except render.UnknownCheckpoint as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except NotImplementedError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if args.out:
        print(f"wrote {args.out}")
    else:
        print(text, end="")


def cmd_link(args):
    collection_dir, name = _resolve(args)
    try:
        msg = person.add_association(collection_dir, args.a, args.b, args.type)
        print(msg)
        triples.index_rebuild()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tag(args):
    collection_dir, _ = _resolve(args)
    try:
        msg = person.add_tag(collection_dir, args.name, args.tag)
        print(msg)
        triples.index_rebuild()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_random(args):
    collection_dir, name = _resolve(args)
    result = person.random_person(collection_dir, context_tag=args.context)
    if not result:
        print(f"(no people in '{name}'{' with tag ' + args.context if args.context else ''})")
        return
    display_name, fpath = result
    print(f"{display_name}  ({fpath})")

    show_args = argparse.Namespace(
        name=display_name, collection=args.collection, dir=args.dir
    )
    cmd_show(show_args)


def cmd_context(args):
    if args.name:
        config.save_state({"active_collection": args.name})
        collections = config.load_collections()
        if args.name in collections:
            print(f"context set to '{args.name}' ({collections[args.name]})")
        else:
            print(f"context set to '{args.name}'")
        return

    state = config.load_state()
    active = state.get("active_collection")
    collections = config.load_collections()
    if active and active in collections:
        print(f"active context: '{active}' → {collections[active]}")
    elif active:
        print(f"active context: '{active}'")
    else:
        print("no active context set")
    print()
    print("Available collections:")
    for name, path in collections.items():
        marker = " ← active" if name == active else ""
        print(f"  {name}  → {path}{marker}")


def cmd_context_report(args):
    collection_dir, _ = _resolve(args)
    fpath = person._find_person_file(collection_dir, args.name)
    if not fpath:
        print(f"'{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    person_dir = fpath.parent
    sections = context.generate_report(person_dir)
    if sections is None:
        print(f"no .folk-context.json found in {person_dir}", file=sys.stderr)
        sys.exit(1)

    for label, content in sections:
        print(f"## {label}")
        print()
        print(content)
        print()


def cmd_stats(args):
    collection_dir, name = _resolve(args)
    stats = person.collection_stats(collection_dir)
    print(f"Collection: {name}")
    print(f"  People:   {stats['total']}")
    print(f"  Tagged:   {stats['tagged']}")
    print(f"  Linked:   {stats['linked']}")
    print(f"  Described: {stats['described']}")
    if stats["tags"]:
        print(f"  Tags ({len(stats['tags'])}):")
        for tag, count in sorted(stats["tags"].items(), key=lambda x: -x[1]):
            print(f"    {tag}: {count}")


def cmd_index(args):
    if args.rebuild:
        n_triples, n_suggestions, n_superseded = triples.index_rebuild()
        msg = f"rebuilt index: {n_triples} triples, {n_suggestions} bedrock suggestions"
        if n_superseded:
            msg += f", {n_superseded} superseded"
        print(msg)
    elif args.verify:
        collection_dir, _name = _resolve(args)
        issues = triples.verify(collection_dir)
        if issues:
            for i in issues:
                print(f"  issue: {i}")
        else:
            print("index looks clean")
    else:
        triple_count = len(triples.query())
        print(f"triple index: {triple_count} records at ~/.folk/triples.ndjson")


def cmd_graph(args):
    person_index = graph.build_person_index()

    if args.person:
        person_id = args.person if args.person.startswith("person:") else f"person:{graph.slugify(args.person)}"
        edges = graph.ego_edges(person_id, depth=args.depth)
    elif args.locus:
        locus_id = args.locus if args.locus.startswith("locus:") else f"locus:{args.locus}"
        edges = graph.locus_edges(locus_id)
    elif args.context:
        edges = graph.context_edges(args.context)
    else:
        _collection_dir, col_name = _resolve(args)
        edges = graph.collection_edges(col_name)

    nodes = graph.nodes_from_edges(edges)
    if len(nodes) > graph.NODE_LIMIT:
        print(
            f"warning: graph would have {len(nodes)} nodes (> {graph.NODE_LIMIT}); "
            "narrow with --person or --context instead of emitting an unreadable diagram",
            file=sys.stderr,
        )
        return

    print(graph.render_mermaid(edges, person_index), end="")


def cmd_surface(args):
    locus_id = None
    if args.locus:
        locus_id = args.locus if args.locus.startswith("locus:") else f"locus:{args.locus}"
    person_ids = [p if p.startswith("person:") else f"person:{graph.slugify(p)}" for p in args.person]

    now = datetime.fromisoformat(args.now) if args.now else None
    items = surface.surface(locus_id=locus_id, person_ids=person_ids, budget=args.budget, now=now)

    if args.json:
        print(json.dumps(items, indent=2, sort_keys=True, default=str))
        return
    for it in items:
        print(it["reason"])


def cmd_agenda(args):
    if args.collection or args.dir:
        collection_dir, _name = _resolve(args)
        collection_dirs = [collection_dir]
    else:
        collection_dirs = [Path(p) for p in config.load_collections().values()]

    now = datetime.fromisoformat(args.now) if args.now else None
    items = agenda.upcoming(collection_dirs, within_days=args.within, now=now)

    if args.json:
        print(json.dumps(items, indent=2, sort_keys=True, default=str))
        return
    if not items:
        print("(no upcoming dates)")
        return
    for it in items:
        print(f"{it['date']}  {it['person']} — {it['label']}  (in {it['days_until']}d)")


def cmd_focus(args):
    locus_id = None
    if args.locus:
        locus_id = args.locus if args.locus.startswith("locus:") else f"locus:{args.locus}"
    person_ids = [p if p.startswith("person:") else f"person:{graph.slugify(p)}" for p in args.person]

    items = surface.focus(locus_id=locus_id, person_ids=person_ids, collection=args.collection, budget=args.budget)

    if args.json:
        print(json.dumps(items, indent=2, sort_keys=True, default=str))
        return
    for it in items:
        print(it["reason"])


REVIEW_LABELS = {
    "vocab": "Vocab proposals",
    "entity": "Entity-resolution proposals",
    "bedrock": "Bedrock suggestions",
    "lint_failure": "Lint failures",
}
REVIEW_ORDER = ("vocab", "entity", "bedrock", "lint_failure")


def cmd_review(args):
    roots = config.load_journal_roots()
    items = review.pending_items(roots=roots)

    if args.json:
        print(json.dumps(items, indent=2, sort_keys=True, default=str))
        return

    total = sum(len(v) for v in items.values())
    if total == 0:
        print("(review queue is empty)")
        return

    if args.interactive:
        _run_interactive_review(items, roots)
        return

    for kind in REVIEW_ORDER:
        group = items[kind]
        if not group:
            continue
        print(f"{REVIEW_LABELS[kind]} ({len(group)}):")
        for it in group:
            print("  " + review.describe_item(it).replace("\n", "\n  "))
        print()


def _run_interactive_review(items, roots):
    flat = [it for kind in REVIEW_ORDER for it in items[kind]]
    for it in flat:
        print()
        print(review.describe_item(it, verbose=True))

        if it["type"] == "lint_failure":
            choice = input("[r]eject(discard) / [s]kip / [q]uit: ").strip().lower()
            if choice == "q":
                break
            if choice == "r":
                review.discard_quarantine(it)
                print("discarded.")
            continue

        choice = input("[a]ccept / [r]eject / [s]kip / [q]uit: ").strip().lower()
        if choice == "q":
            break
        if choice == "r":
            review.record_review(it, "reject", roots=roots)
            print("rejected.")
            triples.index_rebuild()
            continue
        if choice != "a":
            continue

        if it["type"] == "vocab":
            review.accept_vocab(it)
            review.record_review(it, "accept", roots=roots)
            print("accepted -- added to vocab.json.")
        elif it["type"] == "entity":
            review.accept_entity(it)
            review.record_review(it, "accept", roots=roots)
            print("accepted -- alias added to vocab.json.")
        elif it["type"] == "bedrock":
            try:
                fpath, section, line, diff = review.preview_bedrock_edit(it)
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                continue
            if not diff:
                print(f"(already present in {fpath})")
                review.record_review(it, "accept", roots=roots)
                triples.index_rebuild()
                continue
            print(diff)
            confirm = input(f"apply this to {fpath}? [y/N]: ").strip().lower()
            if confirm != "y":
                print("not applied -- item stays pending.")
                continue
            review.apply_bedrock_edit(fpath, section, line)
            review.record_review(it, "accept", roots=roots)
            print(f"appended to {fpath}.")
        triples.index_rebuild()


def cmd_promote(args):
    results = promotion.run_once(cap=args.cap)
    if not results:
        print("(no sessions ready to process)")
        return
    for session_id, outcome in results:
        print(f"{session_id}: {outcome}")
    n_quarantined = sum(1 for _s, o in results if o == "quarantined")
    if n_quarantined:
        print(f"\n{n_quarantined} session(s) quarantined -- see folk review")


def cmd_journal_lint(args):
    errors, proposals, n = journal.lint_paths(
        args.segments,
        transcript_path=args.transcript,
        user_slug=args.user,
        agent_slug=args.agent,
    )
    names = ", ".join(args.segments)
    print(f"{names}: {n} events -- {len(errors)} errors, {len(proposals)} vocab/entity proposals")
    for e in errors:
        print("  ERROR", e)
    for p in proposals:
        print("  PROPOSAL", p)
    if errors:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="folk",
        description="remember the people you know",
    )
    parser.add_argument(
        "-C", "--collection",
        help="collection name (resolved from ~/.config/folk/collections)",
    )
    parser.add_argument(
        "-d", "--dir",
        help="explicit path to collection (overrides -C and $FOLK_DIR)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list people in the active collection")
    p_list.add_argument("--context", help="filter by tag")
    p_list.add_argument("--locus", help="list records scoped to this Locus (slug, with or without 'locus:')")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show a person")
    p_show.add_argument("name", help="person name or slug")
    p_show.set_defaults(func=cmd_show)

    p_lookup = sub.add_parser(
        "lookup", help="check whether a person matching NAME already exists (for source adapters, before minting a new person: slug)")
    p_lookup.add_argument("name", help="free-text name or handle to check")
    p_lookup.add_argument("--json", action="store_true", help="machine-readable output")
    p_lookup.set_defaults(func=cmd_lookup)

    p_render = sub.add_parser(
        "render", help="render a generated persona view (SOUL.md, dream JSON) from a person file or Locus")
    p_render.add_argument("name", help="person name, person:<slug>, or locus:<slug>")
    p_render.add_argument(
        "--format", default="soul", choices=["soul", "card", "yaml", "dream"],
        help="render format ('soul' and 'dream' are implemented; 'card'/'yaml' fail cleanly)")
    p_render.add_argument("--out", help="write to this path instead of stdout")
    p_render.add_argument("--json", action="store_true", help="machine-readable JSON output (--format dream)")
    p_render.add_argument(
        "--checkpoint", help="select a named '## Appearance: <name>' state instead of the base section")
    p_render.set_defaults(func=cmd_render)

    p_link = sub.add_parser("link", help="link two people")
    p_link.add_argument("a", help="first person")
    p_link.add_argument("b", help="second person")
    p_link.add_argument("type", help="relationship (e.g. mentor, colleague)")
    p_link.set_defaults(func=cmd_link)

    p_tag = sub.add_parser("tag", help="tag a person")
    p_tag.add_argument("name", help="person name or slug")
    p_tag.add_argument("tag", help="tag to add")
    p_tag.set_defaults(func=cmd_tag)

    p_random = sub.add_parser("random", help="show a random person")
    p_random.add_argument("--context", help="filter by tag")
    p_random.set_defaults(func=cmd_random)

    p_ctx = sub.add_parser("context", help="show or set active collection")
    p_ctx.add_argument("name", nargs="?", help="collection name to activate")
    p_ctx.set_defaults(func=cmd_context)

    p_ctx_report = sub.add_parser("context-report", help="generate context report for a person")
    p_ctx_report.add_argument("name", help="person name or slug")
    p_ctx_report.set_defaults(func=cmd_context_report)

    p_stats = sub.add_parser("stats", help="collection statistics")
    p_stats.set_defaults(func=cmd_stats)

    p_index = sub.add_parser("index", help="manage the triple index")
    p_index.add_argument("--rebuild", action="store_true", help="regenerate from person files + journal")
    p_index.add_argument("--verify", action="store_true", help="check for broken references")
    p_index.set_defaults(func=cmd_index)

    p_graph = sub.add_parser("graph", help="emit a Mermaid graph over the triple index")
    p_graph.add_argument("--person", help="ego graph centered on this person")
    p_graph.add_argument("--depth", type=int, default=2, help="ego graph depth (default 2, with --person)")
    p_graph.add_argument("--context", help="filter to people carrying this tag")
    p_graph.add_argument("--locus", help="cast-list graph for this Locus (slug, with or without 'locus:')")
    p_graph.set_defaults(func=cmd_graph)

    p_surface = sub.add_parser(
        "surface", help="cross-context relevance: a bounded, ranked slice of facts for session-start assembly")
    p_surface.add_argument("--locus", help="Locus slug (with or without 'locus:') defining the session's focus")
    p_surface.add_argument("--person", action="append", default=[],
                            help="explicit participant (name or slug); repeatable")
    p_surface.add_argument("--budget", type=int, default=surface.DEFAULT_BUDGET,
                            help=f"max items to return (default {surface.DEFAULT_BUDGET})")
    p_surface.add_argument("--now", help="ISO timestamp to use as 'now' for staleness (tests/reproducibility)")
    p_surface.add_argument("--json", action="store_true", help="machine-readable output for prompt assembly")
    p_surface.set_defaults(func=cmd_surface)

    p_agenda = sub.add_parser(
        "agenda", help="upcoming dated events (birthdays, anniversaries) across collections, soonest first")
    p_agenda.add_argument("--within", type=int, default=30, help="look-ahead window in days (default 30)")
    p_agenda.add_argument("--now", help="ISO timestamp to use as 'now' (tests/reproducibility)")
    p_agenda.add_argument("--json", action="store_true", help="machine-readable output")
    p_agenda.set_defaults(func=cmd_agenda)

    p_focus = sub.add_parser(
        "focus", help="attention ranking: containers (people/loci) ranked by the same RRF engine as surface")
    p_focus.add_argument("--locus", help="restrict to this Locus's cast/focus set (slug, with or without 'locus:')")
    p_focus.add_argument("--person", action="append", default=[],
                          help="restrict to this container (name or slug); repeatable")
    p_focus.add_argument("--collection", help="restrict to containers with at least one triple in this collection")
    p_focus.add_argument("--budget", type=int, default=surface.DEFAULT_BUDGET,
                          help=f"max items to return (default {surface.DEFAULT_BUDGET})")
    p_focus.add_argument("--json", action="store_true", help="machine-readable output")
    p_focus.set_defaults(func=cmd_focus)

    p_review = sub.add_parser("review", help="review pending journal decisions (vocab, entity, bedrock, lint failures)")
    p_review.add_argument("--interactive", action="store_true", help="step through items: accept/reject/skip/quit")
    p_review.add_argument("--json", action="store_true", help="machine-readable pending list")
    p_review.set_defaults(func=cmd_review)

    p_promote = sub.add_parser(
        "promote", help="run the session-end promotion job once (extract/promote/lint/append or quarantine)")
    p_promote.add_argument("--cap", type=int, help="override cap_per_run from ~/.config/folk/promotion.json")
    p_promote.set_defaults(func=cmd_promote)

    p_journal = sub.add_parser("journal", help="journal segment tools")
    journal_sub = p_journal.add_subparsers(dest="journal_command", required=True)
    p_journal_lint = journal_sub.add_parser("lint", help="lint journal segment(s), no LLM")
    p_journal_lint.add_argument("segments", nargs="+", help="segment NDJSON file(s) to lint together")
    p_journal_lint.add_argument("--transcript", help="raw source transcript (JSONL) for authoritative quote checks")
    p_journal_lint.add_argument("--user", default="person:sam", help="folk id of the transcript's human speaker")
    p_journal_lint.add_argument("--agent", default="agent:hermes-main", help="folk id of the transcript's agent speaker")
    p_journal_lint.set_defaults(func=cmd_journal_lint)

    args = parser.parse_args()
    try:
        args.func(args)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
