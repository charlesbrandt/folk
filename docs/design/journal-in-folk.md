# Journal, replay, and lint in folk proper

**Status:** implemented 2026-07-19 (`folk/journal.py`; two lint-level adaptations were made during the port — no schema changes)
**Context:** the wider persona-agent architecture design ("The journal (working design)"); prototype at `prototypes/journal-promotion/` (its README and COMPARISON.md are required reading — the prototype is the reference behavior)

## Why

The prototype proved the three-record model end-to-end (person files = curated, journal = what happened, index = disposable cache), but it lives in standalone scripts against fixtures. This item makes it folk's real storage model: `folk index --rebuild` replays the real journal, lint runs before every append, and the trust tier replaces `prov`/`conf` in the index. Everything downstream (session promotion job, review queue at runtime, Phase 1's conversation write-back) sits on this.

## Layout

| Piece | Prototype | In folk |
|-------|-----------|---------|
| Journal segments | `prototypes/.../journal/*.ndjson` | Registered journal roots, typically `<collection-dir>/journal/YYYY-MM.<writer>.ndjson` (see below) |
| Vocabulary | `prototypes/.../vocab.json` | `~/.config/folk/vocab.json` (human-curated → config dir) |
| Replay | `replay.py` | `folk/journal.py` + `folk index --rebuild` |
| Lint | `lint.py` | `folk/journal.py` lint, exposed as `folk journal lint`, and run automatically before any append folk itself performs |
| Index | `index.ndjson` | `~/.folk/triples.ndjson` (same file as today, new record shape). After this lands, the index cache is the *only* thing in `~/.folk/` — per the maintainer, it stays minimal |

**Registered journal roots — roots follow domain, not writer** (settled with the maintainer 2026-07-19, generalizing the digger community-layer doc's decision 4): there is no single `~/.folk/journal/`. A journal root is a directory of segments scoped to one collection, so agents acting in different domains (hermes-main talking with the maintainer → `personal`; a Cast character roleplaying → `characters`) write to different roots and domains never lump together. Two registration mechanisms: (a) automatic — a registered collection directory containing a `journal/` subdirectory is a root scoped to that collection; (b) explicit — `~/.config/folk/journal-roots` (JSON list of `{"path": ..., "collection": ...}`) for adapter-side roots that live next to their producer, like digger's segments next to its own database on that machine (reaching this machine as plain synced files; transport is an ops detail). A pleasant consequence of (a): collection trees that already live inside their own git repos give collection-side journal segments versioning and backup for free — no new infrastructure.

**Per-writer segments within a root** (`2026-07.laptop.ndjson`, `2026-07.desktop.ndjson`): the segment name carries a writer suffix so two machines or agents appending to the same root's month never touch the same file, and synced copies never conflict. Replay globs all segments across all roots; order within the merged index comes from `ts`, not file order. See `session-promotion-job.md` for how the promotion host's writes reach a root.

## Event schema (consolidate from the prototype)

The schema is frozen in `docs/design/journal-schema.md` — normative, with required-vs-optional per `kind`, the `id` computation, and the intentional divergences from the prototype (per-writer segments, `id`, `kind: review`, `locus`, `p_def`). Lint is the executable form of that document. The prototype's lint checks carry over intact: schema validation, src pointers must resolve, `stated` quotes verified by 5-word shingle match, speaker attribution (a `stated` fact's subject must be the speaker of the cited message), duplicate (s,p,o), slug rules, vocab proposals as soft output.

## Rebuild

`folk index --rebuild` = parse person files from all configured collections (human tier) + replay all segments across all registered journal roots (observed/stated/interpreted tiers, bedrock events → suggestions, review events applied, `kind: redaction` events expunge their `ref`'d event entirely per `journal-schema.md`) → write the index sorted and deterministic. Run twice: byte-identical. No LLM anywhere in this path. Readers follow the schema doc's weak-schema policy: unknown fields ignored, unknown `kind`/`v` skipped with a warning, never fatal.

**Index record shape changes** from `{s,p,o,prov,conf}` to `{s,p,o,tier,col,src,when?,last_reinforced?,note?}`. `col` is the collection scope inherited from the record's source — the person file's collection, or the journal root's registered scope. Query commands (`show`, `list`, `graph`) filter to the active collection by default, with a flag to cross domains — this is the muddying-prevention the maintainer asked for, enforced at query time while cross-domain edges remain representable. `triples.py`'s `conf`/`prov` writing goes away; anything that read `conf` reads `tier` ordering instead (human > observed > stated > interpreted). Migration is trivial by design: the current index was built from person files, so delete it and rebuild — that's the whole point of the cache. If any pre-journal machine-suggested triples exist that are worth keeping (check `prov` values in the live index first), convert them into journal events with a one-shot script; anything not derivable from person files or journal is deliberately lost.

**`last_reinforced`** is derived, not stored state: for each index triple, the max `ts` across all journal events asserting the same (s,p,o). Re-observing a fact in a later conversation refreshes it automatically. The Archivist's decay job (later phase) *reads* this field to demote stale triples in its outputs — it never writes the index directly, so the index stays a pure cache.

**Direct-write commands** (`folk link`, `folk tag`) keep writing person files as they do today — person files are the human tier's source, and rebuild picks the edits up. They should stop appending to the index directly (today's dual-write in `triples.py` becomes rebuild-only); until incremental rebuild exists, these commands can just trigger a rebuild, which is cheap at current scale (~16k triples).

## Entity resolution for object slugs

The vocabulary controls predicates but not object slugs, and the prototype's second pass showed the failure mode: `topic:local-history-stories` vs `topic:collecting-local-history-stories` — same referent, fragmenting the graph. Three-part fix:

1. **Prompt side** (lands with the session job): feed existing entity slugs of each type into the promotion prompt, same as predicates — prefer existing, coin only when genuinely new.
2. **Lint side:** flag near-duplicate slugs (normalized token overlap against known slugs; start crude, tune on real collisions) as *proposals*, not errors — same valve as vocab proposals, surfaced in `folk review`.
3. **Resolution side:** accepted mappings live in an `aliases` map in `vocab.json` (`"topic:local-history-stories": "topic:collecting-local-history-stories"`). Replay applies aliases when building the index. The journal is never rewritten — canonicalization is a rebuild-time projection, which is the same trick as everything else in this design.

## Out of scope

- The promotion LLM pass and its scheduling — `session-promotion-job.md`.
- `folk review` — `review-queue.md` (but land the `id` field here, since appends must carry it from birth).
- Incremental (non-full) rebuild — full rebuild is fine at current scale; revisit past ~1M events.

## Exit criteria

- The prototype scenario reproduced with folk commands against `~/.folk/`: segments in place, `folk index --rebuild` twice → byte-identical index; delete the index, rebuild → agent-written memories survive.
- `folk show sam` renders the tiered profile (Curated / Observed / Stated with quotes and src / Interpreted / Bedrock suggestions) from the real index.
- `folk journal lint` on a segment containing the prototype's known-bad event (stated quote in someone else's message) fails with the speaker-attribution error; on the clean LLM second-pass output it exits 0 with zero proposals.
- An alias accepted in vocab.json merges the two slugs' triples in the next rebuild, with the journal untouched.
