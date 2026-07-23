# Decay and supersession — how index facts age (Phase 2)

**Status:** confirmed by the maintainer 2026-07-22 — full text reviewed and holds. **No change to `journal-schema.md`** — this spec deliberately encodes both mechanisms without touching the frozen event shape. The *index record* shape (defined in `journal-in-folk.md`, a derived cache) gains two optional fields; that is a rebuild-output change, not a schema event.
**Context:** the wider persona-agent architecture design (Layer 2, Archivist functions 3 "Decays" and 4 "Invalidates", including the 2026-07-19 corrections: decay must be type-aware, and "a contradicted fact isn't stale, it's superseded"); `docs/design/journal-in-folk.md` (`last_reinforced` — derived, currently unconsumed); `docs/design/review-queue.md` (the proposal flow Decision 4 extends); Zep/Graphiti edge invalidation (arXiv:2501.13956).

## Why

Two distinct ways a true-when-recorded fact stops deserving retrieval weight, and the consolidation literature's correction is that they must not share a mechanism: a fact nobody has mentioned in a year is **stale** (demote gently, type-aware); a fact contradicted by a newer same-slot fact is **superseded** (end its validity, keep the history). folk has the raw material for both — `last_reinforced` is already derived at rebuild, and re-observation already refreshes it — but nothing consumes it, and conflicting facts currently coexist in the index competing at equal weight forever.

## Decision 1 — decay is a read-time lens, never a job and never a write

The architecture doc says "decay is a scheduled job." In folk there is no legal write target for such a job: nothing but rebuild writes the index (invariant 2), journal events record what happened in the world (not the index's opinion of itself), and person files are human-only. More decisively: staleness is a function of *now*, and writing any wall-clock-derived value into the index would break byte-identical rebuild (invariant 4's testability bar). So decay is a **projection, exactly like trust tiers**: `staleness(triple, now)` computed at read time by whoever is reading, from `last_reinforced` and the predicate's stability class. No job, no writes, nothing to drift, and "demoted, not deleted" holds trivially because nothing was ever mutated.

Concretely: `journal.staleness(record, now)` → `fresh` | `aging` | `stale`, a pure function with `now` injected (testable with a fixed clock, like everything else). Consumers apply it as they see fit: `folk show` annotates stale triples in the tiered profile, `folk surface` (its own spec) downweights them, `folk render` is unaffected (Bedrock-only, and person-file facts don't decay).

## Decision 2 — type-awareness lives in `vocab.json`, opt-in

A new per-predicate attribute, `stability: identity | situational`, in `vocab.json` — config, never code, per invariant 7's spirit, editable by hand or through the existing vocab-review flow. `identity` predicates (`born_in`, `created_by`) never go stale; `situational` ones (`works_at`, `interested_in`) do. **Unclassified predicates are exempt from decay** — classification is opt-in, so nothing silently demotes before a human has said the predicate is the demotable kind (the literature's failure mode is uniform decay erasing stable facts; the safe default is no decay, not default decay). Age thresholds for `aging`/`stale` live in a small `decay` block in `vocab.json` alongside the predicates, one pair of durations for the `situational` class — not per-predicate tuning until real use demands it.

## Decision 3 — supersession is a rebuild-time projection, driven by a `functional` predicate attribute

The maintainer's steer was "encode supersession within the existing review-event shape if possible." Working it through, even a new `verdict` value turns out unnecessary — **supersession needs no journal event at all.** The human judgment involved ("can this predicate hold only one value at a time?") is a property of the *predicate*, not of each fact-pair, so it's encoded once, in `vocab.json`: `functional: true` on single-valued predicates (`lives_in`, `works_at`; contrast `interested_in`, which is many-valued and can never supersede). Rebuild then derives supersession deterministically:

- **Slot:** among indexed triples sharing `(s, p)` in the same collection scope, where `p` is `functional: true` in vocab.
- **Winner:** the triple with the latest time anchor — `when` if present, else the source event's `ts`; person-file triples anchor at their curation (they win by tier anyway, see the guard). If the top anchors tie exactly, nothing is superseded — ambiguity is preserved, never resolved by a hash tiebreak.
- **Tier guard:** a fact can only be superseded by a fact of **equal or higher trust tier**. An `interpreted` guess never ends the validity of an `observed` record, and **human-tier facts are never superseded at rebuild** — the person file is ended only by the human editing it. (A newer journal fact conflicting with a person-file fact is still individually visible in the tiered profile drill-down — the human sees the tension; the machine doesn't resolve it.)
- **Output:** the losing record stays in the index — history preserved, Zep's end-of-validity pattern — with a new optional field `superseded_by: <event-id>` (the winning journal event's `id`; or the literal `"human"` when the winner is a person-file triple). Deterministic, so byte-identical rebuild holds.

Default query behavior: `folk show`'s tiered profile lists superseded triples only in a collapsed "superseded" subsection (they must not read as current facts), `folk graph` and `folk surface` exclude them, drill-down always reaches them.

## Decision 4 — the review queue proposes *classification*, not per-fact verdicts

The promotion-time "conflict detected → queue an invalidation proposal" flow from the architecture doc collapses into something cheaper: when rebuild (or lint) finds same-`(s,p)` triples with differing `o` on a predicate that is **not** classified functional, that's a signal the classification question is live — surface it in `folk review` as a vocab-shaped proposal ("`works_at` has conflicting values for person:sam — classify as `functional: true`?"). Accepting updates `vocab.json`; the next rebuild supersedes. One human decision per predicate, flowing through the existing vocab-proposal machinery — no new queue item type, no new event kind. Rebuild's stats line reports the supersession count so a surprising jump is visible.

## Scope for v1

- `stability`, `functional`, and the `decay` thresholds block in `vocab.json` (documented in its comments/README, seeded for the handful of live predicates by hand with the maintainer).
- `journal.staleness(record, now)`; `folk show` annotation of stale triples.
- Supersession pass in `replay()`/`rebuild_index()`; `superseded_by` and (from the surfacing spec's needs) `reinforce_count` as optional index-record fields; query-default exclusions; rebuild stats line.
- The conflicting-values classification proposal in `folk review`.
- Tests: fixture with two `works_at` facts → older gains `superseded_by`, rebuild byte-identical twice; unclassified predicate → coexistence untouched; human-tier fact never superseded by any journal fact; exact-tie anchors → no supersession; staleness pure-function behavior under a fixed `now`; no wall-clock value anywhere in any index record.

**Deferred, deliberately:** per-predicate decay thresholds; any materialized decay state; `guest_of` pattern proposals ("person:Y has appeared in locus:X in N sessions") — still deferred from `loci.md`, and blocked on a real design question this spec intentionally does not solve: a rejected *pattern-derived* proposal has no journal event `id` for a review event to `ref`, so rejection can't currently be recorded without bending the ref semantics. Solve that when loci are live and the pattern has data to fire on.

## Exit criteria

- On a fixture journal with `works_at` classified functional and two dated facts, rebuild marks the older with `superseded_by` pointing at the newer event's `id`; running rebuild twice is byte-identical; `folk show` presents only the newer as current.
- The same fixture with `works_at` unclassified leaves both facts current, and `folk review` surfaces the classification proposal; accepting it and rebuilding produces the supersession.
- A person-file fact conflicting with a newer journal fact on a functional predicate is not superseded, at any evidence tier of the journal fact.
- `journal.staleness` buckets a `situational` triple as stale under an injected far-future `now`, leaves an `identity` and an unclassified triple fresh, and appears nowhere in rebuild's write path.
- No change to `journal-schema.md`; no new event kinds, fields, or verdict values; no new dependencies.
