# folk

Remember the people you know.

A UNIX-philosophy tool for tracking people across collections (personal, work, and domain collections like fictional characters or authors), their media, conversations, and the connections between them — with intentional curation, not algorithmic dumping.

## Quick start

A small reference collection ships in this repo at `examples/characters/` — a couple of person files (associations, tags, `## Archetype`, `## Voice`, an `## Appearance` section with a checkpoint, `## Defining moments`) and a Locus file (`## Locus Type`, `## Genius Loci`) — so you can try the basics with zero setup, via `-d/--dir` (an explicit filesystem path, no `~/.config/folk/collections` entry required):

```bash
folk -d examples/characters list                                # list people in a collection
folk -d examples/characters show toru-watanabe                   # show a person, tiered profile included
folk -d examples/characters link naoko toru-watanabe childhood-friend
folk -d examples/characters tag sheep-man recurring
folk -d examples/characters random                                # remember someone
folk -d examples/characters stats                                 # collection overview
```

`folk graph`, `folk lookup`, and `folk show locus:<slug>` read across every collection registered in `~/.config/folk/collections` (and the rebuilt triple index) rather than an ad hoc `-d` path, so trying those against the fixture data means registering `examples/characters` there first and running `folk index --rebuild` once. A collection's `loci/` subdirectory is picked up automatically as a Locus root. Once you've registered your own collections (see "Collections" below):

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

### Curation policy

By default a collection is `curation: "human"`: only a human creates person files there. A collection may place a `COLLECTION.json` in its own root to declare `{"curation": "agent"}`, which lets an automated process (the bulk importer, see below) create new person files in it. Any other content, a missing file, or malformed JSON resolves to `human`. The policy governs creation only: a human may edit any file in any collection at any time, and a file a human has edited is theirs from then on. Mechanism: `docs/design/collection-curation.md`.

```json
{"curation": "agent"}
```

## Storage model

Three records, one authority each — never make anything authoritative in two places.

| Layer | Authority | Format | Location |
|-------|-----------|--------|----------|
| Person files | What the human curated | Markdown, git-tracked | Collection dir (`{collection}/{initial}/{slug}/{slug}.md`) |
| Journal | What happened | Append-only NDJSON segments, never edited | Registered per-collection journal roots (`{collection-dir}/journal/YYYY-MM.{writer}.ndjson`) — no single global journal directory |
| Triple index | Derived cache | NDJSON | `~/.folk/triples.ndjson` — deletable and rebuildable at any time. Nothing under `~/.folk/` is authoritative: the review quarantine, the promotion state file and log, and the sibling `~/.folk-staging/` also live there, but they are host-local operational state, not a fourth record |

`folk index --rebuild` is the only thing that ever writes the index: it parses person files (human tier) and replays every journal segment (observed/stated/interpreted tiers, plus `bedrock` suggestions awaiting a human decision), deterministically. Run twice, byte-identical output — there is no LLM anywhere in this path.

## Commands

Global options: `-C, --collection <name>` (resolved from `~/.config/folk/collections`) and `-d, --dir <path>` (an explicit root, overriding `-C` and `$FOLK_DIR`). Run `folk <command> -h` for full options.

| Command | Description |
|---------|-------------|
| `list [--context <tag>] [--locus <slug>]` | List people, optionally filtered by tag or scoped to a Locus |
| `show <name>` | Show a person (or `locus:<slug>` for a Locus): archetype, voice, appearance, dates, defining moments, associations, media, and the tiered index profile |
| `lookup <name> [--json]` | Check whether a person matching the name already exists in any registered collection, before minting a new `person:` slug (for source adapters) |
| `render <name> [--format soul\|dream] [--checkpoint <name>] [--json] [--out PATH]` | Generate a persona view (SOUL.md) or dream JSON from a person file or Locus. Deterministic templating, no LLM. `card` and `yaml` are accepted but not implemented |
| `link <a> <b> <type>` | Bidirectional association, written to both person files |
| `tag <name> <tag>` | Add a tag |
| `random [--context <tag>]` | Pick a random person |
| `context [<name>]` | Show or set the active collection |
| `context-report <name>` | Generate a context report for a person |
| `stats` | Collection statistics |
| `graph [--person <slug>] [--depth N] [--context <tag>] [--locus <slug>]` | Emit a Mermaid graph over the triple index |
| `index [--rebuild] [--verify]` | Rebuild the triple index from person files + journal, or check for broken references |
| `surface [--locus <slug>] [--person <name> ...] [--budget N] [--now ISO] [--json]` | Bounded, ranked cross-context facts for session-start assembly. Read-only, no model call |
| `agenda [--within N] [--now ISO] [--json]` | Upcoming dated events (birthdays, anniversaries) across collections, soonest first |
| `focus [--locus <slug>] [--person <name> ...] [--collection <name>] [--budget N] [--json]` | Attention ranking of containers (people and Loci), using the same ranking engine as `surface` |
| `review [--interactive] [--json]` | Work the review queue: vocab proposals, entity near-duplicates, bedrock suggestions, lint failures |
| `promote [--cap N]` | Run the session-end promotion job once: extract → LLM-propose → lint → append or quarantine |
| `journal lint <segments...> [--transcript PATH] [--user ID] [--agent ID]` | Lint journal segment(s) against the schema, no LLM involved |

## Person file format

