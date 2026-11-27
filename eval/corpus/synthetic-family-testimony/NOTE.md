This corpus item stands in for the synthetic 5-message "grandmother" conversation from the 2026-07-19 live Ollama test described in the maintainer's private handoff log's task-4 section (the one whose pre-fix run produced a `stated` fact about `person:grandmother` sourced from a message spoken by a third party, which lint correctly quarantined, and whose post-fix run -- after `folk/promotion.py`'s prompt fix, commit `5c64b0e` -- came back clean).

**This is not that session.** The actual transcript and both model outputs from 2026-07-19 were never written to disk anywhere -- only the paragraph in the maintainer's private handoff log survives, and this environment has no network path to the original promotion host to regenerate them live. Confirmed (2026-07-22) authoring a fresh, clearly-synthetic fixture that exercises the same bug class instead of reconstructing history from prose.

## The scenario

`person:sam` tells the agent about his grandmother Elena's daily bread-baking ritual (`transcript.jsonl`, 5 lines, `person:sam` is the only human speaker). Elena never speaks in this conversation -- everything about her is third-party testimony.

- `outputs/2026-07-18.pre-fix.ndjson` -- 7 candidates, one bad: event 2 asserts `person:elena bakes_daily event:daily-bread-baking` as `evidence: "stated"`, sourced from message #1 -- but message #1 was spoken by `person:sam`, not Elena. This is the exact bug: encoding third-party testimony as if the third party said it directly.
- `outputs/2026-07-19.post-fix.ndjson` -- the same 7 facts, event 2 now correctly demoted to `evidence: "interpreted"` (the prompt's option (b): keep the third party as subject, drop the evidence tier, keep the quote in `note`).

## How the harness catches it

Two independent, deliberately overlapping mechanisms:

1. **`faithfulness.src_lint`** -- runs the real `journal.lint_events` speaker-attribution check. Scoring the pre-fix output against `transcript.jsonl` fails it (event 2 is a `stated` fact whose subject didn't speak the cited message); the post-fix output passes at `1.0`. This is the same lint that would quarantine the batch in the real pipeline (invariant 6) -- Decision 2 calls this "the deterministic faithfulness floor" for `stated` events.
2. **`labels.json`'s `known_false` entry** pins `evidence: "stated"` specifically on the `(person:elena, bakes_daily, event:daily-bread-baking)` triple -- so the pre-fix candidate (`evidence: stated`) is flagged a faithfulness violation by triple-matching too, while the post-fix candidate (`evidence: interpreted`) is not, and instead matches `reference` (the fact itself is true and worth keeping, just not as a first-person quote).

`coverage` is unaffected either way (7/7 both runs) -- Decision 2 is explicit that a fact recovered at the wrong tier is a finding, not a coverage miss. The tier is exactly what the two mechanisms above exist to catch.
