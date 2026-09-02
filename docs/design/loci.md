# `loci` — Locus collections, scoping, and cross-domain guests

**Status:** confirmed by the maintainer 2026-07-20. In `docs/HANDOFF.md`'s task sequence as task 5. Nothing here touches a CLAUDE.md invariant or the frozen journal schema.
**Context:** the wider persona-agent architecture design (Layer 4, "Locus ↔ folk mapping" — "a dedicated entity but not a dedicated type"; the five views, the Archivist's cross-Scene surfacing); `docs/design/journal-schema.md` (the `locus` field — reserved since v1, unused until this spec); `docs/design/collections-and-graph.md` (precedent for domain collections, config-only); `docs/design/journal-in-folk.md` (precedent this spec generalizes: registered per-domain roots, two registration mechanisms)

## Why

The architecture doc settled that a Locus is "two existing mechanics composed" — a person-like markdown file (identity, genius loci) and a scope tag carried on triples and journal events (`locus`, already reserved in the schema). That means loci is mostly wiring, not new design — but three questions were still open: whether entering a Locus is a hard boundary or a soft ranking signal, how an event gets tagged with a locus in the first place, and which of {file, journal, index} is authoritative for a Locus's contents. A fourth, practical question came up alongside them: where do Locus files actually live on disk. All four are resolved here.

## What a Locus is (no new machinery)

A markdown file with a `## Genius Loci` section (personality, mood, rules — per Aetheria), identified as `locus:<slug>` — one more entity type prefix alongside `person:`, `work:`, `topic:`. Scenes are `conv:` entities, unchanged, that carry the `locus` field on their journal events. Nothing new in the schema; this spec is about registration, scoping, and one new predicate.

## Decision 1 — default barrier, explicit wormhole

**Default: hard boundary by domain.** A Locus has a home domain — the collection its file lives in (see Decision 4). Locus-scoped queries (`folk show locus:X`, `folk list --locus X`, `folk graph --locus X`, and later `folk render`'s prompt assembly) admit only:
- journal events whose `locus` field matches, regardless of which collection the event's subject's home file lives in, and
- associations explicitly curated in the Locus's own file or a participant's file (`appears_in`, `guest_of` — see below).

A person's own default profile (`folk show person:Y`) is **never widened** by a guest appearance elsewhere — home-domain scoping for a person's default view is untouched by anything in this spec. The barrier is enforced on the Locus side, not the person side.

**The wormhole, in two forms — the tier split already used everywhere else:**
- **Ephemeral tunnel** (the common case — "wouldn't need to be permanent for every session"): a single Scene's events simply carry a locus tag outside the participant's home domain. Nothing gates this at write time (see Decision 2 — event tagging stays deterministic, no judgment call). The Scene shows up in that Locus's drill-down and its view. No standing relationship is created; the guest does **not** appear in `folk graph --locus`'s cast listing, because that reads curated associations, not raw journal events.
- **Durable tunnel:** a curated `guest_of` association (new open-vocabulary predicate, same mechanism as `mentor` or `created_by` — no schema change, just a vocab entry) written by the human into the Locus's file or the person's file. Bedrock tier, human-only, exactly like every other association. This is what makes a guest a recognized, ongoing Cast member across sessions. Natural promotion path (v2, not required for v1): the review queue proposes "person:Y has appeared in locus:X in N sessions — record as `guest_of`?" — same shape as an entity-near-duplicate proposal.

Net effect: crossing a domain boundary once is free and leaves no trace beyond that Scene; crossing it as a standing thing is a deliberate, human, file-level decision — the same "system suggests, you decide" posture as everything else in folk.

## Decision 2 — how an event acquires its locus

**Declared by surface**, not inferred. The source adapter (a Hermes profile bound to a Locus, an OpenWebUI folder, a manual `folk` invocation) stamps the `locus` field on the events it writes, mechanically — the same contract task 4's pluggable source adapters already expose. Locus assignment stays out of the promotion LLM's judgment entirely: a mislabeled locus is a scoping error, and scoping errors must stay in the deterministic part of the pipeline (same reasoning as `id` computation and src-lint — no LLM in a path that decides trust or visibility). This also means no gate is needed for cross-domain tagging: the surface either is or isn't bound to a Locus outside a participant's home domain, and that's a fact about the session, not a judgment call.

## Decision 3 — file vs. journal authority

Split along the existing three-records invariant, applied to loci instead of people:
- **The Locus's markdown file** curates its cast and pillar scenes as ordinary association edges — human tier, Bedrock. This is where "who's really in this Locus" lives, and only the human edits it.
- **Journal events** carry the scope tag — what actually happened there, mechanically recorded.
- **The index derives the union** at rebuild time, same as every other entity. `folk show locus:X` combines curated associations (file) with locus-tagged history (journal-derived index slice) into one tiered profile, using the same rendering `folk show person:X` already has.

Nothing authoritative in two places — same invariant, same guarantee.

## Decision 4 — where Locus files live

**Per-domain `loci/` subdirectories, mirroring `journal-in-folk.md`'s registered-roots mechanism exactly** (two registration paths, `config.load_journal_roots()` is the template):

1. **Automatic:** any registered collection directory containing a `loci/` subdirectory is a loci root scoped to that collection — e.g. `~/notes/fiction/characters/loci/murakami-world/murakami-world.md`. This gives every Locus physical proximity to the domain it's really about (a Murakami-flavored Locus sits next to `characters`; a life-planning Locus sits next to `personal`), without forcing every Locus into one folder.
2. **Explicit:** `~/.config/folk/loci-roots`, a JSON list of `{"path": ..., "collection": ...}`, for a Locus that's genuinely cross-cutting and doesn't want to nest under one existing domain.

`locus:<slug>` is addressed as one flat namespace across all registered loci roots, the same way `person:`/`work:` already resolve across collections — this isn't new resolution logic, it's the existing cross-collection graph traversal applied to one more entity type.

New in `folk/config.py`: `load_loci_roots()`, a near-literal copy of `load_journal_roots()` with `journal` swapped for `loci` and `JOURNAL_ROOTS_FILE` swapped for a `LOCI_ROOTS_FILE` constant (`~/.config/folk/loci-roots`).

**On-disk layout is flat — `{loci-root}/{slug}/{slug}.md`, no `{initial}/` subdirectory.** This differs from person files (`{collection}/{initial}/{slug}/{slug}.md`, `folk/person.py`), and the difference is easy to miss by pattern-matching against the more familiar person layout: `folk/locus.py`'s `_locus_files()` iterates a loci root's immediate children expecting each to *be* a slug directory, so a Locus file written at `{root}/d/department-name/department-name.md` (the person convention, with `d` as the initial) is invisible to `folk show locus:<slug>`, `folk graph --locus`, and index rebuild's locus-triple replay — silently, no error anywhere, on write or on read. A real deployment hit exactly this (iusm-directory, 2026-09-02): a hand-rolled department-locus minting helper copied the person-file layout, and 26 Locus files sat on disk, fully populated, completely unreadable by every folk command that reads Loci, until the layout was corrected. Anything that mints a Locus file outside `folk/locus.py` itself should either reuse a shared helper or be tested against `folk show locus:<slug>` immediately after writing, not just against the file existing on disk.

## Scope for v1

- `load_loci_roots()` in `folk/config.py`.
- Locus person files: `## Genius Loci` section convention, `locus:<slug>` identity, ordinary `## Associations` for cast (`appears_in`, `guest_of`).
- `folk show locus:<slug>` — tiered profile, reusing `journal.person_profile`'s rendering path (it's already keyed generically, not person-specific in name only).
- `folk list --locus <slug>` (Outline View) and `folk graph --locus <slug>` (Map View) — both apply the barrier from Decision 1.
- Locus tagging on journal events: verify the existing lint path does not silently drop the `locus` field (it's schema-legal today but unexercised) — no lint *logic* change expected, this is a verification step, not new lint.
- No new collection-name enumeration anywhere in code (invariant 7) — registering a new Locus, either mechanism, requires zero code changes.

**Deferred to follow-on specs, deliberately:**
- `folk focus` (attention scoring) — needs loci to exist first as its query scope; a natural first consumer of the currently-unconsumed `last_reinforced` field.
- `guest_of` review-queue proposal automation.
- `folk render`'s genius-loci prompt assembly (Phase 1) — same prompt-assembly machinery as SOUL.md generation; shouldn't be designed twice.
- Timeline, Corkboard, Studio views.

## Exit criteria

- A Locus file with a `## Genius Loci` section exists both in a domain-local `loci/` directory and via the explicit `loci-roots` registration; both resolve via `folk show locus:<slug>`.
- `folk list --locus <slug>` and `folk graph --locus <slug>` return only locus-tagged events and curated-cast associations — control test: a triple that exists for a cast member but is neither locus-tagged nor a curated association does not appear.
- An ephemeral guest Scene (an event tagged with an out-of-domain locus, no `guest_of` edge) shows up in the Locus's drill-down but **not** in `folk graph --locus`'s cast list; adding `guest_of` to the person's file makes them appear in the cast list on the next rebuild.
- `folk show person:<home-collection-member>` is byte-for-byte unchanged by any guest appearance of theirs elsewhere — no widening of a person's own default profile via a Locus.
- Nothing in code enumerates locus or collection names; registering a new Locus, either mechanism, requires no code change.
