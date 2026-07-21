# `folk render` — SOUL.md and other generated persona views (Phase 1)

**Status:** confirmed by the maintainer 2026-07-21, with one condition attached to Decision 3 (see below). In `docs/HANDOFF.md`'s task sequence as task 6. None of the five decisions touch a CLAUDE.md invariant or the frozen journal schema.
**Context:** the wider persona-agent architecture design (Layer 1, "SOUL.md as a generated view"; Layer 3's Core Traits/Speaking Style mapping; Phase 1's exit criterion); `docs/design/loci.md` (explicitly defers genius-loci rendering to this spec's machinery — "shouldn't be designed twice"); `docs/design/collections-and-graph.md` ("characters may carry media associations... that `folk render` later inherits into SOUL.md"); `folk/person.py` (current section-parsing conventions this spec extends); `folk/journal.py` (`person_profile`, referenced in Decision 3 but not used by v1)

## Why

Phase 0 is done; Phase 1 is `folk render --format soul <person>` producing a Hermes SOUL.md from a folk person file. Two things are missing today. First, mechanically: Hermes's SOUL.md (on whatever host runs it) is hand-maintained, which violates the architecture's stated invariant ("SOUL.md is never edited by hand after first generation; edits go to the folk person file and are re-rendered") — that invariant isn't true until this command exists. Second, structurally: folk's person-file schema was never finished. `person.py` parses `## Associations`, `## Tags`, `## Media` today; `review.py`'s bedrock-accept path already writes to a fourth, `## Defining moments`, but nothing formalizes `## Archetype` or `## Voice` — the two sections the architecture doc's Layer 3 table (Core Traits, Speaking Style) needs somewhere to live. The architecture doc names this directly: "person-file schema stabilization... rolls into Phase 1 (`folk render` forces it)." This spec is that stabilization plus the render command itself.

## Decision 1 — deterministic template render, no LLM

`folk render` is pure templating over structured input (person-file sections; see Decision 3 for what else). No model call anywhere in it. CLAUDE.md invariant 4 scopes "no LLM" to the rebuild path specifically, but the same reasoning applies here: a render step that calls a model stops being testable the way every other folk command is (run twice on unchanged input → byte-identical output, the same bar `journal.rebuild_index` holds itself to). If prose synthesis ever becomes wanted — weaving Voice and Defining moments into flowing paragraphs rather than a templated list — that is a distinct, later, explicitly opt-in layer on top of this deterministic base, not part of v1.

## Decision 2 — two new person-file sections, both Bedrock tier

Extend `person.py`'s section conventions (parsed the same way `## Tags`/`## Media` already are — free text or list lines under a `##` heading):

- **`## Archetype`** — free text, typically a short phrase or a few tag-like words (e.g. `trickster mentor`). Optional; absent for most existing files today (none currently have it).
- **`## Voice`** — free text describing speaking style, register, verbal habits. Optional.

`## Defining moments` already exists in practice (`review.py`'s `_person_file_edit_target` picks it as the default bedrock-accept section) but was never documented as a first-class section — this spec formalizes it alongside the two new ones.

All three are Bedrock tier, same as `## Associations`/`## Tags`: human-owned, edited by hand or via `folk review`'s interactive accept (never a batch write, never an agent write directly). `folk show` should parse and display `## Archetype`/`## Voice` the same way it already surfaces Tags/Media, so a human reviewing a file can see what render will produce without running render.

## Decision 3 — v1 render input is Bedrock only, not the index

`folk render` reads *only* the person file: name (H1), bio (body text before the first `##`), Archetype, Voice, Associations, Tags, Media, Defining moments. It does not query `journal.person_profile` or pull any observed/stated/interpreted triple into the rendered output.

Rationale: deciding *which* Core-tier facts belong in a system prompt, and how many, is a relevance-ranking problem — Woven Imprint's Reciprocal Rank Fusion, the "context-bleeding" failure mode `locus-model.md` names for naive RAG — not a templating problem. That's the Archivist's job (Phase 2), which doesn't exist yet. Rendering only what a human curated keeps Phase 1's scope honest: a SOUL.md that reflects exactly the identity layer, nothing inferred, nothing ranked. Folding a bounded slice of Core-tier facts into render is explicitly a Phase 2 extension, gated on the Archivist existing to bound and rank it — not a v1 gap to fill later ad hoc.

**Confirmed by the maintainer 2026-07-21, with a condition:** when Phase 2 (the Archivist) work begins, explicitly revisit whether `folk render`'s scope should expand to include a bounded, ranked slice of Core-tier facts — this is not an automatic follow-on, but it should be a deliberate checkpoint in the Archivist design work, not something that falls through the gap between the two specs.

**Checkpoint resolved 2026-07-21 (Phase 2 design session):** render stays Bedrock-only by default, permanently. A bounded Core-tier slice becomes available only behind an explicit opt-in flag (`--with-core N`), implemented as a budgeted `folk surface` query — render grows no ranking logic of its own. See `folk-surface.md` ("Consumers"); the flag doesn't exist until `folk surface` does, and is a small follow-on, not part of either spec's v1.

## Decision 4 — v1 ships `--format soul` only

The architecture doc names three targets (`soul`, `card`, `yaml`), but only `soul` has a live consumer (Hermes). `card` (a SillyTavern-style character card) and `yaml` (a Persatrix persona file) are speculative until one of those runtimes is actually adopted here — designing their exact field mappings now means designing against a target nobody has verified folk needs. `folk render --format <fmt> <person>` takes the format argument from day one so `card`/`yaml` are additive later rather than a breaking CLI change, but only `soul` is implemented in v1; any other value exits with "not yet implemented," not a guess at a schema.

## Decision 5 — write target is the caller's choice, with a hand-edit warning

`folk render --format soul <person>` writes to stdout by default; `--out <path>` writes to a file. folk has no privileged knowledge of Hermes's filesystem (it may not even run on the same machine), so it never assumes a default path for Hermes's SOUL.md — the caller (a human, or a deploy script) pipes or redirects explicitly. The rendered output opens with a plain marker comment:

```
<!-- generated by folk render --format soul from person:<slug> — do not hand-edit; edit the person file and re-render -->
```

This is a visible warning for a human who opens the file, not an enforcement mechanism (no hash check, no lock) — consistent with folk's existing posture of documented convention over code-enforced restriction (e.g. person files are plain git-tracked markdown; nothing stops a hand edit, the convention is the guardrail).

## Scope for v1

- `## Archetype` and `## Voice` sections: parsing in `person.py` (mirroring `_parse_tags`/`_parse_media`), surfaced by `folk show`.
- `folk render --format soul <person> [--out <path>]`, wired into `folk/cli.py`.
- Template: name → bio → Archetype → Voice → Associations (rendered as relationships, e.g. "appears in Norwegian Wood") → Media → Defining moments, in that stable order; empty sections omitted, not emitted as empty headers.
- Deterministic byte-identical output on unchanged input (Decision 1's testability bar) — verify by literally diffing two runs, the same discipline `journal-in-folk.md` used for rebuild.
- No new dependencies (invariant 8) — stdlib templating (f-strings / `string.Template`), not a templating library.

**Deferred to follow-on work, deliberately:**

- Locus genius-loci rendering (`docs/design/loci.md`'s own deferred list: "same prompt-assembly machinery as SOUL.md generation; shouldn't be designed twice" — extend this spec's template mechanism to `locus:<slug>` once loci ships, don't redesign it).
- `--format card`, `--format yaml` — implement when a consumer actually exists.
- Any Core-tier (index-derived) content in rendered output — Phase 2, the Archivist's relevance scoring. **Checkpoint:** when Phase 2 design work starts, explicitly revisit this scope decision rather than letting it lapse by default. *(Resolved 2026-07-21 — see Decision 3's resolution note: opt-in `--with-core N` via `folk surface`, after both commands are stable.)*
- Prose synthesis / LLM-assisted rendering.
- Batch rendering (a whole Cast at once) — v1 is one person, one invocation.
- Auto-detecting or writing to the Hermes data directory — always an explicit `--out` or a shell redirect.

## Exit criteria

- `folk render --format soul <person>` emits markdown containing (when present) name, bio, archetype, voice, associations, tags, media, and defining moments, in the stable order above; running it twice against unchanged input produces byte-identical output.
- `## Archetype` and `## Voice` round-trip through `folk show`: adding either section to a person file and re-running `folk show <person>` displays it, using the same section-parsing path as `## Tags`.
- A real Hermes profile's SOUL.md, regenerated from a folk person file via this command (piped or redirected onto the Hermes host), differs from the hand-written one only in the marker comment and whatever content the person file actually specifies — no silent field loss.
- No LLM call anywhere in `folk render`'s code path.
- `folk render --format card <person>` (or `yaml`) exits cleanly with a "not yet implemented" message rather than emitting a guessed-at schema.
