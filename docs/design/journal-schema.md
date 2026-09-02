# Journal event schema (frozen 2026-07-18)

**Status:** normative — the single authority for journal event shapes. Lint (`lint.py`, later `folk journal lint`) is the executable form of this document; if they disagree, fix whichever is wrong and say so in the commit. The other specs (`journal-in-folk.md`, `review-queue.md`, `session-promotion-job.md`) reference this file rather than restating fields.

One event per line, NDJSON, in per-writer monthly segments `YYYY-MM.<writer>.ndjson` inside a **registered journal root** — a directory scoped to one collection/domain, typically `<collection-dir>/journal/` (registration rules in `journal-in-folk.md`; there is no single global journal directory). An event's domain scope comes from its root, not from a field. Segments are append-only and never edited; a wrong event is corrected by appending a later event, never by rewriting.

## Fields

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `v` | integer | yes (from folk-proper onward) | Event schema version; `1` for this schema. Cheap insurance the event-sourcing literature says to buy before the second writer exists — versioned events + weak schema first, upcasting only if ever needed (arXiv:2104.01146). |
| `id` | string | yes (from folk-proper onward) | First 12 hex chars of sha256 over `ts\|actor\|s\|p\|o` (the literal `\|` as separator, empty string for absent s/p/o). Computed by the writer at append time; recomputable, so lint verifies it. |
| `ts` | ISO-8601 string | yes | When the event was recorded. Not the fact's own time — that's `when`. |
| `actor` | string | yes | Who wrote it: `human`, `agent:<name>` (e.g. `agent:hermes-main`), or a mechanical tool version (e.g. `extract:v1`, `import:digger:v1`). A *mechanical* actor is a deterministic, versioned tool with no LLM anywhere in its path — that determinism is what earns the *observed* trust tier; anything with an LLM in the loop must write as `agent:<name>`, never under a mechanical name. |
| `kind` | enum | yes | `session` \| `observation` \| `promotion` \| `review` \| `redaction`. See per-kind rules below. |
| `evidence` | enum | promotions only | `stated` (said directly — `note` must contain the verbatim quote) \| `interpreted` (a reading of the conversation). |
| `level` | enum | promotions only | `core` (ordinary durable fact) \| `bedrock` (identity-level — only ever a suggestion to the human, never indexed as fact). |
| `s`, `p`, `o` | strings | session/observation/promotion | Subject, predicate, object. Slugs are type-prefixed (`person:sam`, `topic:x`); the type prefix is lowercase ascii (controlled vocabulary), the slug body is hyphen-separated and Unicode-aware (any script's letters/digits survive diacritic-folding — see `docs/design/unicode-slugs.md`); predicates come from `vocab.json` or carry `p_def`. |
| `p_def` | string | when coining | One-line definition attached when the predicate is not in `vocab.json`. Lint files coined predicates as proposals for `folk review`, not errors. |
| `src` | string | stated promotions; recommended for interpreted; required for source-adapter events | Pointer to the event's source. Conversation sources: `msg:<session-id>#<index>` (0-based index into the transcript's user/assistant messages). Source adapters: an adapter-namespaced row pointer (e.g. `digger:play:12345`). For `stated`, the pointer must be a `msg:` pointer and lint verifies the quote appears in that message (5-word shingle) and that the fact's subject is the message's speaker — shingle verification applies to `msg:` pointers only. |
| `session` | string | conversation-source session/observation/promotion | `conv:<session-id>` — the conversation this event came from. Drill-down path from an index triple back to what was actually said. Absent on source-adapter events, which have no conversation (see "Source adapters" below). |
| `counterparty` | array of strings | session only, optional | Slugs of the non-agent parties in the conversation (`person:x`, or `unknown:<handle>` when unresolved). Derivable from observation events, but carried here so review tooling can filter without a join — promotions from external-counterparty sessions get stricter review defaults (memory-poisoning containment; see `review-queue.md`). |
| `locus` | string | optional | Locus scope slug, when the event belongs to a Locus (Layer 4; reserved now, used later). |
| `when` | string | optional | The fact's own time anchor (`2025-12`, `2026-05-14`) — distinct from `ts`. Include whenever the conversation dates the fact. |
| `note` | string | promotions: required; others: optional | For `evidence: stated`: the verbatim quote (plus optional gloss after an em dash). For `interpreted`: a summary; its audit trail is the `src` pointer. |
| `verdict` | enum | review only | `accept` \| `reject`. |
| `ref` | string | review/redaction | The `id` of the event being decided (review) or expunged (redaction). |

## Per-kind rules

