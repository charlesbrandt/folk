Evaluation harnesses. Both are dev tools, not `folk` subcommands: user-facing surface area is deliberately zero.

- **Promotion** (`eval/corpus/`, `scripts/promotion_eval.py`) -- `docs/design/promotion-eval.md`. Everything below describes this one.
- **Appearance** (`eval/appearance/`, `scripts/appearance_eval.py`) -- `docs/design/appearance.md` Decision 10. See "Appearance harness" at the end.

## Layout

- `eval/vocab.json` -- the harness's own frozen vocab (types/predicates/aliases), separate from `~/.config/folk/vocab.json` so scoring is reproducible across machines and time.
- `eval/baseline.json` -- current per-session and aggregate numbers. Updated deliberately (`scripts/promotion_eval.py update-baseline`, then commit) when a change legitimately moves the numbers -- never auto-adjusted by a run.
- `eval/corpus/<session-id>/` -- one corpus session per directory:
  - `labels.json` -- `reference` (facts that should be recovered), `acceptable_extras` (true facts the reference set doesn't bother enumerating), `known_false` (facts that are wrong -- optionally pinned to a specific `evidence` tier, see `synthetic-family-testimony/labels.json`).
  - `meta.json` -- `user_slug`/`agent_slug`/`collection`/`transcript` filename, when a raw transcript is available for this session (needed for `src_lint` scoring and live mode; absent for corpus items whose raw transcript was never preserved).
  - `transcript.jsonl` -- optional, Hermes session-line shape (`{"role": ..., "content": ..., "timestamp": ...}` per line).
  - `outputs/*.ndjson` -- dated stored candidate-event snapshots, one promotion run's output each.
  - `NOTE.md` -- per-session provenance notes; read these before trusting a number.

## Running it

```
python3 scripts/promotion_eval.py replay                 # score every corpus session's latest stored output, no network
python3 scripts/promotion_eval.py replay <session-id> --output <file.ndjson>
python3 scripts/promotion_eval.py live <session-id> --model ... --ollama-url ...   # real Ollama, needs a transcript
python3 scripts/promotion_eval.py update-baseline         # record current replay numbers as the new baseline
```

`replay` exits 1 if any session's numbers dropped against `eval/baseline.json` (no metric may decrease against the recorded baseline -- Decision 2). `live` is never run from `tests/`.

## Corpus provenance

- `20260601_025800_7f3ac9e2/` -- the synthetic prototype fixture (`prototypes/journal-promotion/`). Read its `NOTE.md`: the harness does *not* reproduce the historical "6/8" figure, and that's expected, not a bug -- see the note for why.
- `synthetic-family-testimony/` -- a fixture authored for this harness, standing in for a real 2026-07-19 live-test session whose raw data was never saved. Read its `NOTE.md` before assuming it's verbatim history.

## Appearance harness

`docs/design/appearance.md` Decision 10. Scores what is deterministically checkable about a figure's `## Appearance` brief, and refuses to score what isn't.

- `eval/appearance/consumers.json` -- which labels each consumer reads, frozen and committed for the same reason `eval/vocab.json` is: a coverage number must be reproducible, not a lookup into whatever a live consumer happens to be configured with today. This is also the only place in the repo where label names are written down -- folk's own source contains none.
- `eval/appearance/corpus/<figure>/` -- one fixture figure per directory:
  - `person.md` -- the fixture person file (the brief under test).
  - `expected.json` -- golden snapshot of the compiled brief. Updated deliberately (`update-golden`, then commit); the diff is the point.
  - `prompts/*.txt` -- fixture compiled prompts, for the propagation check. Hand-written; the check only asks whether an artifact still contains the current brief, not how it was produced.
  - `labels.json` -- `expected_stale_prompts` (planted failures, so a check that stops firing is caught) and `likeness_grades` (human judgment, attributed to a brief fingerprint, never scored).
  - `NOTE.md` -- per-figure provenance; read before trusting a number.

```
python3 scripts/appearance_eval.py run                  # score the corpus; exit 1 on a gating failure
python3 scripts/appearance_eval.py run <figure>
python3 scripts/appearance_eval.py update-golden        # record current briefs as golden snapshots
```

Four checks. **Determinism**, **stability** (matches golden) and **propagation** (every compiled prompt still contains the *current* brief -- the stale-artifact failure, where a brief was edited, a prompt was never recompiled, and the render drifted for a boring reason) gate and exit 1. **Coverage** is reported and never gates: most people in most collections have no reason to carry a physical description, so a missing label is information, not a broken build.

**No image is ever opened and no model is ever called** -- a test asserts the runner imports nothing that could. Whether a render *looks like* the figure is a human grade in `labels.json`, pinned to the fingerprint of the brief that produced it; the harness reports those grades and derives nothing from them. Handing the render and the brief to a vision model is exactly the move `promotion-eval.md` Decision 1 rules out, for the same reason.
