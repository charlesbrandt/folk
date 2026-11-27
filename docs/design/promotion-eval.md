# Promotion evaluation harness — TRUSTMEM triad (Phase 2)

**Status:** confirmed by the maintainer 2026-07-22 — full text reviewed and holds. No invariant or schema change anywhere in this spec.
**Context:** the wider persona-agent architecture design (Known issue #3's resolution: TRUSTMEM's transition-verification triad, arXiv:2606.25161, adopted 2026-07-19 as promotion's measurable criterion — never built); `docs/design/session-promotion-job.md` (the system under test); `prototypes/journal-promotion/` (the fixture corpus and the original ad-hoc "6/8 reference facts" count this replaces); the maintainer's private handoff log escalation item 3 (prompt-quality judgment is stronger-model work — this harness is the *detector* that tells you when to escalate, never the thing that iterates the prompt itself).

## Why

`folk promote` runs nightly on the promotion host, unmeasured. The one quality signal so far is anecdote: a supervised run quarantined 5/7 backlog sessions, a prompt fix brought re-validation to 4/5 clean, and the "6/8 reference facts" count from the prototype was a coverage check only. Known issue #3 already ruled that promotion needs a measurable criterion and named it — **coverage** (nothing important omitted), **preservation** (nothing existing corrupted), **faithfulness** (nothing hallucinated) — but nothing computes those three numbers. Until something does, "did the prompt change help?" and "did the model swap hurt?" are vibes, and every later Phase 2 piece (surfacing ranks what promotion produced) builds on unmeasured ground.

## Decision 1 — labeled-fixture harness with two modes, deterministic core

The harness compares promotion output against **human-labeled reference sets** — no LLM judge anywhere in the scoring path (an LLM grading an LLM reintroduces exactly the unmeasurability this exists to remove). Two modes share one scorer:

- **Replay mode** — scores a *stored* model output (NDJSON, the prototype's second-pass fixture pattern) against the labels. Fully deterministic, no network, runs in `tests/`. This is the regression gate: prompt or lint changes re-score stored outputs instantly.
- **Live mode** — runs the real `promotion.promote()` against the configured Ollama model on a corpus session, then scores the fresh output with the same scorer, and stores it as a new dated output snapshot. This is how a prompt change or model swap gets measured; it requires a real Ollama endpoint and is never part of the test suite.

Same scorer, so a live run's numbers are directly comparable to every stored run's.

## Decision 2 — the three metrics, concretely

Per corpus session, against its label file:

- **Coverage** — fraction of the labeled *reference facts* recovered. A reference fact matches an emitted candidate on `(s, p, o)` after alias canonicalization (the `aliases` map in `vocab.json`, same projection rebuild uses); `evidence`/`level` are reported on the match but don't gate it (a fact recovered at the wrong tier is a finding, not a miss).
- **Faithfulness** — every emitted candidate is either (a) a labeled reference fact, (b) on the session's labeled *acceptable-extras* list (true facts the reference set didn't bother enumerating), or (c) **ungraded** — reported by slug for human grading, never auto-failed. A candidate on the labeled *known-false* list is a faithfulness violation. For `stated` events, src lint is already the deterministic faithfulness floor and runs first; this metric is chiefly what catches `interpreted` drift, the gap Known issue #3 named. Grading an ungraded candidate means moving it onto one of the lists — the corpus grows by exactly the facts real runs surface.
- **Preservation** — run the full pipeline (extract → promote → append into a *staging* journal root → `rebuild_index` over real-plus-staging) and verify every index record derivable *without* the new session is byte-identical before and after. This is a subset check over the rebuilt file, and it's nearly free — byte-identical rebuild is already a tested property; the new assertion is that adding a session never mutates what was already true.

The report is per-session and aggregate: three ratios, the miss/violation/ungraded lists, and the src-lint pass rate. No thresholds are hardcoded; the regression rule is **no metric decreases against the recorded baseline** (`eval/baseline.json`, updated deliberately in a commit when a change legitimately moves the numbers).

## Decision 3 — the corpus starts small and grows from real runs

Initial corpus: the prototype's fixture session (its reference facts become the first label file — the "6/8" count should reproduce as a coverage ratio on day one) plus the synthetic 5-message validation conversation from the 2026-07-19 live test (its 7 candidates and the known-bad grandmother event are already analyzed — that event seeds the known-false list). The 7-session real Hermes backlog is the natural next labeling target, human-paced — labeling is Bedrock-adjacent judgment work the maintainer does when he does it; the harness must be useful at corpus size 1.

## Decision 4 — home and shape

`eval/` at the repo root: `eval/corpus/<session-id>/` holds the transcript, the label file (`labels.json`: `reference`, `acceptable_extras`, `known_false`), and dated stored outputs; `eval/baseline.json` holds the current baseline numbers. The runner is `scripts/promotion_eval.py` (stdlib only, invariant 8) — a dev tool, not a `folk` subcommand; user-facing surface area is deliberately zero. Replay-mode scoring is also importable so `tests/` can pin the scorer's own behavior.

## Scope for v1

- The scorer (match + three metrics + report), replay and live modes, `eval/` layout, baseline file, prototype-fixture and synthetic-session labels.
- Wire the src-lint pass rate into the report (it's computed anyway during scoring's lint pass).
- Tests: scorer determinism (score twice → identical report), a planted-corruption preservation check (mutate one pre-existing index record in a fixture rebuild → preservation must fail), alias-canonicalized matching.

**Deferred, deliberately:** LLM-judge scoring in any form; automatic threshold gates in CI beyond baseline non-decrease; labeling tooling (labels are hand-edited JSON until volume justifies more); external benchmarks (HaluMem, MemoryAgentBench) — yardsticks to borrow test *design* from, not dependencies.

## Exit criteria

- Replay mode on the prototype fixture reproduces the documented reference-fact recovery as a coverage ratio, and scoring the same stored output twice yields byte-identical reports.
- The synthetic session's known-bad grandmother event scores as a faithfulness violation when run against the pre-fix stored output, and does not recur in the post-fix stored output — the harness retroactively *measures* the 2026-07-19 prompt fix.
- The planted-corruption test fails preservation; an untouched pipeline run passes it.
- Live mode runs end-to-end against a real Ollama and emits a report in the same format, stored and comparable.
- No LLM anywhere in the scoring path; no new dependencies.
