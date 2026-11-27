# `folk surface` — cross-context relevance as session-start assembly (Phase 2)

**Status:** confirmed by the maintainer 2026-07-22 — full text reviewed and holds. Read-only command; no invariant or schema change. This spec also records the resolution of `folk-render.md` Decision 3's checkpoint condition (see "Consumers").
**Context:** the wider persona-agent architecture design (Layer 2, Archivist function 2 "Surfaces"; Layer 5's Focus Engine; Known issue #3 — the "surfaces a forgotten connection" exit criterion was ruled a north star, not a testable gate); `docs/design/loci.md` (locus scoping, `folk focus` deferred here); `docs/design/decay-and-supersession.md` (the staleness lens and `reinforce_count`/`superseded_by` index fields this consumes); Woven Imprint's Reciprocal Rank Fusion (the ranker-combination pattern, taken without its semantic ranker).

## Why

The Archivist's surfacing is the piece RAG doesn't do: not "retrieve text matching a query" but "notice that something established in another context bears on this one." The architecture drafted it as interactive and mid-conversation — but the interaction surface that presumes is Phase 4's GUI, which doesn't exist. What exists today is **prompt assembly**: a Hermes session starts, something decides what context rides along. That is where surfacing can land now — a query answering "given this locus and these participants, what small set of cross-context facts should this session know?" — consumed by Hermes's session start the same explicit way `folk render` output is, and later by the GUI when there is one. Mid-conversation surfacing is a latency problem on top of the same query, deferred with it.

## Decision 1 — deterministic ranking only, RRF over four rankers

No model call anywhere — not generative, not embeddings (considered and deferred: semantic similarity via Ollama embeddings would be a third model-touching site and an untestable ranking input; it can be revisited as one more ranker if the deterministic four prove insufficient on real data, which the eval discipline from `promotion-eval.md` would show). The four rankers, each a total order over candidate triples computable from the index alone:

1. **Tier** — human > observed > stated > interpreted (the existing trust order).
2. **Recency** — rank by `last_reinforced` descending (a rank, not an age: no wall clock needed to order).
3. **Recurrence** — rank by `reinforce_count` descending (how many distinct source events asserted this triple — derived at rebuild, added to the index record per `decay-and-supersession.md`).
4. **Gravity** — rank by the graph degree of the triple's far entity (entities many triples touch are pillars; a candidate connecting the focus to a pillar outranks one connecting to a leaf).

Combined by Reciprocal Rank Fusion — rank-based, no tuned weights to drift. After fusion, two filters apply: `superseded_by` records are excluded outright, and `stale` records (per the staleness lens, with `--now` injectable for tests) are dropped to the bottom rather than excluded — a stale cross-context fact can still be exactly the forgotten thing worth surfacing, but it must never displace a fresh one within the budget.

## Decision 2 — the query: focus set in, bounded cross-context slice out

`folk surface --locus <slug> [--person <slug> ...] [--budget N] [--now ISO] [--json]`

The **focus set** is the entities the session is about: the Locus's own slice (its cast-list entities and locus-tagged triples' subjects/objects, via the machinery `loci.md` built) plus any explicitly named participants; `--person` without `--locus` is legal (a locus-less session still has participants worth briefing on). **Candidates** are index triples *adjacent* to the focus set — sharing an entity with it — that are **not already in the focus slice**: facts from other loci, other collections (respecting the existing cross-domain query flags), or unscoped history. In-slice facts are what the session already has by construction; surfacing is definitionally about what lies just outside.

Output is at most `--budget` items (default 12 — a briefing, not a dossier), each with a one-line mechanical reason: `person:mira — works_at studio-b (observed, reinforced 9×, last 2026-07-14, shared entity with locus:writing-room)`. `--json` emits the same ranked records for prompt assembly. Empty result on no qualifying candidates is correct behavior, not a failure — silence is the non-intrusive default.

## Decision 3 — surface proposes; nothing links, nothing writes

The command is read-only, absolutely: no journal events, no person-file edits, no "auto-link" of a surfaced connection (the architecture is explicit — the user links; the Archivist doesn't). A surfaced fact that deserves durability travels the existing paths: the human curates it, or conversation re-mentions it and promotion proposes it. This also means surfacing has no memory-poisoning surface of its own — it can only re-rank what already passed the journal's containment.

## Consumers — and the resolution of the `folk render` checkpoint

- **Hermes session-start assembly** (the Phase 2 consumer): a deploy-side step runs `folk surface --json` with the session's locus/participants and folds the result into the assembled prompt, exactly as explicit as piping `folk render` output — folk never assumes the Hermes filesystem.
- **`folk render`** — resolving Decision 3's condition from `folk-render.md`, revisited now as Phase 2 design begins per its checkpoint: render stays Bedrock-only by default, permanently. A bounded Core-tier slice becomes available *only* behind an explicit opt-in flag (`--with-core N`), implemented as nothing more than a `folk surface` query with `N` as the budget and the person as the focus set, appended in its own clearly-marked section. Render grows no ranking logic of its own; if surfacing isn't built, the flag doesn't exist. Not part of this spec's v1 — it lands as a small follow-on once both commands are stable.
- **`folk focus`** (attention ranking over Scenes/Loci — momentum, gravity, recurrence) — deferred when this spec was written, per `loci.md`; **landed since** as `folk focus` (`folk/surface.py` `focus()`, `cli.cmd_focus`): it shares this scoring engine but ranks containers rather than triples, and it has nothing to rank until real Loci and locus-tagged sessions exist. Build it as a thin second caller of this engine when they do.

**Precondition worth naming for the whole phase:** every locus-shaped behavior here needs at least one real Locus file and a locus-declaring source adapter (declared, never inferred — `loci.md`'s rule). Creating the first Locus and wiring the Hermes adapter's `locus` declaration is a small human-involved setup step that should happen early in Phase 2, or this ships as dormant as task 5 did.

## Scope for v1

- The four rankers + RRF + staleness/supersession filters as a library function (`journal.surface(...)` or a new `folk/surface.py`), with focus-set expansion from loci machinery; `folk surface` CLI over it, `--json` included.
- `reinforce_count` in index records (specced with `superseded_by` in `decay-and-supersession.md`; whichever task lands first adds both).
- A planted-fixture test corpus: a shared entity spanning two loci that must surface; a disconnected fixture that must surface nothing.

**Deferred, deliberately:** embeddings or any model-derived ranker; mid-conversation invocation and its latency budget; `folk focus` (landed since, see above); render's `--with-core`; auto-linking in any form; GUI presentation (Phase 4 visualizes this query's output — glow and heat come later, the ranked list is the substance now).

## Exit criteria

Replacing the architecture's north-star criterion with testable gates, per Known issue #3's precedent:

- On the planted fixture (an entity established in locus A, session context in locus B), `folk surface --locus B` ranks the cross-locus connection within the top 3, with a reason line naming the shared entity; on the disconnected fixture it emits nothing and exits 0.
- Output is byte-identical across repeated runs against an unchanged index with a fixed `--now`; the budget is never exceeded; superseded records never appear; a stale record appears only when the budget isn't filled by fresher ones.
- In-slice facts (already reachable inside the focus locus) never appear in the output — surfacing returns only cross-context items.
- `--person`-only invocation works with no locus configured, so the command is useful before the first real Locus exists.
- No model call of any kind in the code path; no writes to journal, index, or person files; no new dependencies.
