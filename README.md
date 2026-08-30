# folk

Remember the people you know.

A UNIX-philosophy tool for tracking people across collections (personal, work, and domain collections like fictional characters or authors), their media, conversations, and the connections between them — with intentional curation, not algorithmic dumping.

## Quick start

A small reference collection ships in this repo at `examples/characters/` — a couple of person files (associations, tags, an `## Appearance` section with a checkpoint) and a Locus file (`## Locus Type`, `## Genius Loci`) — so you can try the basics with zero setup, via `-d/--dir` (an explicit filesystem path, no `~/.config/folk/collections` entry required):

```bash
folk -d examples/characters list                                # list people in a collection
folk -d examples/characters show toru-watanabe                   # show a person, tiered profile included
folk -d examples/characters link naoko toru-watanabe childhood-friend
folk -d examples/characters tag sheep-man recurring
folk -d examples/characters random                                # remember someone
folk -d examples/characters stats                                 # collection overview
```

`folk graph`, `folk lookup`, and `folk show locus:<slug>` read across every collection registered in `~/.config/folk/collections` (and the rebuilt triple index) rather than an ad hoc `-d` path, so trying those against the fixture data means registering `examples/characters` there first and running `folk index --rebuild` once. Once you've registered your own collections (see "Collections" below):

```bash
folk -C characters graph --person toru-watanabe --depth 2  # Mermaid graph, terminal-first
folk -C authors show haruki-murakami                     # authors get their own collection
folk lookup "toru watanabe" --json                     # does this person exist? (checks every registered collection)
```

## Collections

Physically separate directory trees, logically partitioned. Collections are config, never code — no collection name is ever enumerated in folk's source, so adding a domain (`musicians`, `loci`, ...) is a one-line change:

```bash
folk -C personal list        # browse personal
folk -C characters list      # browse a domain collection (separate dir)
folk context characters      # set active context
folk list                    # now using the characters collection
```

Configured in `~/.config/folk/collections`:

```json
{"personal": "~/people/personal",
 "characters": "~/notes/fiction/characters",
 "authors": "~/notes/fiction/authors",
 "musicians": "~/notes/music/people"}
```

Real people and fictional people are never merged into one collection — cross-domain connections (a character `appears_in` a book, an author who `created` it) are edges in the graph, not shared files. An entity that belongs to two collections gets one canonical person file and a symlink from the secondary collection, never two files.

## Storage model

Three records, one authority each — never make anything authoritative in two places.

| Layer | Authority | Format | Location |
|-------|-----------|--------|----------|
| Person files | What the human curated | Markdown, git-tracked | Collection dir (`{collection}/{initial}/{slug}/{slug}.md`) |
| Journal | What happened | Append-only NDJSON segments, never edited | Registered per-collection journal roots (`{collection-dir}/journal/YYYY-MM.{writer}.ndjson`) — no single global journal directory |
| Triple index | Derived cache | NDJSON | `~/.folk/triples.ndjson` — deletable and rebuildable at any time. Nothing under `~/.folk/` is authoritative: the review quarantine, the promotion state file and log, and the sibling `~/.folk-staging/` also live there, but they are host-local operational state, not a fourth record |

`folk index --rebuild` is the only thing that ever writes the index: it parses person files (human tier) and replays every journal segment (observed/stated/interpreted tiers, plus `bedrock` suggestions awaiting a human decision), deterministically. Run twice, byte-identical output — there is no LLM anywhere in this path.

## Commands

| Command | Description |
|---------|-------------|
| `list [--context <tag>]` | List people, optionally filtered by tag |
| `show <name>` | Show a person: associations, tags, media, and the tiered index profile |
| `link <a> <b> <type>` | Bidirectional association, written to both person files |
| `tag <name> <tag>` | Add a tag |
| `random [--context <tag>]` | Pick a random person |
| `context [<name>]` | Show or set active collection |
| `context-report <name>` | Generate a context report for a person |
| `stats` | Collection statistics |
| `graph [--person <slug>] [--depth N] [--context <tag>]` | Emit a Mermaid graph over the triple index |
| `index [--rebuild] [--verify]` | Rebuild the triple index from person files + journal, or check for broken references |
| `journal lint <segments...>` | Lint journal segment(s) against the schema — no LLM involved |
| `review [--interactive] [--json]` | Work the review queue: vocab proposals, entity near-duplicates, bedrock suggestions, lint failures |
| `promote [--cap N]` | Run the session-end promotion job once: extract → LLM-propose → lint → append or quarantine |

## Person file format

```markdown
# Toru Watanabe

Narrator and protagonist of Norwegian Wood.

## Associations
- [Norwegian Wood](work:norwegian-wood) — appears_in

## Tags
character
```

## Trust tiers

`folk show` groups facts by tier, derived at read time from who asserted it and how — there are no `conf` numbers to hand-tune:

1. **Curated** — you wrote this, in a person file.
2. **Observed** — mechanical record (e.g. a message was sent).
3. **Stated** — a direct statement, agent-recorded with a quote and a `src` pointer back to the transcript.
4. **Interpreted** — an agent's inference; verify via the `src` pointer.
5. **Bedrock suggestions** — proposed durable facts awaiting your decision in `folk review`; not fact until you accept them, and only ever land in a person file, never the index.

## Design

folk is Layer 0 of a larger persona-agent architecture, but this repo is self-contained and usable on its own. See `docs/design/` for the specs behind the current implementation (journal schema, review queue, session promotion, collections + graph).

Key decisions:
- **Agency**: the system suggests, you decide. Only a human edits Bedrock (person files); nothing else is ever promoted into them automatically.
- **Files over databases**: person files are plain markdown, journal segments and the triple index are NDJSON (greppable, `jq`-compatible). No lock-in.
- **No media duplication**: reference photos/videos in Immich, Plex, or local paths. `folk media` queries them at recall time.
- **Perennial**: Python stdlib only, zero daemon dependencies, git-trackable.

## Development history

This repo's public history is a curated export from a longer private development history, grouped into milestone commits rather than replaying every incremental change — done deliberately before the first public push, to keep personal test data and infrastructure details that accumulate during private day-to-day use out of what ships here. `scripts/check_release_hygiene.py` is the checker that enforces this going forward for anyone contributing.
