# Session-end promotion job

**Status:** spec, ready to implement (roadmap item 4) — depends on `journal-in-folk.md` (schema, lint, per-writer segments) being landed, or at minimum its event schema being frozen
**Context:** the wider persona-agent architecture design (Layer 2 flow); prototype pipeline in `prototypes/journal-promotion/` (`extract_observations.py`, `promote_llm.py`, `lint.py`)

## Why

This is the step that turns the prototype into a living memory: real conversations flow into the journal without anyone running scripts by hand. After this lands, every processed conversation leaves (a) mechanical observation events and (b) linted, actor-stamped promotion proposals — and nothing else changes until a human reviews.

## Transcript sources are pluggable (clarified with the maintainer 2026-07-19)

Hermes is **not** structurally required in this loop — it is the first transcript source, not the only one. The maintainer also converses in OpenWebUI (and may adopt other surfaces); the journal must not care. The pipeline's front step is therefore a **source adapter** with a fixed contract: fetch a conversation and normalize it to *ordered, speaker-attributed messages with stable 0-based indices* (the `msg:<session-id>#<index>` pointer contract in `journal-schema.md` depends on those indices never shifting). Everything downstream — extract → promote → lint → append — consumes only the normalized transcript and never knows the source.

Per-source responsibilities: session id (namespaced so sources never collide — `conv:hermes-...`, `conv:owui-...`), `actor` (the agent profile for Hermes; for OpenWebUI chats there may be no persona-agent at all — the extract writer, e.g. `extract:v1`, is still the observation actor either way), `counterparty` on the session event (from source metadata), and the profile/chat → collection routing. Source #1 is Hermes session files (below). Source #2, designed but not built with this item, is an OpenWebUI adapter — fetch via its API (the `openwebui-chats` workflow already does this read) and normalize; it slots in as config + one adapter module, no pipeline changes. Build this item against the adapter interface even while Hermes is the only implementation — the subtle coupling to Hermes's session file format is exactly the kind of decision that gets amplified during implementation.

## Where it runs

On the promotion host: the session transcripts live there and so does the model (via Ollama, Hermes's own primary — confirmed usable for promotion in COMPARISON.md). The job writes host-local segments; the per-writer segment naming from `journal-in-folk.md` (`YYYY-MM.desktop.ndjson`) exists precisely so this machine can append without coordinating with any other writer.

**Routing — sessions land in the root of the domain the agent was acting under** (settled with the maintainer 2026-07-19): each Hermes profile declares the folk collection it acts as/in — `hermes-main` conversing with the maintainer → `personal`; a future Cast character roleplaying → `characters` (or its Locus's collection). The job routes each session's events to a host-local staging directory per target collection (`~/.folk-staging/<collection>/YYYY-MM.<writer>.ndjson`), never mixing domains in one segment. Take the profile→collection mapping from job config, one line per profile — don't infer it from content.

**Transport:** staging segments sync to the canonical registered roots (e.g. `personal`'s root in the notes tree on the laptop) as plain files — rsync or the existing sync tooling; an ops detail, per the digger community-layer doc's identical stance. Per-writer naming means the synced file is only ever written by the promotion host, so there are no merge or collision cases; the laptop syncs before `folk index --rebuild`.

## Trigger and idempotency

A cron job (systemd timer or an existing cron mechanism), nightly — not a literal session-end hook. Batch is simpler, the model is likely idle at night, and same-day latency is not a requirement. "Session end" is detected by mtime quiescence: process sessions whose file hasn't changed in >1h.

Idempotency via a processed-sessions state file on the promotion host (`~/.folk/promotion-state.json`: session id → {processed ts, outcome}). A session is processed exactly once; re-running the job after a crash skips completed sessions and retries failed ones.

## Per-session flow

1. **Extract** — `extract_observations.py` logic: mechanical, deterministic, no LLM. Observation events (participants, utterances with `msg:` pointers) append to the current host segment. This step cannot fail on content, only on I/O; it always runs even if promotion later fails, so the factual record is never held hostage by the LLM step.
2. **Promote** — `promote_llm.py` logic: prompt carries the transcript, the observation events, `vocab.json` (predicates + definitions + known entity slugs, per the entity-resolution fix in `journal-in-folk.md`), and the evidence/level instructions. Temperature 0. Output is candidate promotion events, not yet appended.
3. **Lint** — full lint (schema, src pointers, quote shingle match, speaker attribution, duplicates, slugs) against the transcript + vocab.
4. **Append or quarantine** — lint-clean events append to the segment (vocab and slug proposals are soft output and append fine — they queue in `folk review` by construction). Hard lint errors: the entire promotion output for that session goes to `~/.folk/quarantine/<session-id>.ndjson` with the lint report alongside; nothing partial is appended; the state file records the failure; `folk review` surfaces it. One automatic retry (fresh generation) before quarantining — transient model flakiness is real, but two failures mean a human should look.
5. **Record** — update the processed-sessions state file; the appended segment reaches the canonical root via the transport sync above.

## Operational guardrails

- **Cost/thermal:** the job holds Hermes's already-configured model; ~5 min per session at prototype scale. Cap per run (e.g. 10 sessions) so a backlog after a vacation doesn't run the GPU for hours; the cap plus nightly cadence drains any backlog within days.
- **Never blocks Hermes:** run at low priority; if Ollama is busy serving a live conversation, defer (retry next run). The event-driven cost-gating policy from the design doc applies — this is scheduled work, not an autonomous loop.
- **Logging:** one log line per session (id, event counts by kind, lint result, wall time) to a journal-adjacent log file. Silence is the failure mode to design against — the monthly habit should be checking `folk review`, not reading logs, so anything needing attention must reach the queue.

## Out of scope

- Mid-session (streaming) promotion — batch on quiescent sessions only.
- Multi-profile attribution — today there is one Hermes profile; when Phase 1 creates more, `actor` comes from the profile name, which the session files already imply. Design the extract step to take actor as a parameter rather than hardcoding `agent:hermes-main`.
- The Archivist's surfacing and decay — later phases; this job is promotion only (per the agreed subsystem split, Known issue #3).

## Exit criteria

- A real Telegram conversation happens; by the next morning its observation events and lint-clean promotions are in the `personal` staging segment `2026-MM.desktop.ndjson`; after transport sync + rebuild on the laptop, `folk show sam` shows a new stated fact with a correct verbatim quote and src pointer.
- A session engineered to produce a lint failure (or a replayed known-bad fixture) lands in quarantine, appears in `folk review`, and appends nothing.
- Running the job twice in a row processes zero sessions the second time.
