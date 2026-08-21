# `## Appearance` — durable physical description for a person or Locus

**Status:** implemented 2026-08-12. Decision 6 resolved by the maintainer the same day — **no emission gate**; the collection's own registration carries the use case. Both open questions resolved on their stated recommendations during implementation (`## Appearance`; Locus parsing generic, display provisional). One addition made while building: `appearance_fingerprint` ships as a third dream-JSON key, for Decision 9's benefit — see Decision 4. No CLAUDE.md invariant and no `journal-schema.md` event shape changes anywhere in this spec: a person-file section, two additive keys in one render format, one registered predicate, and an eval harness that follows `promotion-eval.md`'s shape.
**Context:** `docs/design/folk-render.md` (Decision 2 established `## Archetype`/`## Voice` as Bedrock sections; this is the same move for a third axis, and Decision 4's `--format dream` is the consumer surface); `folk/person.py` (`_parse_free_text`, `_parse_dates` — the two line conventions this reuses); `docs/design/loci.md` (`## Genius Loci`, the Locus-side equivalent); `docs/design/decay-and-supersession.md` (why Bedrock facts do not decay, and what "superseded" means for a hand-edited file); the dream toolkit's `dreamkit/folkref.py` and `dreamkit/frames.py` (the only live consumer of `--format dream` today), and the `dream-draft` skill §6, which currently documents this gap as a hard limitation for writers.

## Why

`folk render --format dream person:<slug>` hands a consumer a `description`: bio, plus `Archetype:` and `Voice:` when written. That is identity and interiority — deliberately, per `folk-render.md` Decision 3 — and it is the right content for a system prompt or a frame's atmosphere. It is the wrong content for anything that has to *look* like a specific figure twice in a row.

The dream toolkit folds that description straight into a frame's `figure:` clause. A locally-described cast member (`cast/<name>.md`) gets five structured fields the compiler reads in a fixed order — `posture.default`, `posture.face`, `traits.build`, `traits.wardrobe`, `traits.hair` — so a figure holds together across twelve frames. A folk-backed figure (`person:<slug>`) gets one prose blob with no such fields, because folk has no slot for them. The `dream-draft` skill states the consequence plainly to any writer who hits it: "folk has no field for build, wardrobe, hair, or posture… If a folk-backed figure needs to look a specific way across renders, that has to already be written as plain prose inside the folk person file's own bio; there is nothing this project can do to add it."

So folk-backed figures are currently *worse anchored* than throwaway local ones, which inverts the point of using folk as the cross-project anchor at all. The gap is not that folk is missing prose — a human can already stuff physical description into a bio, and some do. It is that the description is unaddressable: a consumer cannot ask for hair without taking the whole bio, cannot tell durable traits from this-piece staging, and cannot tell a figure with no described appearance from one whose appearance is buried in paragraph three.

This spec adds the slot. It does not add a body taxonomy, a likeness pipeline, or anything that infers what a person looks like.

## What this does and does not buy you

Worth stating up front, because the feature is easy to over-trust: **consistent text is not consistent likeness.** A diffusion model handed the same six clauses in twelve prompts produces twelve related-looking strangers, not one person. Face-level identity consistency comes from a reference image, a trained embedding, or a pinned seed — machinery that lives entirely on the rendering side and that folk has no business owning.

What this buys is real but bounded: one place where a figure's durable description is written once, addressable by field, and inherited by every project and every render that references them, so drift comes from the model rather than from twelve writers describing the same person twelve ways. That is the same value proposition as `## Voice` — it does not make an LLM sound like someone, it makes every consumer start from the same brief.

The second half of the value is the feedback loop, and it is the reason this spec is worth building even before likeness anchoring exists: once the brief is addressable, you can **track** which renders consumed which version of it (Decision 9) and **test** the properties of it that are deterministically checkable (Decision 10). Without that, an appearance definition is a wish — written once, never confronted with what it actually produced. With it, a figure's definition becomes an artifact with a history and a regression gate, the same way promotion output became measurable rather than anecdotal.

## Decision 1 — `## Appearance` is a person-file section, Bedrock tier, human-only

A new optional section, parsed the same way `## Tags`/`## Media`/`## Dates` already are, on both person files and Locus files (a Locus's "appearance" is its physical fabric — light, materials, wear — as distinct from `## Genius Loci`, which is its mood and rules; the same soul/shell split as a person's).

Bedrock tier, exactly like `## Archetype` and `## Voice`: written by a human by hand or through `folk review`'s interactive accept. Nothing writes it in batch, no agent writes it directly, and it is not derived from anything.

Promotion may **propose** appearance facts — an observation like "she'd cut her hair short since March" is a legitimate journal event and a legitimate `level: bedrock` proposal — and those land in the review queue as suggestions like every other bedrock proposal (invariant 5: "`level: bedrock` facts are only ever suggestions"). The proposal path needs no new machinery; it is the existing one, and the lint-before-append rule (invariant 6) applies unchanged.

## Decision 2 — labeled lines, with an open key set folk never enumerates

The section is a list of `- label: value` lines, reusing the `## Dates` line convention with the date pattern dropped:

```markdown
## Appearance

- build: tall, narrow through the shoulders, stands slightly off-plumb
- hair: dark, past the collar, never quite under control
- face: long; deep-set eyes; a scar through the left eyebrow
- dress: a heavy wool coat, worn in every season
```

**folk does not validate labels against a list, and no label name appears in folk's code.** This is invariant 7's reasoning applied one level down: the moment `build|hair|wardrobe` is an enum in `person.py`, adding `gait` or `hands` or `scent` is a code change and a release, and folk has quietly appointed itself the owner of a taxonomy of human bodies — which is both a bad job and a job nobody asked it to do. The consumer decides which labels it reads; the conventional set is documented here and in the `folk` skill, and is guidance, not schema.

Parsing is tolerant in the way `_parse_media` already is: lines that do not match `- label: value` are not errors. They are collected in file order into a free-text `note` alongside the labeled pairs, so a section someone wrote as a paragraph still round-trips and still reaches consumers — it is simply not addressable by field until someone labels it.

`person.show_person` gains `appearance` → `{"labels": [{"label", "value"}, …], "note": "…"}`, order-preserving, JSON-serializable as-is. `folk show` displays it the way it already displays Tags and Voice.

## Decision 3 — durable traits only; staging belongs to the consumer

The line between what goes in folk and what stays in the project is not "physical vs. not." It is **does this change between two frames of the same piece.**

- **folk holds** what is true of the figure whenever you meet them: build, height, face, hair, distinguishing marks, and characteristic dress *when the dress is genuinely part of the identity* (the coat a character is never without).
- **The project holds** what is true of them in this piece or this shot: posture, expression, per-piece wardrobe, what they are holding, and `negative_hints` (a rendering-only lever against a model's pull toward glamour — folk has no reason to care what an image model over-produces).

So `wardrobe` is not banned from folk and not welcome in it either; the label is not the test, the durability is. A uniform someone has worn for thirty years is folk's. What they wore to the beach in frame 04 is the frame's.

This keeps the anchor property intact: everything folk hands back is safe to inherit into every project referencing that slug, because none of it was ever about one scene.

## Decision 4 — in `--format dream`, appearance is a sibling of `description`, never folded into it

`description` stays exactly what it is today — bio, `Archetype:`, `Voice:` — so every existing consumer keeps working byte-for-byte and nothing double-prints. The JSON descriptor gains two additive keys, after `description` in the stable key order:

```json
{
  "kind": "person",
  "slug": "…",
  "name": "…",
  "description": "…bio…\n\nArchetype: …\n\nVoice: …",
  "appearance": [
    {"label": "build", "value": "tall, narrow through the shoulders"},
    {"label": "hair", "value": "dark, past the collar"}
  ],
  "appearance_text": "build: tall, narrow through the shoulders; hair: dark, past the collar",
  "tags": ["…"],
  "associations": ["…"],
  "defining_moments": ["…"]
}
```

**Shipped with a third key, `appearance_fingerprint`** — first 12 hex chars of sha256 over `appearance_text`, the same width and construction journal event ids use, and empty when there is no brief. Decision 9 needs a fingerprint of the consumed brief in every render observation, and having each adapter hash the string itself is the identical drift risk that `appearance_text` exists to remove. One implementation (`person.appearance_fingerprint`), exposed where the adapter already looks.

`appearance` is the structured form, for a consumer that wants to order or select fields (the dream compiler's fixed-order `figure:` clause is exactly that consumer); the free-text `note` deliberately does not appear in it, since an unlabeled line has no field to be selected by — it reaches consumers through `appearance_text`. `appearance_text` is the same content deterministically flattened — labeled pairs joined with `; `, then the free-text `note` appended as its own clause — so a consumer that just wants one more line in a prompt does not have to invent its own join and drift from everyone else's. Both are `[]`/`""` when the section is absent; neither is ever `null`.

`folkref.resolve`'s existing contract checks (`kind` matches the ref prefix, `description` non-empty) are untouched — a figure with no appearance still resolves, still renders, and is not an error. That matters: most people in most collections will never have this section, and a missing shell is the normal case, not a broken record.

The human-readable `folk render --format dream <ref>` (no `--json`) appends an `Appearance:` block after the description when non-empty. This is deliberately *not* the same string as the JSON `description` field — the readable form is for a person checking what a figure looks like, the JSON field is a contract with a compiler. Documented in the docstring so the asymmetry is a choice on the record rather than a bug someone finds later.

## Decision 5 — `--format soul` includes it, after Voice

SOUL.md's stable section order becomes: name, bio, Archetype, Voice, **Appearance**, Associations, Tags, Media, Defining moments — empty sections omitted, never emitted as empty headers, same as every other section. An agent wearing a persona should be able to answer "what do you look like" from its own system prompt rather than improvising a new body each time it is asked. Cost is one template block; there is no reason to make the dream pipeline the only consumer that can see this.

## Decision 6 — no emission gate; the collection's registration *is* the decision

**Resolved 2026-08-12 (maintainer):** there is no opt-in flag and no code path that treats one collection differently from another. If a human wrote `## Appearance`, `folk render` emits it, in every format, from every collection.

The reasoning is that the gate I first proposed would have been a second, weaker copy of a decision the configuration already makes. A collection is registered for a purpose — a dreams collection exists to feed dream projects, `characters` exists to hold fictional figures, the personal collections exist to remember people. Choosing which collection a figure lives in is already the act of choosing what that figure is for, and it is made deliberately, once, by a human editing config. Adding a per-collection boolean on top of that would express the same intent twice and create the standard failure of duplicated intent: the two disagree, and the one that silently wins is the one nobody remembers setting.

It is also more consistent with folk's posture everywhere else. `folk-render.md` Decision 5 puts a hand-edit warning comment in generated SOUL.md rather than a hash check or a lock, on the explicit grounds of "documented convention over code-enforced restriction." Person files are plain git-tracked markdown; nothing stops a hand edit, and the convention is the guardrail. An appearance gate would have been the first place folk restricted what a human may do with their own curated file, for a risk the human is better positioned to judge than the tool is.

What remains, and is enough: appearance is emitted, so a figure whose description should not travel simply does not get one written, or does not live in a collection wired to a renderer. The convention is documented in the `folk` skill rather than enforced in code.

**This resolution is scoped to prose.** Reference images (Decision 8) are a materially different artifact — a likeness a machine can reproduce, not a sentence — and if they are ever designed, the question of who may emit one is reopened from scratch there, not inherited from here.

## Decision 7 — no appearance history; an edit is the whole mechanism

People change. The mechanism for that is editing the person file, and nothing more: the file states the present tense, git holds what it used to say, and there is no timeline, no `as_of`, no per-trait validity window.

This falls straight out of `decay-and-supersession.md`: decay is a read-time lens over *index* facts, and Bedrock person-file facts do not decay — "person-file facts don't decay" is that spec's own phrasing for why render is unaffected by it. Appearance is Bedrock, so it inherits that. If a piece genuinely needs a figure as they were twenty years ago, that is either a distinct entity or a project-local cast file; it is not a folk feature, and building versioned bodies into a people-memory tool to serve one period piece would be the tail wagging the dog.

Note that this does not leave the history nowhere — it puts it where invariant 1 says history goes. The person file holds the present-tense curated definition; the **journal** holds what happened, including which definition a given render actually consumed (Decision 9). So "what did this figure look like when we rendered frame 04 last spring" is answerable, and answerable from the record of events rather than from a versioned field in a Bedrock file. That is the same division of authority the whole system runs on, applied to a body instead of a fact.

## Decision 8 — reference images are out of scope for v1, and stay pointers if they ever land

Given the honest limitation stated above, the obvious next question is whether folk should hold a reference image for a figure. Not in v1, and the deferral is on purpose rather than an oversight.

If it ever lands: folk stores a **pointer**, never an asset (person files are markdown in git; a repo full of faces is a different tool), `## Media` is the existing section for exactly that kind of pointer and no new section should be invented for it, and whatever gate Decision 6 settles on applies at least as strictly to a likeness as to a sentence. Note also that a reference image is materially more sensitive than prose — it is the one form of this data that makes a real person's likeness reproducible by a machine — so it should be its own decision with its own stop-and-ask, not something that arrives as an implementation detail of this spec.

## Decision 9 — tracking is a source adapter, not new machinery

"Which renders used this figure, and which version of the brief did they use" is a question about **what happened**, so it belongs to the journal, and folk already has the exact shape for a non-conversation writer recording its own events: the source adapter (`journal-schema.md`, "Source adapters"; digger is the first one). A render pipeline is the same kind of writer as a music-play exporter.

Concretely, on the rendering side, not in folk:

- **Actor** `import:dream:v1` — a mechanical actor, deterministic, no LLM in its path, which is what earns the observed tier. Compiling a prompt and recording that it happened involves no interpretation.
- **Kind** `observation`, per the rule that mechanical exporters write observations and never promotions.
- **Triple** `person:<slug>` — `depicted_in` — `dream:<project-slug>`. One new predicate registered in `vocab.json` before first run (config, never code — invariant 7 and the adapter registration commitment), with a `p_def` on the way in if it is coined ahead of registration.
- **`src`** `dream:<project>:<render-id>` — an adapter-namespaced row pointer, required, and doubling as the re-export idempotency key exactly as the schema specifies (`id` hashes `ts`, so it is not a dedup key).
- **`note`** carries the **fingerprint of the brief that was consumed**: a short hash of the `appearance_text` folk returned at compile time, plus the folk collection it resolved against. This is the load-bearing part for tracking. It is what makes "these six renders used the old hair description, these four used the new one" a query rather than an archaeology project, and it costs one hash of a string folk already computes deterministically.
- **No `session`** field — there is no conversation behind a render.

What folk contributes is nothing but the predicate registration and the fact that `appearance_text` is deterministic enough to fingerprint. `folk show` then surfaces `depicted_in` like any other triple, and the drill-down path from "this figure" to "the pieces they appear in" comes free from machinery that already exists. Repeated renders of the same figure into the same project are legitimate re-observations, not duplicates, and refresh `last_reinforced` at replay — the schema already says so.

This is deliberately the *whole* tracking mechanism. No render registry in folk, no new record type, no images anywhere near a person file.

## Decision 10 — testing scores what is deterministic, and never judges an image

An appearance definition has properties worth regression-gating, and one property that cannot be automated. Separating them is the entire design, and it follows `promotion-eval.md` Decision 1: **no LLM judge anywhere in the scoring path**, because a model grading a model reintroduces exactly the unmeasurability the harness exists to remove. That rule bites harder here, since the tempting shortcut — hand the render and the brief to a vision model, ask "does this match" — is precisely the banned move.

**Deterministically checkable, and therefore the harness:**

- **Determinism** — compiling a fixture person file twice yields byte-identical `appearance_text`. The same bar every other folk output holds.
- **Coverage** — for a figure referenced by a consumer that reads specific labels, are those labels present? A figure missing `build` entirely is a definition that will drift for a reason having nothing to do with the model. Reported per figure, per collection; missing labels are a finding, never an error, since most people will never have this section at all.
- **Propagation** — does the compiled prompt actually contain the figure's *current* `appearance_text`? A deterministic substring check that catches the stale-artifact failure: a brief was edited, a prompt was never recompiled, and the render drifted for a boring reason. This is the check most likely to catch a real bug, and it never opens an image.
- **Stability** — a golden snapshot of each fixture figure's compiled `appearance_text`, so an unintended change to the flattening (a separator, an ordering) is a diff in a commit rather than a mystery in a render three weeks later.

**Human judgment, and therefore a label file, not a score:** whether a render *looks like* the figure. That is graded by a human, recorded as hand-edited JSON in the corpus, exactly as `promotion-eval.md` Decision 3 treats labeling — "Bedrock-adjacent judgment work the maintainer does when he does it," with the harness required to be useful at corpus size 1. A grade is a label against `(figure, render-id, brief-fingerprint)`, which is why Decision 9's fingerprint matters: it is what lets a grade be attributed to the version of the brief that actually produced the image, so "did the new hair line help" becomes answerable across a handful of graded renders instead of a vibe.

**Home and shape**, following `promotion-eval.md` Decision 4: `eval/appearance/` for fixtures, golden snapshots, and label files; `scripts/appearance_eval.py` as the runner (stdlib only, a dev tool, not a `folk` subcommand — user-facing surface area deliberately zero); the scorer importable so `tests/` can pin its behavior. The one exception to zero surface area: appearance coverage joins the counts `folk stats` already reports per collection (it counts tagged and linked today), because that number is useful outside the harness and costs nothing.

**folk never opens an image file.** Not in the harness, not in the scorer, not anywhere. That keeps the harness stdlib-only (invariant 8), keeps it deterministic, and keeps the one genuinely subjective question in front of a human where it belongs.

## Scope for v1

- `## Appearance` parsing in `person.py`: `_parse_labeled_lines(sections, "appearance")` → `{"labels": [...], "note": "..."}`, order-preserving, tolerant of unlabeled lines; surfaced in `show_person` (and therefore `show_locus`, which delegates).
- `folk show` displays Appearance alongside Archetype/Voice.
- `folk render --format soul`: Appearance block after Voice, omitted when empty.
- `folk render --format dream`: `appearance` and `appearance_text` keys in the JSON descriptor, in stable order after `description`; `Appearance:` block in the readable form.
- `depicted_in` registered in `vocab.json` (config), with `stability: identity` per `decay-and-supersession.md` Decision 2 — a figure having appeared in a piece is a fact that never stops being true, so it must not decay.
- `eval/appearance/` and `scripts/appearance_eval.py`: the four deterministic checks (determinism, coverage, propagation, stability), the label-file layout for human likeness grades, and a starting corpus of one figure — the harness must be useful at corpus size 1.
- Appearance coverage in `folk stats`.
- Determinism preserved: two runs on unchanged input produce byte-identical stdout, verified by diffing two runs (the same discipline `folk-render.md` and `journal-in-folk.md` hold).
- Docs: the conventional label set and the durable/staging rule in the `folk` skill; the `dream-draft` skill §6 and its FAQ ("Does folk store the soul, the shell, or both?") both need rewriting once this ships, since they currently document the absence as permanent.
- No new dependencies (invariant 8).

**Deferred, deliberately:**

- Reference images / likeness anchoring of any kind (Decision 8).
- Any consumer-side change in the dream toolkit — folk emitting the fields and the compiler reading them are two separate pieces of work in two separate repos, and the folk side is useful on its own (`folk show`, SOUL.md) before the compiler reads a byte of it. The render adapter of Decision 9 is likewise the rendering side's work; folk's part is the predicate and the fingerprintable string.
- Any scoring of image content, by any means, including a vision model behind a flag (Decision 10). The prohibition is not about difficulty; it is what keeps the harness meaningful.
- `negative_hints` in folk. It is rendering-only, it belongs in the project overlay where it already lives, and pulling it into folk would put model-drift compensation into a people-memory tool.
- A validated or suggested label vocabulary in `vocab.json`. Labels here are display keys for a human-curated section, not predicates in the index; wiring them to the predicate vocabulary would imply an index relationship that does not exist.
- Appearance anywhere in the index or the journal beyond the ordinary proposal path of Decision 1. No `appearance` triple type, no new predicate.

## Open questions — resolved during implementation

Both were non-blocking and both went the way the draft recommended.

1. **Section name.** `## Appearance` in folk; the dream toolkit keeps calling its clause `figure:` — the consumer owns its own words. `Appearance` reads correctly for a Locus as well as a person and avoids "figure" also meaning body shape specifically.
2. **Locus side.** Parsing is generic and cost nothing (`show_locus` delegates to `show_person`), so a Locus can separate its physical fabric from `## Genius Loci`'s mood and rules if it wants to. The usage stays documented as **provisional** until a real Locus actually wants it — the distinction may well prove to be one without a difference.

## Exit criteria

- A person file with a `## Appearance` section round-trips through `folk show`, the same way `## Archetype` does.
- `folk render --format dream <ref> --json` emits `appearance` and `appearance_text` in stable key order; a person with no Appearance section emits `[]` and `""` and still resolves cleanly through `folkref.resolve` (non-empty `description`, matching `kind`) — no consumer breaks.
- `folk render --format soul` places Appearance after Voice, omits it when absent, and never emits an empty header.
- Two consecutive runs of each format on unchanged input are byte-identical.
- Unlabeled prose written under `## Appearance` reaches `appearance_text` rather than being dropped.
- No label name (`build`, `hair`, `wardrobe`, …) appears anywhere in folk's code, and no collection is treated specially by any appearance code path.
- `scripts/appearance_eval.py` reports the four deterministic checks against a corpus of one figure, scores twice to an identical report, and fails propagation when a fixture's brief is edited without recompiling its prompt (the planted-failure test, mirroring the planted-corruption preservation check in `promotion-eval.md`).
- A human likeness grade round-trips as a label attributed to a specific brief fingerprint, and nothing in the scoring path reads an image or calls a model.
- `depicted_in` events written by a stub adapter replay into the index, survive a re-export without duplicating (same `src`), and never decay.
