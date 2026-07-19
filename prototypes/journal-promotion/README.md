# journal-promotion prototype

Exercises the journal design from the wider persona-agent architecture design ("The journal (working design, 2026-07-18)") against a synthetic-but-realistic Hermes conversation: a fictional 2026-06-01 Telegram session about meaning-making, recency bias, and the garden-tracker priority (`20260601_025800_7f3ac9e2`) — authored for this prototype, not a real transcript. See `fixtures/mara.md` and `NOTE.md`-style provenance notes throughout this directory for that framing.

## The three records

| Record | Here | Authoritative for | Who writes |
|--------|------|-------------------|------------|
| Person files | `fixtures/mara.md` | What the human curated | Human only |
| Journal | `journal/*.ndjson` | What happened | Append-only: scripts + agents |
| Index | `index.ndjson` | Nothing — it's a cache | `replay.py rebuild` |

## The pipeline

1. `extract_observations.py <session.jsonl>` — **mechanical, deterministic, no LLM.** Turns a Hermes transcript into observation events (who participated, who said what, with `msg:` pointers back to the exact transcript line). This is the "observed" trust tier. Generated `journal/2026-06-observations.ndjson`.
2. `journal/2026-06-promotions.ndjson` — **hand-authored for this prototype**, simulating the output of the future LLM promotion job (the one real-LLM step in the whole design: scan observations, propose which facts deserve triples). Each event carries `kind` (`promotion` / `inference` / `bedrock_candidate`), the proposing `actor`, a supporting quote in `note`, and a `src` pointer to the message it came from.
3. `lint.py <events.ndjson> <transcript.jsonl>` — **deterministic guardrail, no LLM.** Hard errors (exit 1): schema violations, src pointers at nonexistent messages, `stated` quotes that don't appear in the cited message (5-word shingle match), duplicate triples, malformed slugs. Soft output: predicates/types not in `vocab.json` are filed as *proposals* — the flexibility valve. Accepting one = adding it to vocab.json with a definition; until then it queues for review.
4. `vocab.json` — the seeded-but-open vocabulary: predicate definitions, entity type prefixes, slug rules. Fed verbatim into the promotion prompt; the LLM must prefer listed predicates and may coin new ones only with a `p_def` definition attached.
5. `replay.py rebuild` — **pure script.** Parses person files into human-tier triples, replays journal segments into observed/stated/interpreted-tier triples (bedrock-level proposals become suggestions), writes `index.ndjson` sorted. Run it twice: byte-identical. Delete the index and rebuild: agent memories survive, because they live in the journal, not the index.
6. `replay.py show mara` — tiered profile: Curated / Observed / Stated (verbatim quotes + src) / Interpreted / Bedrock suggestions.

## What this proves

- **Rebuild safety** (design doc Known issue #1): the index is disposable; nothing is lost when it's regenerated, including agent-written memories.
- **Trust without `conf`** (Known issue #2): the tier is derived from `actor` + `kind` at read time. No number to maintain, no decay corrupting truth. Utterance observations stay journal-only (drill-down via `msg:` pointer); only relational facts reach the index.
- **LLM proposes, script disposes**: the LLM's only write surface is journal events. A bad promotion is visible (actor-stamped, quoted, pointed at its source) and can be demoted without breaking determinism.
- **Bedrock stays human**: the radio-workshop defining-moment candidate is surfaced as a suggestion, never indexed as fact — "the system suggests, you decide."

## What's simulated

The promotion events were hand-written to match a plausible LLM promotion pass over the fictional transcript. The next step is replacing that file's authorship with an actual LLM pass (a local model) over the observation events + raw transcript, emitting the same event schema — then comparing its output against this hand-written reference to judge promotion quality.

## Next steps

- ~~Promotion job as an LLM pass, judged against this reference file~~ — done 2026-07-18 (`promote_llm.py`, gemma4:31b); findings in `COMPARISON.md`
- ~~src lint~~ — done: `lint.py`. On its first run it caught a paraphrase-as-quote in the hand-written reference, and produced its own refinement: quote verification binds only `evidence: stated` events; interpreted notes are summaries whose audit trail is the src pointer
- ~~Split `kind` into `evidence` + `level`~~ — done: schema, reference file, replay tiers, and prompt all updated
- ~~Controlled vocabulary~~ — done: `vocab.json` + prompt integration + lint proposals queue
- Review-queue tooling for the less-in-the-loop workflow: a `review` command that batches pending vocab proposals and bedrock suggestions, with accept/reject writing back to vocab.json / person files as human journal events
- ~~Speaker-attribution lint~~ — done: a `stated` fact's subject must be the speaker of the cited message; verified against the live false-stated event (COMPARISON.md second pass, finding 1)
- Entity resolution for object slugs (second pass, finding 2): feed existing entity slugs into the prompt; near-duplicate mapping before append
- `last_reinforced` field on index triples (staleness, separate from trust)
- Fold the journal/replay mechanism into folk proper (`folk index --rebuild` replaying `~/.folk/journal/`)
