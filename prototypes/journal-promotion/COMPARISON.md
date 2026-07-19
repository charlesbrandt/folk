# LLM promotion pass vs hand-written reference (2026-07-18)

Model: `gemma4:31b` (Hermes's own primary, already loaded on the promotion host), temperature 0, ~4.5 min wall time. Output: `llm/20260601_025800_7f3ac9e2.gemma4-31b.ndjson` — 8 events, all schema-valid on the first try, zero rejected lines. Reference: `journal/2026-06-promotions.ndjson`.

## Fact-level agreement: 6 of 8 reference facts recovered

| Fact | Reference | LLM | Verdict |
|------|-----------|-----|---------|
| garden-tracker is Mara's current project | promotion, `prioritizes` | promotion, `worked_on` | match (predicate drift) |
| interested in collecting local history stories | promotion | promotion | match (slug drift) |
| values: self-reliance, rootedness, hands-on craft | inference ×3 | bedrock_candidate ×3 | match on content, kind diverges |
| radio workshop refuge (identity-level) | bedrock_candidate | bedrock_candidate | full match — both withheld it from auto-promotion |
| worked through parish archive in December 2025 | promotion | — | **LLM miss** (the one dated fact) |
| agent judged parish/oral-history-03 most meaningful | inference | — | LLM miss (defensible — arguably transient) |

LLM extras not in the reference: `person:mara believes value:start-over-elsewhere` ("If a place lets you down, you can always start fresh somewhere new" — a memoir line attributed as a held belief; exactly the kind of aggressive claim the bedrock gate exists to catch, and the LLM did route it to bedrock_candidate) and `motivated_by value:workshop-sanctuary` (plausible inference, marked as such).

## The upset: the LLM beat the human on pointer accuracy

The LLM's `src` pointers were correct on all 8 events. The hand-written reference had wrong message indices on 6 of 8 (written from memory instead of checked; fixed 2026-07-18). Two lessons: mechanical claims should never be hand-authored, and the pipeline needs a **src lint** — a deterministic check that the quoted text in `note` actually appears in the message `src` points to. That lint also becomes the guardrail against LLM-hallucinated quotes.

## Second pass (vocab-aware prompt + new schema, 2026-07-18)

Same model, same transcript, prompt now carrying `vocab.json`, the `evidence`/`level` split, and an explicit time-anchor instruction. Result: 7 events, **lint-clean on the first try** — 0 errors, 0 vocab proposals (no coining needed), all `stated` quotes verbatim-verified against their source messages.

What the first-pass fixes fixed:
- **The December 2025 miss is recovered** — `worked_through` with `when: "2025-12"`. The time-anchor instruction worked; `prioritizes` also picked up `when: "2026-06-01"`.
- **Predicate drift gone** — `prioritizes` (not `worked_on`), all predicates from the vocabulary.
- **Kind alignment** — the radio-workshop moment came back as `defining_moment` / `interpreted` / `bedrock` with the *identical slug* (`moment:radio-workshop-refuge`) as the reference: exact match on all axes.
- Pointer accuracy stayed perfect.

What's still open, in order of importance:
1. **Speaker attribution was a lint blind spot — now closed.** Event 5 asserts `person:mara believes value:start-over-elsewhere` as `evidence: stated` — and the quote *is* verbatim in msg #19, so the original lint passed it. But #19 is an **assistant** message quoting Mara's memoir; Mara never said it in the conversation. This was the exact mechanism by which literary material could quietly become "things Mara said." Fixed same day: lint.py now requires a `stated` fact's subject to be the speaker of the cited message (`SPEAKER_ROLE` map); re-linting the LLM output flags exactly this event and nothing else.
2. **Object-slug entity resolution.** The vocabulary controls predicates but not object slugs: `topic:local-history-stories` vs the reference's `topic:collecting-local-history-stories`, `work:parish-records-md` vs `work:parish-archive`. Fix: feed existing entity slugs into the prompt (like predicates), plus a resolution pass that maps near-duplicates before append.
3. The values cluster came back consolidated (`value:self-sufficient-systems`, `value:workshop-sanctuary`) rather than the reference's three — reasonable reframing, and correctly bedrock-gated either way.

## Findings for the design

1. **Promotion quality is already usable.** Hermes's own local model, zero-shot, recovered 6/8 reference facts with valid schema and honest kind-labels. The promotion job is not blocked on model quality.
2. **The `kind` axis is conflating two questions** — evidence strength (stated vs interpreted) and destination (Core vs Bedrock). The values cluster is *interpreted* evidence with *identity-level* destination; the reference called it "inference," the LLM called it "bedrock_candidate," and both followed the spec. Split the axes: `evidence: stated|interpreted` and `level: core|bedrock` instead of one `kind` enum.
3. **Controlled vocabulary needed.** Predicate and slug drift (`worked_on` vs `prioritizes`, `value:hands_on_craft` vs `value:hands-on-craft`, `topic:local_history` vs `topic:collecting-local-history-stories`) would fragment the graph within weeks. The promotion prompt should carry the allowed predicate list and existing entity slugs (or a normalization pass should map to them).
4. **Misses skew temporal.** The one clear miss was the dated fact (December 2025). Promotion prompts should explicitly ask for time anchors — dates are what make a memory graph queryable later.
