# Review queue — `folk review`

**Status:** spec, ready to implement (roadmap item 1 by priority; depends on `journal-in-folk.md`, which lands the event `id`, journal locations, and review-event replay this needs — that dependency landed 2026-07-19, see `docs/HANDOFF.md`'s task 2 section for the `journal.py` interfaces to build on, including `journal.person_profile`'s existing "unresolved bedrock candidate" logic this item's queue view can extend)
**Context:** the wider persona-agent architecture design ("The journal" + Known issue #5); prototype at `prototypes/journal-promotion/`

## Why

The journal design lets agents write freely because nothing they write becomes authoritative without a human decision. That only works if the pending decisions are *visible and cheap to make*. Today they accumulate in three places with no tooling: vocab proposals (lint output), bedrock suggestions (`level: bedrock` promotion events), and lint failures (quarantined promotion output, once the session job exists). `folk review` is the single place all of it queues — the keystone for the less-in-the-loop workflow.

The queue is also the **memory-poisoning containment boundary**. Query-only injection attacks (MINJA, arXiv:2503.03704: >95% injection success through ordinary conversation) poison an agent's session honestly — the crafted text really was said, so src lint passes and the trust tier is truthful about provenance while silent about manipulation. The last line of defense is that nothing enters the index as durable fact without passing here. Practical consequence: promotions whose session has an external `counterparty` (per `journal-schema.md`) should default to a stricter review posture — surfaced individually, never batch-accepted — while self-directed sessions can use lighter-touch batch flows.

## What queues here

1. **Vocab proposals** — a promotion event used a predicate (or entity type) not in `vocab.json`, with an attached `p_def`. Accepting adds it to `vocab.json`; rejecting means future lint files it as an error, and the coining event's triples are excluded from replay.
2. **Bedrock suggestions** — promotion events with `level: bedrock`. Accepting means the fact enters the person file (the only authority for Bedrock); rejecting records the decision so the suggestion stops resurfacing.
3. **Entity-resolution proposals** — near-duplicate object slugs flagged at lint time (see `journal-in-folk.md`). Accepting writes an alias mapping into `vocab.json`.
4. **Lint failures** — promotion output quarantined by the session job (see `session-promotion-job.md`). Shown for triage; the fix is usually editing nothing and discarding, occasionally re-running promotion.

## Design

**The queue is derived, never stored.** An item is pending iff it exists in the journal (or quarantine dir) and no review event resolves it. This follows the three-record rule: person files = curated, journal = what happened, index/queues = derived. No queue file to corrupt or drift.

**Events need identity.** To say "this decision resolves that event," events carry an `id` (defined normatively in `journal-schema.md`; landed by `journal-in-folk.md`).

**Decisions are journal events** — `kind: review` with `verdict` and `ref`, per `journal-schema.md`. Append-only like everything else, so the decision history is itself auditable and replayable. `replay.py` (later `folk index --rebuild`) consumes review events: an accepted bedrock suggestion stops being surfaced (the fact now lives in the person file); a rejected event's triples are dropped from the index.

**Accept side-effects by item type:**

- Vocab accept → append the predicate + definition to `vocab.json` (vocab.json stays the authority for the vocabulary; the review event is the audit record, not a second authority).
- Bedrock accept → offer to append a line to the relevant person-file section (`## Tags`, `## Associations`, or a `## Defining moments` bullet), show the diff, human confirms. The person file remains human-owned; the tool is a typist, not an author.
- Alias accept → add to the `aliases` map in `vocab.json`.
- Reject (any type) → review event only.

## Command surface

```
folk review              # list pending items, grouped by type, oldest first
folk review --interactive  # step through items: [a]ccept / [r]eject / [s]kip / [q]uit
folk review --json       # machine-readable pending list (for future UI)
```

Each listed item shows: the claim (s/p/o), the evidence tier, the verbatim quote or note, the src pointer, and — for vocab items — the proposed definition.

## Out of scope

- No web/TUI — terminal output only; `--json` is the hook for anything richer later.
- No batch auto-accept policies ("accept all stated facts from agent X"). Every accept is explicit until there's enough history to know what a safe policy looks like.
- Decay/staleness review — that's the Archivist's decay job, later phase.

## Exit criteria

- Running against the prototype's live data, the queue shows: the LLM's first-pass coined predicates, the radio-workshop bedrock candidate, and the known false-stated event (after it's quarantined by re-lint).
- Accepting the radio-workshop suggestion appends to `fixtures/mara.md` (confirmed interactively), writes a review event, and the item leaves the queue.
- Rejecting an item, then rebuilding the index, drops its triples; `folk review` shows an empty queue; a second rebuild is byte-identical.
