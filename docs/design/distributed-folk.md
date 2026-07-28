# distributed folk — federation as a future direction (exploration, not a spec)

**Status:** EXPLORATION — written 2026-07-26. This is a parked future direction, not a build target and not on any task sequence. It exists so the idea is written down with its hard problems named, so a later design session starts from here instead of from scratch. Nothing in `web-ui.md` depends on this; the web UI is deliberately local-first and single-user precisely so this can be explored later without being on the critical path.
**Context:** `docs/design/web-ui.md` (Decision 5 — the local-first boundary this would cross); `docs/design/journal-schema.md` (the append-only per-writer log that turns out to rhyme with distributed-social-media substrates); `CLAUDE.md` invariants 1–6.

## The observation that started this

folk already has the shape of a distributed-social substrate, without anyone designing it that way:

- **Append-only, per-writer logs.** The journal is per-writer NDJSON segments, never edited, corrections-as-later-events. This is structurally the same as Secure Scuttlebutt's per-feed append-only logs and the AT Protocol's per-repo commit logs.
- **Content-addressed, verifiable events.** Every event has a deterministic `id` (sha256 over its fields); the index is a pure, reproducible projection. Replication and integrity checks are things you can build on content-addressing.
- **Local-first, no lock-in, deletable cache.** The person files are the human's own git repo; the index is throwaway. There is no server that owns the truth. This is the founding premise of the local-first / Fediverse / Nostr worlds.

So the question this draft parks: **what would it mean for many people, each running their own folk, to share the parts they choose about the connections between them?** "You and I both know Sam; we each keep our own folk; can my view of Sam benefit from yours, with consent, without either of us surrendering authority over our own record?"

## Prior art worth studying (when this is picked up)

- **Secure Scuttlebutt (SSB)** — the closest structural match: local-first, append-only per-identity logs, gossip replication, works offline. The mental model ("your log is yours; others replicate what you publish") maps almost directly onto folk's journal. Start here.
- **AT Protocol / Bluesky** — per-user data repos (signed, content-addressed commit logs) + separate indexing/aggregation services. The "your repo is authoritative, indexers are derived and swappable" split mirrors folk's "person files authoritative, index derived." The federation-with-portable-identity model is the most mature.
- **ActivityPub / Fediverse (Mastodon)** — server-to-server activity delivery. Less structurally aligned (it's message-passing between instances, not log replication), but the largest live network and the standard people mean by "federated."
- **Nostr** — simplest: signed events, relays as dumb replicators, identity is a keypair. The "events are portable, relays are interchangeable" ethos is close to folk's "index is a deletable cache." Good for the minimal end of the design space.

## The hard problems (why this is parked, not built)

Federation is not the hard part — folk's substrate is already most of the way there. **Consent and privacy are the hard part, and they are unsolved here:**

1. **Facts about people are other people's personal data.** folk's whole discipline (the "no real names in the repo" rule, the counterparty memory-poisoning containment) exists because a record *about* a person is sensitive. Publishing or gossiping it multiplies that. The unit of sharing cannot be "my folk"; it has to be a consciously-curated, per-relationship, per-fact export — and designing that consent model is the actual work.
2. **Whose authority governs a shared connection?** Invariant 1 (one authority per record) is clean for one person's folk. Across two people who both know Sam, "the connection" has two authors with two views. Federation must not quietly make one person's view authoritative over another's, or create a third shared store (also an invariant-1 violation). Likely answer: each person's folk stays sole authority over *their own* record; a peer's contribution arrives as — at most — a new *observed/stated*-tier journal event attributed to that peer as `counterparty`, subject to the same review-queue containment as any other external input. Federation would then be "a new source adapter that happens to be another human's folk," not a new authority model. That framing is promising and worth pressure-testing first.
3. **Poisoning surface.** Every containment rule folk has (lint before append, counterparty items reviewed one at a time, never batch-accepted) exists because external text is adversarial-by-default. A peer's feed is external text. Federation inherits *all* of that containment and adds trust-graph questions (who do you replicate? transitively?) on top.
4. **Redaction across replicas.** The one sanctioned "forget" path (`kind: redaction` + sealed-segment purge) is hard enough locally. Once an event has been gossiped to peers, local redaction can't reach it — the SSB "you can't unpublish" problem. A consent model has to treat sharing as irreversible and design for that up front.

## The through-line to keep

If this is ever built, the invariants are the thing that makes folk *worth* federating rather than just another social app: **local-first authority, derived-and-deletable indexes, trust as a read-time tier, and human-in-the-loop containment for everything external.** A federated folk that kept those would be a genuinely different point in the design space from the ad-driven or server-authoritative networks — closer to SSB/AT Proto's values, grounded in the concrete daily use of "remember your people." A federated folk that dropped them would just be a worse Mastodon. The point of writing this down now is so that, when the time comes, the design starts from the invariants and treats consent as the central problem — not as a feature to bolt on after the replication demo works.

## Not now

No task, no code, no dependency, no schema change. Parked deliberately. The web UI (`web-ui.md`) is single-user and local-first specifically so that shipping it commits us to none of this — federation can be explored on its own timeline, from this starting point, whenever it earns priority.
