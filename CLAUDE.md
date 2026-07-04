# folk — instructions for implementing agents

folk is a UNIX-philosophy CLI for remembering people, and Layer 0 of a wider persona-agent architecture. Implementation work is specified in `docs/design/` — start from the spec for your task, not from the architecture doc. **Implementing agents start at `docs/HANDOFF.md`** — it holds the task sequence, per-task escalation guidance, and the definition of done.

## Invariants — violating any of these is a design regression, not a style choice

1. **Three records, one authority each.** Person files (markdown, git) = what the human curated. The journal (append-only NDJSON segments in registered per-domain roots — there is no single global journal directory) = what happened. The index (`~/.folk/triples.ndjson`, the only thing in `~/.folk/`) = a derived cache, deletable at any time. Never make anything authoritative in two places.
2. **Nothing but `folk index --rebuild` writes the index.** Agents, promotion jobs, and commands write person files (human-driven) or append journal events — never index lines. A directly-written index line is destroyed by the next rebuild, silently.
3. **Journal segments are append-only and never edited.** Corrections are later events (e.g. `kind: review`), not rewrites. Canonicalization (slug aliases) happens at rebuild time as a projection. One sanctioned exception, human-only, for privacy: `kind: redaction` events (and the sealed-segment purge step they enable) per `journal-schema.md` — never generalize it.
4. **No LLM in the rebuild path.** `folk index --rebuild` is a pure deterministic script: run twice → byte-identical output. LLMs appear in exactly one place in the whole system: writing `promotion` events. LLM proposes; script disposes.
5. **No `conf` numbers.** Trust is a tier derived at read time from `actor` + `kind` + `evidence` (human > observed > stated > interpreted). `level: bedrock` facts are only ever suggestions — only the human edits Bedrock (person files).
6. **Lint before append.** Any programmatic append of promotion events runs the lint first; hard failures quarantine the whole batch for `folk review`, nothing partial lands.
7. **Collections are config, never code.** No collection name may be enumerated in code — the architecture depends on adding domain collections (`characters`, `authors`, `musicians`, later `loci`) being a one-line config change. Journal roots are likewise registered, never hardcoded.
8. **Stdlib only, Python 3.10+.** No new dependencies without explicit sign-off from the maintainer.

## Event schema

`docs/design/journal-schema.md` is normative. Lint is its executable form; keep them in agreement.

## Build order for the current specs

Dependency order differs from the roadmap's priority order. Build:

1. `docs/design/collections-and-graph.md` — independent, can go first or in parallel with anything.
2. `docs/design/journal-in-folk.md` — lands the journal, lint, rebuild, `id` field, per-writer segments.
3. `docs/design/review-queue.md` — depends on 2 (event `id`, journal locations, review events in replay).
4. `docs/design/session-promotion-job.md` — depends on 2 (and pairs with 3 for its failure path).

The reference implementation for 2–4 is `prototypes/journal-promotion/` — its `README.md` and `COMPARISON.md` are required reading before touching journal code. Prefer porting its logic over rewriting it; its behaviors (shingle quote match, speaker attribution, vocab proposals as soft output) were each earned by a real failure.

## Conventions

- Design docs: one feature per file in `docs/design/`; git commit messages serve as the project journal (`todo.md`/`journal.md` at the repo root are the legacy pattern — read them for history, don't extend them).
- Markdown: no hard line wraps — write paragraphs as single lines.
- Commits: plain messages, no `Co-Authored-By` lines.
- When a spec says "confirm with the maintainer," that is a stop-and-ask, not a pick-a-default.
- No real person names in code, scripts, tests, or docs — including internal ones like `docs/HANDOFF.md` that otherwise stay concrete about real infra (IPs, hostnames, tool names are fine there). A name is someone else's personal data riding along in a file that gets committed and may go public; describe the role instead (e.g. "an external adapter script" or "a collection member"), not who it belongs to. Found and fixed once already: an external adapter script had been named after the real person whose collection it indexed, and that name had leaked into `scripts/migrate_legacy_index_triples.py`'s example usage and `docs/HANDOFF.md`'s migration note — see the `folk` skill's Public-Facing Documentation Conventions section for the fuller writeup. This is separate from invariant 7 (collection names) — it's about individual names specifically, repo-wide, not just `docs/site/`.
