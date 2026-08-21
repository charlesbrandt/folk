---
name: folk
description: Remember the people you know — CLI tool for tracking people, their media, conversations, and connections across collections (personal/work/fictional); person files as markdown with NDJSON triple index
---

# folk — Remember the People You Know

A UNIX-philosophy CLI tool for tracking people across collections (personal, work, fictional domains), their media, conversations, and the connections between them. Person files are plain markdown, git-tracked. Agent/tool memory lives in an append-only NDJSON journal. The triple index is a deletable, deterministically-rebuildable NDJSON cache. No lock-in, no daemons, stdlib only.

folk is Layer 0 of a wider persona-agent architecture, but the repo is self-contained and usable on its own — see the "Public-Facing Documentation Conventions" section below before writing anything meant to be read outside this repo.

## Quick Reference

| Property | Value |
|----------|-------|
| Repo | The repository root (this skill lives in `skills/folk/` alongside the code) |
| Config dir | `~/.config/folk/` — `collections`, `state`, `journal-roots`, `loci-roots`, `vocab.json`, `promotion.json` |
| Triple index | `~/.folk/triples.ndjson` — the only thing under `~/.folk/`, deletable and rebuildable at any time |
| Quarantine | `~/.folk/quarantine/` — batches that failed lint during promotion |
| Promotion state | `~/.folk/promotion-state.json` — idempotency record, one entry per processed session |
| Install | `pip install -e .` or `python3 -m folk` (stdlib-only, so `python3 -m folk` works with no venv) |
| Dependencies | Python 3.10+, stdlib only (invariant 8 — no new deps without the maintainer's sign-off) |
| Tests | `tests/` (`unittest`), all green — `python3 -m unittest discover tests` |
| Nightly promotion | Reference unit files in `deploy/` (see `deploy/README.md`); the concrete deployment is an ops concern, not part of this repo's install |

## Commands

| Command | Description |
|---------|-------------|
| `list [--context <tag>] [--locus <slug>]` | List people, optionally filtered by tag or scoped to a Locus |
| `show <name>` | Show a person: associations, tags, media, archetype/voice/defining-moments, and the tiered index profile |
| `lookup <name> [--json]` | Identity check across every collection before minting a new `person:` slug — exact match / near-match (flag for human) / new. For source adapters. |
| `render <name> [--format soul] [--out PATH]` | Generate a persona view (SOUL.md) from a person file — pure deterministic templating, Bedrock-only input, no LLM. Only `soul` is implemented; `card`/`yaml` fail cleanly. |
| `link <a> <b> <type>` | Bidirectional association, written to both person files, triggers a rebuild |
| `tag <name> <tag>` | Add a tag to `## Tags`, triggers a rebuild |
| `random [--context <tag>]` | Pick a random person |
| `context [<name>]` | Show or set active collection (persisted to `~/.config/folk/state`) |
| `context-report <name>` | Generate a context report for a person |
| `stats` | Collection statistics |
| `graph [--person <slug>] [--depth N] [--context <tag>] [--locus <slug>]` | Mermaid graph over the triple index — ego graph, tag-filtered, or a Locus cast-list graph |
| `index [--rebuild] [--verify]` | Rebuild the triple index from person files + journal (deterministic, no LLM), or check for broken references |
| `journal lint <segments...> [--transcript PATH] [--user ID] [--agent ID]` | Lint journal segment(s) against the schema, standalone, no LLM |
| `review [--interactive] [--json]` | Work the review queue: vocab proposals, entity near-duplicates, bedrock suggestions, lint failures. `--interactive` shows exact diffs for person-file writes, no batch mode. |
| `promote [--cap N]` | Run the session-end promotion job once: extract → LLM-propose → lint → append-all or quarantine-all |
| `surface [--locus <slug>] [--person <name> ...] [--budget N] [--now ISO] [--json]` | Bounded, ranked cross-context slice of facts for session-start assembly — deterministic RRF over tier/recency/recurrence/gravity, no model call, read-only |

Global options: `-C, --collection <name>` (resolved from `~/.config/folk/collections`), `-d, --dir <path>` (explicit root, overrides `-C` and `$FOLK_DIR`).

## Collection Model

Physically separate directory trees, logically partitioned, selected by context. **Collections are config, never code** (invariant 7) — no collection name is ever enumerated in folk's source, so adding a domain is a one-line change. `characters` and `authors` are real, seeded domain collections (task 1, `collections-and-graph.md`) built specifically so anyone can try every command without touching personal data — see the Quick start in `README.md`.

| Mechanism | Example |
|-----------|---------|
| `--collection` flag | `folk -C characters list` |
| `--dir` flag | `folk -d ~/people list` |
| `$FOLK_DIR` env var | `export FOLK_DIR=~/work/people` |
| `folk context <name>` | Persisted to `~/.config/folk/state` |

Configured at `~/.config/folk/collections` (JSON):

```json
{"personal": "~/people/personal",
 "characters": "~/notes/fiction/characters",
 "authors": "~/notes/fiction/books/authors",
 "musicians": "~/notes/music/people"}
```

Real people and fictional people are never merged into one collection — cross-domain connections (a character `appears_in` a book, an author who `created_by` it) are edges in the graph, not shared files. An entity spanning two collections gets one canonical person file and a symlink from the secondary collection, never two files — `folk lookup "<name>" --json` is how an adapter checks before minting a new slug.

## Person File Format

```markdown
# Toru Watanabe

Narrator and protagonist of Norwegian Wood.

## Archetype
quiet observer

## Voice
understated, first-person, wry

## Appearance
- build: narrow, stooped from years of reaching upward
- hair: cropped close, gone grey at the temples

## Associations
- [Norwegian Wood](work:norwegian-wood) — appears_in

## Tags
character

## Defining moments
- ...
```

Every `##` section is a convention, not a schema — folk parses the ones it knows (`Associations`, `Tags`, `Media`, `Dates`, `Archetype`, `Voice`, `Appearance`, `Defining moments`) and leaves the rest alone. `Archetype`/`Voice`/`Appearance`/`Defining moments` are Bedrock tier, same ownership rule as `Associations`/`Tags`: only a human writes them, and `folk review`'s bedrock-accept path is a typist, not an author — it shows the exact diff and asks.

### `## Appearance` — durable physical description (`docs/design/appearance.md`, landed 2026-08-12)

One `- label: value` per line, order preserved. **The label set is open and folk never validates it** — no label name appears anywhere in folk's code (a test enforces this), because the alternative is folk owning a taxonomy of bodies and `gait` becoming a code change. Conventional labels, guidance only: `build`, `hair`, `face`, `dress`, `distinguishing marks`. Unlabeled prose in the section is not an error — it lands in a free-text `note` and still reaches consumers, just not addressable by field.

What goes here versus what stays with the consumer is **not** "physical vs. not" — it is *does this change between two frames of the same piece*. Durable (folk's): build, height, face, hair, marks, and characteristic dress when the dress is genuinely part of the identity. Staging (the project's): posture, expression, per-piece wardrobe, and negative prompt hints. A uniform worn for thirty years is folk's; what someone wore to the beach in frame 04 is the frame's. That line is what keeps a folk brief safe to inherit into every project referencing the slug.

Honest limit, worth repeating to anyone who asks for this: **consistent text is not consistent likeness.** The same clauses in twelve prompts give twelve related-looking strangers. Face-level consistency needs a reference image, a trained embedding, or a pinned seed — all rendering-side, none of it folk's. What this buys is one brief every consumer starts from, so drift comes from the model rather than from twelve writers describing the same figure twelve ways.

There is **no per-collection gate** on emission: if a human wrote it, `folk render` emits it, from every collection. Which collection a figure lives in is already the human's statement of what that figure is for, and duplicating that intent in a flag would just create two things to disagree. This is scoped to prose — reference images would reopen the question from scratch. A **Locus** file (a narrative place, e.g. `loci/murakami-world/murakami-world.md`) uses the same parser plus one more section, `## Genius Loci` (mood, rules, voice for the place itself).

### `## Appearance: <name>` — concurrently-valid checkpoint states (`docs/design/appearance-checkpoints.md`, landed 2026-08-21)

For a subject with more than one permanently-true appearance state — a character at seven and at seventeen, both true forever, neither superseding the other — a `## Appearance: <name>` section (same `- label: value` syntax as the base) states what's true *at that checkpoint only*. This is not history (git already owns what used to be true and no longer is); it's simultaneous multiplicity, and the test is "did the earlier value stop being true?" — if yes, edit the file, git holds the past; if both are still true, this is the tool. A checkpoint name is opaque and unenumerated by folk (same invariant-7 reasoning as labels themselves): `age 7`, `chapter 1`, `winter` are all equally valid, and no name may appear anywhere in folk's code. `folk show` lists available checkpoint names but never their contents or a merge, matching `--format dream`'s own no-implicit-merge rule. `folk render --format soul|dream <ref> --checkpoint "<name>"` merges that checkpoint over the base — base labels first in file order, a label the checkpoint restates overrides in place (keeps the base's position), a label new to the checkpoint appends — and fingerprints the merged text, so a graded render can be attributed to *which* checkpoint's brief produced it, not just which version. No `--checkpoint`: base only, never a default merge — merging every checkpoint would render a figure who is seven and seventeen at once, confidently. An unknown checkpoint is a hard error naming the ref and listing what does exist, never a silent fall-back to the base. The heading-suffix split (`## Section: qualifier`) is deliberately generic, not Appearance-specific, so a future `## Voice: <checkpoint>` needs no parser rework. Not built: any consumer-side change in the dream toolkit (its own repo), any comparison/ordering/interpolation over checkpoint names (interpolation is either a graded render, promoted by a human, or a proposed Bedrock text edit through `folk review` — never folk's own generative work), or any checkpoint-scoping of the top-level `description` field (a separate, still-open gap — see `docs/HANDOFF.md`).

## Storage Model: Three Records, One Authority Each

Never make anything authoritative in two places (invariant 1).

| Layer | Authority | Format | Location |
|-------|-----------|--------|----------|
| Person files | What the human curated | Markdown, git-tracked | `{collection}/{initial}/{slug}/{slug}.md` |
| Journal | What happened | Append-only NDJSON segments, never edited | Registered per-collection roots: `{collection-dir}/journal/YYYY-MM.{writer}.ndjson` — no single global journal dir |
| Triple index | Derived cache, nothing else | NDJSON | `~/.folk/triples.ndjson` |

`folk index --rebuild` is the *only* thing that ever writes the index (invariant 2) — it parses person files (human tier) and replays every journal segment across every registered root (observed/stated/interpreted tiers, plus `bedrock` suggestions awaiting a human decision in `folk review`), deterministically. Run twice, byte-identical output — no LLM, no wall clock, no filesystem-order dependence anywhere in this path (invariant 4), and it's a hard test in `tests/`.

An index record:

```json
{"s": "person:sam", "p": "works_at", "o": "org:studio-b",
 "tier": "observed", "col": "personal",
 "src": "msg:20260601_120000_ab12cd34#12",
 "when": "2026-05", "last_reinforced": "2026-07-14T03:11:02Z"}
```

## The Journal

`folk/journal.py` — event schema is normative in `docs/design/journal-schema.md`; `journal.lint_events`/`lint_paths` are its executable form, kept in agreement. Five event kinds, one line of NDJSON each:

| Kind | Written by | What it is |
|------|-----------|------------|
| `session` | extract step (mechanical) | One per processed conversation — marks it present, carries the `counterparty` list review filters on |
| `observation` | deterministic tools only | Mechanical record (participants, utterances, adapter exports). No LLM ever — that's what earns tier `observed`. |
| `promotion` | an LLM, as `agent:<name>` | A *proposal*, not an append — `evidence` (stated/interpreted) + `level` (core/bedrock), lint-verifiable. The only event kind an LLM produces anywhere in folk. |
| `review` | `human`, always | `verdict: accept \| reject` on the event `ref` points at — itself a journal event, so decisions are replayable |
| `redaction` | `human`, always | The one sanctioned exception to "nothing is forgotten," for privacy — expunges the ref'd event entirely at replay |

**Lint before append** (invariant 6): `journal.append_event(root, writer, event, run_lint=True, ...)` lints first; any hard failure raises `journal.LintError` and writes nothing. Lint checks schema shape, `id` recomputation (12 hex of sha256 over `ts|actor|s|p|o`), slug rules, resolvable `src` pointers, the 5-word shingle quote match, speaker attribution (a `stated` fact's subject must be the cited message's speaker — the fix for a real third-party-testimony bug landed 2026-07-19), and duplicate triples in a batch. Coined predicates and near-duplicate entity slugs are *soft* output (proposals for `folk review`), not errors.

**No `conf` numbers, ever** (invariant 5). Trust is a **tier** derived at read time from `actor` + `kind` + `evidence`: curated (human) > observed > stated > interpreted, with `level: bedrock` promotions floating outside the ladder entirely as suggestions until a human accepts them into a person file — `journal.person_profile()` returns exactly this, grouped by `journal.TIER_ORDER`, and is what `folk show` renders.

## Promotion & Review

Nightly, `folk promote` turns quiescent agent sessions into journal events: extract (mechanical, always runs) → LLM promote (temperature 0, proposals only) → lint (deterministic gate) → append-all or quarantine-all. *LLM proposes; script disposes.* Source adapters are pluggable (`folk/sources/__init__.py`'s contract: ordered, speaker-attributed messages, stable 0-based indices) — the primary implemented adapter ingests the agent runtime's session transcripts (`folk/sources/hermes.py`). A network-level model-provider failure defers the session (retried next run, no quarantine); a lint failure quarantines the whole batch to `~/.folk/quarantine/` and surfaces in `folk review`. The promotion job's concrete wiring (model provider URL, source profiles, session dirs, routing) lives in `~/.config/folk/promotion.json` and is an ops concern — see `deploy/` for the reference unit files.

`folk review` is where durability is actually decided: vocab proposals (into `vocab.json`), bedrock suggestions (into a person file, diff shown, always interactive, never batch), entity-resolution aliases (into `vocab.json`, merged at next rebuild), and quarantined lint failures. The queue is derived, never stored — an item is pending iff no `review` event resolves it. Sessions with an external `counterparty` are always reviewed one at a time, never batch-accepted — this is the containment boundary against memory-poisoning attacks (crafted text in a real conversation is still honestly `stated`; the review gate, not the tier system, is what stops it becoming durable unnoticed).

## Domains & Loci

Collections stay config-only even as new relationship types appear. A **Locus** (`docs/design/loci.md`, task 5) is a narrative place — built from two existing mechanics composed, no new schema: a person-like markdown file (`## Genius Loci`) plus a `locus` scope tag carried on journal events, stamped **mechanically by the source adapter, never inferred by the promotion LLM** (scoping is a trust decision, stays deterministic). The barrier is enforced on the Locus side: `folk show person:X`'s own profile is byte-for-byte unchanged by any guest appearance of theirs elsewhere. Crossing into a Locus once (a locus-tagged Scene) is ephemeral and leaves no cast-list trace; a curated `guest_of` edge in a file is the durable, human-decided wormhole. Registered via `~/.config/folk/loci-roots` or an auto-detected `loci/` subdirectory.

## folk render

Phase 1's first generated persona view: `folk render --format soul <person>` turns a person file into a SOUL.md by pure, deterministic templating — no LLM, byte-identical on unchanged input. v1 reads **only the person file** (Bedrock tier) — nothing observed/stated/interpreted leaks into a system prompt; deciding which machine-tier facts belong there is explicitly deferred to Phase 2 (the Archivist), revisit then, not before. Output goes to stdout or `--out`, never a default write path — a marker comment at the top warns "do not hand-edit," a convention not a lock.

## Decay & Supersession

Phase 2's second piece (`docs/design/decay-and-supersession.md`, task 8): two ways a true-when-recorded fact stops deserving weight, kept deliberately separate. **Staleness** is `journal.staleness(record, now, vocab)` — a pure read-time lens, `now` always injected, never called from `replay()`/`rebuild_index()`, so nothing wall-clock-derived ever touches the index. A predicate only decays if `vocab.json` opts it in as `stability: "situational"` (unclassified and `"identity"` predicates never go stale — safe default). **Supersession** is the opposite: a rebuild-time projection, gated on `functional: true` in `vocab.json` (single-valued predicates like `works_at`). Among triples sharing `(s, p, collection)`, the latest-anchored value wins the slot; every other non-human-tier, equal-or-lower-trust value gets `superseded_by` pointing at the winner's real event id (or the literal `"human"`). Human-tier facts are never superseded, exact anchor ties resolve nothing (ambiguity preserved, never hash-tiebroken) — both are exit-criteria-tested, not incidental. `folk show` collapses superseded records into their own section and marks `[aging]`/`[stale]` on current ones; `folk index --rebuild` reports the supersession count. When a predicate isn't yet classified and conflicting values show up, `folk review` surfaces a classification proposal (reuses the existing `vocab` item type, doesn't add a new one) — accepting it adds `functional: true` and the next rebuild supersedes.

## Cross-Context Surfacing

Phase 2's third piece (`docs/design/folk-surface.md`, task 9): `folk surface` answers "given this locus and these participants, what small set of cross-context facts should this session know?" — the Archivist function a plain RAG doesn't cover, landed as prompt-assembly input rather than the mid-conversation interaction the architecture originally drafted (that needs Phase 4's GUI, which doesn't exist). No model call anywhere, not even embeddings: four deterministic rankers over index triples — tier (trust order), recency (`last_reinforced`), recurrence (`reinforce_count`), gravity (graph degree of the triple's far entity, i.e. pillar entities outrank leaves) — combined by Reciprocal Rank Fusion, no tuned weights. The **focus set** is a Locus's cast-list entities plus any `--person`-named participants (built on task 5's `journal.locus_records()`, no new locus-scoping logic); **candidates** are index triples touching the focus set that aren't already inside it — in-slice facts never surface, since surfacing is definitionally about what lies just outside. Superseded records are excluded outright; stale records (task 8's lens) are demoted to the bottom of the ranking rather than dropped, so a stale cross-context fact can still be the forgotten thing worth surfacing but never displaces a fresher one within `--budget` (default 12). Absolutely read-only — no journal events, no person-file edits, no auto-linking; a surfaced fact earns durability the same way any fact does, curated by a human or re-promoted from a re-mention. `--person`-only works with no Locus configured, so it's useful before any real Locus exists.

## Project Status

Tasks 1–6 (foundation + Phase 1) are implemented and tested: collections+graph, journal/lint/rebuild, review queue, nightly promotion, Locus, and render. Phase 2 (the Archivist) is implemented in code: promotion eval (task 7), decay/supersession (task 8), and cross-context surfacing (task 9). Two things remain ops/config, not code: task 8's real `stability`/`functional`/`decay` classifications for folk's live predicates still need seeding on the actual `~/.config/folk/vocab.json` with the maintainer (only the mechanism was built, against synthetic fixtures), and task 9's locus-shaped behaviors need a real Locus file plus a locus-declaring source adapter before they're exercised outside tests (`--person`-only works today regardless). Full history, task-by-task implementation notes, and escalation guidance: `docs/HANDOFF.md`. Reader-facing summary with diagrams: `docs/site/` (`phases.html` in particular).

## Files

| File | Purpose |
|------|---------|
| `folk/cli.py` | argparse entry point, all subcommands |
| `folk/config.py` | Collection/state/journal-root/loci-root/vocab resolution |
| `folk/person.py` | Person (and Locus) file CRUD, section parsing, stats |
| `folk/triples.py` | Triple index read/write (rebuild-only writer) |
| `folk/journal.py` | Event `id`/lint/append/replay/rebuild, `person_profile` tiering |
| `folk/review.py` | `folk review` queue logic and interactive accept/reject |
| `folk/promotion.py` | Nightly promotion pipeline (extract → LLM → lint → append/quarantine) |
| `folk/sources/hermes.py` | Primary session-transcript adapter (only implemented source) |
| `folk/render.py` | `folk render` deterministic templating |
| `folk/locus.py` | Locus file support, barrier logic |
| `folk/graph.py` | Mermaid graph emission |
| `folk/surface.py` | `folk surface` — four-ranker RRF cross-context query |
| `~/.config/folk/collections` | Collection name → path mapping |
| `~/.config/folk/journal-roots` | Explicit journal-root registration (auto via `journal/` subdir otherwise) |
| `~/.config/folk/loci-roots` | Explicit Locus-root registration |
| `~/.config/folk/vocab.json` | Predicate vocabulary, `aliases` (entity-resolution), `stability`/`functional` predicate attributes |
| `~/.config/folk/promotion.json` | Promotion job config (source profiles, cap, model, provider URL) |
| `~/.folk/triples.ndjson` | Derived triple index, rebuild-only |
| `prototypes/journal-promotion/` | Reference implementation for the journal/promotion pipeline — read its `README.md`/`COMPARISON.md` before touching journal code; its quirks were each earned by a real failure |

## Typical Usage Patterns

```bash
# Try it without touching personal data (seeded domain collections)
folk -C characters list
folk -C characters show toru-watanabe
folk -C characters graph --person toru-watanabe --depth 2
folk lookup "toru watanabe" --json          # exists already? checks every collection

# Daily: remember someone
folk random
folk -C work list

# Connect and categorize
folk link jess_frazelle marie-drake colleague
folk tag marie-drake writer

# Journal-backed work
folk journal lint path/to/segment.ndjson --transcript session.jsonl --user person:sam --agent agent:assistant-main
folk review --interactive                    # work the queue, diffs shown for bedrock accepts
folk promote --cap 5                         # run promotion once, capped
folk index --rebuild                         # after any manual journal edit or migration
folk index --verify                          # check for broken references

# Generate a persona view
folk render --format soul jess_frazelle --out /tmp/SOUL.md

# Cross-context briefing for session-start assembly
folk surface --locus writing-room --person jess_frazelle --budget 8 --json

# Switch contexts
folk context work
folk random                                   # from work collection now
folk context personal
```

## Web UI (`folk web`)

`docs/design/web-ui.md`; code lives in `web/` (FastAPI + Uvicorn API, Svelte 4 + Vite UI), a pure in-process consumer of the `folk` library — adds no dependency to folk core itself (invariant 8 stays satisfied). Launch:

```bash
cd web
docker compose up --build          # API :8500, UI dev server :5175
```

or without Docker: `cd web && uvicorn api:app --reload --port 8500` in one terminal, `cd web/ui && npm run dev` in another. The container's bind mounts must land at *identical absolute paths* inside the container — folk's `config.py` resolves via `Path.home()` and `collections.json` stores absolute host paths, so path identity has to survive the container boundary. Confirm health with `docker compose ps` and `curl localhost:8500/status` / `curl localhost:8500/collections`.

**Healthcheck gotcha (found 2026-08-01):** the `ui` service's Docker healthcheck used `wget --spider`, but the `node:20-slim` base image doesn't ship `wget` (or `curl`) — the healthcheck failed every cycle (`FailingStreak` climbing in `docker inspect --format='{{json .State.Health}}'`) even though the Vite dev server itself was up and answering `curl` from the host with `200`. `docker compose ps` alone reports "unhealthy" forever without explaining why — the actual signal is in `docker inspect`'s health log, not the compose status line. Fixed by swapping the healthcheck for a Node one-liner, since `node` is the one binary guaranteed present in a `node:*-slim` image: `["CMD", "node", "-e", "require('http').get('http://localhost:5175', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"]`. Worth checking for the same pattern in any other `*-slim`-based compose healthcheck before trusting a "healthy"/"unhealthy" status at face value.

## Proposed Consumer: a dream-generation project (`folk render --format dream` landed 2026-08-12)

A separate creative project sources its characters and settings from folk rather than growing its own cast schema — its frames reference `person:<slug>` and `locus:<slug>`, resolved through `folk render --format dream` (deterministic templating, same Bedrock-only rule as `soul`). Rendering-only fields it needs (negative prompt hints, reference-image weights) stay on its side as an overlay, since they mean nothing to folk. Plan and decisions: the design docs in the sibling project's toolkit repo (`docs/design/folk-integration.md`); the shared-collection-descriptor question (folk currently has no `visibility`/`policy` concept, which the dream project does) is addressed alongside it.

Decisions as of 2026-08-09:

- **Archetypes stay local cast.** Single-project archetypal figures live in the dream project's own `cast/`, never in folk. Only identity-bearing, cross-work-reusable figures get a folk person file.
- **folk entities are reference-only.** A drafting model may freely mint *local-cast* figures (the unvetted nursery); `person:`/`locus:` refs resolve from folk, and graduation into a folk person file is a human act. No machine may create folk entities.
- **New `dreams` folk collection** for dream figures and loci — not scattered into `characters`.
- **Loci stay pure** — no dream-side overlay for locuses.
- **Gate covers compiled prompts**, so a folk edit shows up as an out-of-date prompt via the compile `--check`.

**Landed 2026-08-12:** `folk render --format dream <person:slug|locus:slug> [-C <collection>] --json [--out <path>]` — a JSON descriptor (`kind`, `slug`, `name`, `description`, `tags`, `associations`, and, for a person, `defining_moments`) built the same way `--format soul` builds its markdown: pure templating over the person/Locus file, no LLM call, deterministic on unchanged input. Without `--json` it prints the readable `description` text alone. A `locus:` ref resolves via `config.load_loci_roots()` and ignores `-C`/`--dir` (loci are not scoped to a person collection). See `folk/render.py` (`render_dream`, `render_dream_json`) and `tests/test_render.py`'s `TestRenderDream*` classes for the exact contract. This closes out `folk-integration.md`'s work-order item 2 on the dreams side; `dreamkit/folkref.py` there already shells out to this exact command.

**Landed 2026-08-12 (appearance):** the dream JSON descriptor gained three additive keys after `description` — `appearance` (the structured `[{label, value}]` list), `appearance_text` (the same content deterministically flattened: pairs as `label: value` joined with `; `, then the free-text note as its own clause), and `appearance_fingerprint` (first 12 hex of sha256 over `appearance_text`, empty when there is no brief). `description` is unchanged — still bio + `Archetype:` + `Voice:` — so nothing double-prints and `folkref.resolve`'s existing contract checks still hold; a figure with no `## Appearance` returns `[]` / `""` / `""` and resolves fine. The consumer side has **not** been built: `dreamkit/frames.py` still folds only `description` into its `figure:` clause, so the fields are available and unread until that project reads them. The fingerprint exists so a render adapter records *which version of the brief* produced a given image without reimplementing the hash (`person.appearance_fingerprint`, one implementation, no drift).

**Landed 2026-08-21 (appearance checkpoints):** the dream JSON descriptor gained two more additive keys, right after `appearance_fingerprint` — `checkpoint` (the selected `## Appearance: <name>` state, `""` when none requested) and `checkpoints` (every checkpoint name the file has, in file order, always emitted so a consumer can enumerate without a second subprocess). `--checkpoint "<name>"` on `folk render` (either format) selects one; omitting it renders the base section alone, never a merge of all of them. See the Person File Format section above for the full mechanism. **Update, same day:** the dream toolkit's consumer side has also landed — `dreamkit/folkref.py::resolve` takes a `checkpoint` param and passes `--checkpoint` through to `folk render`, and a frame selects one per folk-backed cast member via new `cast_checkpoints: {<ref>: "<name>"}` frontmatter (`dreamkit/frames.py`, toolkit repo; see its `dream-draft` skill §5). Validated live, not just compiled: `books/ten-thousand-doors` frame 03 (a chapter-1 render of a seven-year-old character) had its 2026-08-18 hand-typed age/build/dress prose patch reverted and replaced with `cast_checkpoints: {person:january-scaller: "age 7"}`, then actually re-rendered on the GPU — the checkpoint-sourced render matched the correct child proportions the hand patch had achieved, with zero age cues left in the frame's own text. January's real person file had carried `## Appearance: age 7` inert since 2026-08-17, four days ahead of the parser that could finally read it — folk's "an unrecognized `##` heading is silently ignored, never an error" design is what made writing that checkpoint early safe.

**Tracking renders back to folk** is a source adapter on the *rendering* side, not folk machinery: mechanical actor `import:dream:v1`, `kind: observation`, triple `person:<slug> — depicted_in — dream:<project>`, `src: dream:<project>:<render-id>` (also the re-export dedup key), and `note` carrying the brief fingerprint. `depicted_in` is registered in `~/.config/folk/vocab.json` with `stability: identity` — having appeared in a piece never stops being true, so it must never decay. Not yet written; folk's half (predicate + fingerprintable string) is done.

## Media Sources (Not Yet Built)

Still backlog (see `todo.md`), unchanged since the journal-era work landed:
- `folk media <name> --immich` / `--local <path>` — media source adapters
- `folk discover-media <name>` — suggest untagged candidates for curation; whenever this gets built it should follow the agency principle and current architecture (suggestions the human decides on, likely as journal `observation` events, never index writes or `conf` numbers)

## Fiction Character Maps (book companion pattern, added 2026-08-02)

Mapping a book's cast/settings into `characters`/`authors`/loci as you read it, without spoiling yourself: person files and a Locus for the setting go in as normal (`docs/design/collections-and-graph.md`, `docs/design/loci.md`), but two more pieces make it spoiler-safe and multi-book-friendly.

- **Chapter-gated companion doc**, outside folk itself (e.g. `media/books/companions/<book-slug>.md` in the notes tree) — a narrative-order index of who/where is new *per chapter*, populated only up to the reader's actual progress. This is the thing the reader is allowed to open; folk's `show`/`graph` commands are the interface into the (also progress-gated) person files it points at.
- **A full spoiler-heavy index cached separately** (e.g. `media/books/companions/spoilers/<book-slug>.md`), built once by having an agent read the *rest* of the book in the background and produce a per-chapter character/locus list plus a full spoiler-tagged cast summary. This lets the map advance instantly when the reader reports progress — no re-reading, and the agent never has to summarize ahead-of-progress content live in the conversation where the reader could see it. Label the file and its containing folder unambiguously (`spoilers/`) and never paste its contents into a reply; only use it to derive the next slice of the non-spoiler companion doc and the next batch of person/locus files.
- **Per-book `--context` tag, not folder-per-book.** The person-file layout (`{initial}/{slug}/{slug}.md`) is deliberately the *one* layout across a collection (see Person File Format) — grouping by book would fight every command that walks `{collection}/{initial}/...`. Instead, tag every file belonging to a book with a slug (alongside the usual `character`/`locus`/`author` tag) and use the existing `--context` filter — `folk -C characters list --context <book-slug>` / `folk -C characters graph --context <book-slug>` zero in on just that book's cast across both `characters` and `authors`, the same mechanism `--locus` already uses. Scales to any number of books sharing the same collections with zero structural change.
- **Copyrighted source text stays out of git.** Pulling a book for processing (see the media/book-ingestion pipeline) and extracting chapter text is fine for a session's scratch space, but don't commit the book's own text into the notes repo — only the derived index (character names, one-line neutral descriptions, chapter numbers) is a note, not a copy of the work.

**Tags-parsing gotcha (found 2026-08-02):** `folk/person.py`'s `_parse_tags` only reads the *first non-empty line* of a `## Tags` section and space-splits it — a second line of tags is silently ignored (no error, no warning). Always write tags space-separated on one line: `character ten-thousand-doors-of-january`, not one tag per line. Caught by `folk list --context <tag>` returning nothing for a tag that was visibly present in the file. Worth a `folk index --verify`-time lint check (a `## Tags` section with more than one non-bullet line is always a mistake) if this bites again.

## Public-Facing Documentation Conventions (learned 2026-07-22)

`docs/site/` is a concept-documentation site (plain HTML + hand-authored inline SVG diagrams, styled by `folk.css`) that explains the design to a reader who hasn't read `docs/design/` — `index.html`, `three-records.html`, `trust.html`, `journal.html`, `promotion.html`, `domains.html`, `phases.html`. Every diagram is tracked in `docs/site/DIAGRAMS.md` (one row per figure, with a stated utility — no diagram ships without one). When writing or editing anything meant to be reader-facing (`docs/site/`, `README.md`), genericize:

- No real vault paths in examples — use illustrative-but-fake paths (`~/people/personal`, `~/notes/fiction/characters`) that still show the shape and flexibility of the collections config.
- No specific external tool/product names in examples — use generic role terms ("agents", "chat UI", "music library", "media server"). Keeps the docs from going stale as tools change.
- No internal machine codenames — say "server" to convey server-side vs. edge without exposing personal infra naming.
- No personal names in examples — use the placeholder person already established in the design docs and site (`person:sam`), not the author's own name.
- Avoid dramatic/anthropomorphic phrasing ("folk refuses to...") — prefer plain, precise verbs ("prevents", "avoids").
- Don't lean on the link to the larger persona-agent architecture unless it's actually load-bearing for the point being made — `docs/site/` is meant to read standalone.

This section governs `docs/site/`/`README.md` only — the rest of *this* skill file, and internal docs like `docs/HANDOFF.md`, should stay concrete and accurate about the real system since they're operational references, not public-facing copy. Motivation: see the "Extract folk for public release" note in `todo.md` — this repo may eventually go public, and keeping documentation decoupled from personal infra now avoids a bigger rewrite later.

**One exception that overrides "internal docs can stay concrete" — real third-party person names, never, anywhere in the repo (learned 2026-07-23).** Infra specifics (IPs, hostnames, tool names) are fine in `docs/HANDOFF.md`, `scripts/`, commit messages, etc. — that's operational history. A real person's name is not the same kind of fact: it's someone else's personal data riding along in code/docs that gets committed, pushed, and (per the public-release note above) may eventually be public, regardless of whether that person is the maintainer, a family member, or a name incidental to some other collection. Concrete incident: an external adapter script had been named after the real person whose collection it indexes, and that real name showed up in `scripts/migrate_legacy_index_triples.py`'s docstring/`--actor` example and in `docs/HANDOFF.md`'s task-2 migration note — fixed 2026-07-23 by swapping in a generic name (`extract:legacy-adapter`, "an external adapter script"). Before committing anything in `docs/`, `scripts/`, `tests/`, or code comments — including a *writeup of this very lesson* — check it doesn't embed a real name the same way — describe the *role* (an external adapter, a collection member) instead. This is stricter than the collections-config rule (invariant 7, no collection name in code) — this is about individual person names specifically, and it applies repo-wide, not just to `docs/site/`. `person:sam`/`person:jess_frazelle`-style example data already used elsewhere in this skill file and in `docs/design/` are the deliberately-seeded exception (public tech figures / an established placeholder), not a precedent for pulling in names from private personal or family collections.

## Design Note

Full original design rationale lives outside this repo (see the archived design note in the personal vault, and the persona-agent architecture doc that motivated the journal). Implementing agents start at `docs/HANDOFF.md`, not this skill and not the architecture doc — this skill is orientation, not the source of truth. For what the journal actually does today, `docs/design/journal-schema.md` and `docs/HANDOFF.md` are authoritative.