```markdown
# Toru Watanabe

Narrator and protagonist of Norwegian Wood.

## Archetype

quiet observer

## Voice

understated, first-person, wry

## Appearance

- build: narrow, stooped from years of reaching upward
- hair: cropped close, dark, kept short and plain

## Appearance: student years

- build: lean, restless, always a little underslept

## Dates

- birthday: 03-14

## Associations

- [Norwegian Wood](work:norwegian-wood) — appears_in

## Tags

character narrator

## Defining moments

- Leaves Tokyo to walk, alone, for weeks, after a loss.
```

Every `##` section is a convention, not a schema: folk parses the ones it knows and leaves the rest alone. `## Archetype`, `## Voice`, `## Appearance`, and `## Defining moments` are Bedrock, the same as `## Associations` and `## Tags` — only a human writes them. `## Dates` takes one `- label: MM-DD` or `- label: YYYY-MM-DD` line per date and feeds `folk agenda`. `## Media` lists references (an Immich, Plex, or local-path reference, with an optional note) and is displayed by `folk show`; folk stores no copies of media.

`## Appearance` takes one `- label: value` per line. The label set is open and unvalidated; conventional labels are `build`, `hair`, `face`, `dress`, and `distinguishing marks`. A `## Appearance: <name>` section records a state that is true at that checkpoint only, such as an age or a chapter. `folk render --checkpoint "<name>"` merges it over the base section; without `--checkpoint`, render uses the base only. Details: `docs/design/appearance.md` and `docs/design/appearance-checkpoints.md`.

## Locus Type

A Locus is a narrative place or an organization-like container (a department, a lab, a resource). Its file lives at `loci/<slug>/<slug>.md` under a collection root. A Locus file may carry a one-line `## Locus Type` section — for example `department`, `research-center`, `resource`, `lab`, or `narrative-place` — which is free text: folk does not validate or enumerate the values, and `folk show locus:<slug>` displays it. The design is in `docs/design/locus-type.md`; it is proposed and not yet confirmed by the maintainer.

## Bulk import

`folk/bulk.py`'s `import_batch()` is the library entry point for mechanical importers, such as an adapter that reads a public organizational directory. It appends `kind: observation` events under an `import:<name>:v1` actor, skips and reports records that fail rather than aborting the batch, and never runs a rebuild itself. When the target collection is `curation: "agent"`, the batch can also mint a person file for each new subject; in any other collection the mint is refused, and the event still appends. There is no `folk import` subcommand. `folk/sources/directory_scrape.py` is a generic adapter skeleton: its parser is implemented, and its fetcher is a documented stub, because reaching a live site needs a dependency this repo does not add. Design: `docs/design/bulk-import.md`.

## Identity resolution (open design)

`folk lookup` currently matches by exact slug or display name, and falls back to a token-overlap heuristic that flags near matches for a human. That heuristic is not enough for directory-scale imports (common names, name-order differences, repeat scrapes of the same person). `docs/design/identity-resolution.md` is an open design document, not implemented: it proposes exact-lookup anchors in person files and a set of named matchers, and it lists its open questions for the maintainer.

## Web UI (optional)

`web/` is an optional, deletable front end: a FastAPI and Uvicorn API, a Svelte UI, and a Docker Compose setup. It is a pure consumer of folk, imported in-process, and reads the same three records as the CLI. Its API covers collections, people, the ego graph, Loci, agenda, focus, the review queue, and staged person-file edits; writes go through git commits and journal events, never direct index writes. It is the one exception to the stdlib-only rule (invariant 8): its dependencies are listed under `web/` only, and folk core does not depend on it. Deleting `web/` leaves the CLI untouched. The views that are not built are deferred: the Corkboard and the Studio view. Design: `docs/design/web-ui.md`. Setup: `web/README.md`.

## Trust tiers

`folk show` groups facts by tier, derived at read time from who asserted it and how — there are no `conf` numbers to hand-tune:

1. **Curated** — you wrote this, in a person file.
2. **Observed** — mechanical record (e.g. a message was sent).
3. **Stated** — a direct statement, agent-recorded with a quote and a `src` pointer back to the transcript.
4. **Interpreted** — an agent's inference; verify via the `src` pointer.
5. **Bedrock suggestions** — proposed durable facts awaiting your decision in `folk review`; not fact until you accept them, and only ever land in a person file, never the index.

## Design

folk is Layer 0 of a larger persona-agent architecture, but this repo is self-contained and usable on its own. See `docs/design/` for the specs behind the current implementation (journal schema, review queue, session promotion, collections and graph, curation, web UI).

Key decisions:
- **Agency**: the system suggests, you decide. Only a human edits Bedrock (person files); nothing else is ever promoted into them automatically, and a machine may only create person files in a collection that opts in.
- **Files over databases**: person files are plain markdown, journal segments and the triple index are NDJSON (greppable, `jq`-compatible). No lock-in.
- **No media duplication**: folk references photos and videos where they already live (media library, photo server, local paths) and stores no copies. The `folk media` source commands are not built yet.
- **Perennial**: Python stdlib only, zero daemon dependencies, git-trackable.

## Development history

This repo's public history is a curated export from a longer private development history, grouped into milestone commits rather than replaying every incremental change — done deliberately before the first public push, to keep personal test data and infrastructure details that accumulate during private day-to-day use out of what ships here. `scripts/check_release_hygiene.py` is the checker that enforces this going forward for anyone contributing.