- **`session`** — one per processed conversation, written by the extract step; carries conversation-level facts (e.g. `opened_on` → platform) and marks the session as present in the journal.
- **`observation`** — mechanical record (participants, utterances). Written only by deterministic tools (`actor: extract:v1`), no LLM. Utterance events (`p: uttered`) are journal-only — replay never indexes them; they exist for drill-down.
- **`promotion`** — an LLM's proposal that a fact deserves an index triple. Must carry `evidence`, `level`, `note`, and (for `stated`) a lint-verifiable `src`. `level: bedrock` events are surfaced by replay as suggestions, never as facts.
- **`review`** — a human decision (`actor: human` always). Resolves the event `ref` points at: accepted vocab proposals also land in `vocab.json`; accepted bedrock suggestions also land in the person file; rejected events' triples are dropped by replay. See `review-queue.md`.
- **`redaction`** — the one sanctioned exception to "nothing is ever forgotten" (`actor: human` always), for privacy: someone asked to be forgotten, or a segment captured something that must not persist. Replay excludes the `ref`'d event *entirely* — triples, drill-down, everything — unlike a reject, which drops triples but leaves the event readable. Live segments stay append-only; when a sealed segment is archived, an explicit purge step MAY rewrite it to blank the redacted events' content (tombstone stays, fields emptied) — the only permitted physical rewrite, and only on sealed segments.

## Source adapters (non-conversation writers)

Not every writer is transcribing a conversation. A **source adapter** (digger is the first — `~/repos/digger/docs/design/community-layer.md`; Immich/Plex/Calibre are the same shape) exports events mechanically from its own datastore. The general rules above already cover them; the specifics worth stating:

- Adapter events carry no `session`; their `src` is an adapter-namespaced pointer to the row that produced the event (`digger:play:12345`, `digger:search_attempt:87`). `src` is required — it is both the drill-down path and the adapter's idempotency identity (`id` hashes `ts`, which changes per run, so `id` is *not* a re-export dedup key; verifying the segment tail against `src` values is).
- A deterministic exporter is a mechanical actor (`import:digger:v1`) and its events are `kind: observation` — observed tier, no `evidence` field. This includes verbatim material (a search query string, a CSV row): observed already outranks stated, and stated's quote-verification machinery only exists because conversation promotions pass through an LLM. Adapter output that *does* involve interpretation (fuzzy cross-source merges, facts harvested from prose by an LLM) must be `kind: promotion` with `evidence: interpreted` under a non-mechanical actor, and queues in `folk review` like any other machine reading.
- **Repeated observations are legitimate, not duplicates.** The same `(s,p,o)` re-observed with a distinct `src` (a track played twice) is a re-observation — it refreshes `last_reinforced` at replay. Lint's duplicate-triple check is a hard error for promotions within a batch only.
- Adapters register their predicates and entity types in `vocab.json` before their first run (the digger doc's commitment 4); genuinely new terms flow through the proposal path.
- Before minting a new `person:{slug}` (identity minting, digger doc decision 2), an adapter can check `folk lookup "<name>" --json` — scriptable, checks every configured collection, returns an exact `match` (safe to reuse silently), `near_matches` (never auto-reuse or merge — the same token-overlap heuristic promotion-event review applies, surfaced earlier so an adapter can flag ambiguity itself), or neither (genuinely new). Backed by `graph.find_person()`.

## Reader policy (weak schema)

Readers (replay, lint, review tooling) MUST ignore unknown fields and tolerate absent optional ones; an unknown `kind` or unknown `v` is skipped with a warning, never a fatal error. This is what lets `v: 2` events coexist with `v: 1` readers during a migration instead of requiring a flag-day rewrite.

## Trust tiers (derived, never stored)

`human` (person files) > `observed` (mechanical observation events) > `stated` (promotion, `evidence: stated`) > `interpreted` (promotion, `evidence: interpreted`); `level: bedrock` promotions surface as *candidates* outside this ordering. There is no `conf` number anywhere in the journal or index.

## Divergences from the prototype (intentional)

- Prototype events have no `id`; folk-proper events must. A one-shot migration script may add `id` to the prototype segments (permitted only because they are pre-production).
- Prototype segments are per-month only (`2026-05-observations.ndjson`); folk-proper segments are per-month **per-writer** (`2026-05.desktop.ndjson`) so multiple machines never append to the same file.
- `kind: review`, `locus`, and `p_def` are additions this schema introduces; the prototype predates them.
- `v`, `counterparty`, and `kind: redaction` added 2026-07-19 (an earlier critical-review pass over the wider persona-agent architecture design); the prototype predates them too. Still `v: 1` — these are the first version's shape, not a bump, since no folk-proper events exist yet.
- Source-adapter generalization added 2026-07-19 (digger community-layer reconciliation): `session` scoped to conversation sources, `src` generalized to adapter-namespaced pointers, mechanical-actor definition tightened, duplicate-triple lint scoped to promotions. Also still `v: 1`, same reasoning.
