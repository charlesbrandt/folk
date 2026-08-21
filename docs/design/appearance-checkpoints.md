# `## Appearance: <checkpoint>` — concurrently-valid appearance states

**Status:** draft 2026-08-17; both open questions confirmed by the maintainer 2026-08-18 (see "Open questions for a human"); implemented 2026-08-21 (`docs/HANDOFF.md` task 12). Reopens `appearance.md` Decision 7 ("no appearance history") and scopes it rather than overturning it.
**Context:** `docs/design/appearance.md` (Decisions 1–4 and 7 in particular — this is an extension of that section, not a new one); `docs/design/reference-images.md` (the companion spec — a reference image is *of* a checkpoint, so the two land together or the second lands alone and useless); `docs/design/folk-render.md` (Decision 4, `--format dream`, the consumer surface); `docs/design/decay-and-supersession.md` (why Bedrock facts do not decay, which is the rule this spec must not quietly break); the `folk` skill's "Fiction Character Maps" section (the chapter-gated companion pattern, which turns out to share this spec's axis exactly).

## Why

`appearance.md` Decision 7 rejected appearance history outright: the person file states the present tense, git holds what it used to say, and there is no `as_of`, no timeline, no per-trait validity window. That reasoning is correct and this spec does not touch it.

It does not, however, cover the case that actually arrived. A narrator is seven years old in chapter 1 and seventeen in chapter 2, and both are permanently true — neither replaces the other, and there is no moment at which the earlier one becomes wrong. A person file that must choose one is choosing which half of a book it can illustrate.

That is not history. History is a **superseded** state: hair was long, hair is now short, the old value is dead and git is the right place for a dead value. What a character has instead is **simultaneous multiplicity**: two or more states that are concurrently canonical, forever, with no ordering that makes one of them the answer. Decision 7 never contemplated a subject like that, because it was reasoning about people who change. So Decision 7 stands unchanged for what it decided, and this spec adds the thing it did not decide.

The same shape appears outside fiction wherever a subject is *defined* across more than one state rather than moving through them — a figure whose ceremonial and working presentation are both permanent facts about them, a place in two seasons. It is not a fiction-only feature, and nothing in the mechanism knows what a book is.

## Decision 1 — the test is "does the earlier value stop being true", and history keeps its answer

| Question | Answer | Where it goes |
|---|---|---|
| Did the old value become wrong? | yes → **history** | edit the file; git holds the past (Decision 7, unchanged) |
| Are both values still true? | yes → **checkpoint** | this spec |

Applying the test is a human act at write time and needs no code. Getting it wrong in the "history" direction costs nothing (a stale checkpoint nobody selects); getting it wrong in the "checkpoint" direction produces a file that asserts two contradictory present tenses, which is a curation error the same way any wrong Bedrock line is, and is fixed the same way.

Explicitly still rejected, because this spec must not become the timeline Decision 7 refused: **a checkpoint is not a date.** No `as_of`, no validity window, no ordering, no interval arithmetic, nothing derived from a wall clock anywhere in this path. A checkpoint is an opaque name for a state, and folk never compares two of them.

## Decision 2 — a suffixed section heading, merged deterministically over the base

```markdown
## Appearance
- skin: coppery, "an in-between sort of thing" by the world's reckoning of her
- eyes: round and light, set wide

## Appearance: age 7
- build: small for her age, sharp-elbowed, always slightly untidy
- dress: whatever Mr. Locke's money chose for her — good cloth, stiff, never hers
```

`## Appearance` is what is true at every checkpoint. `## Appearance: <name>` is what is true at that one. The merge is: base first in file order, then each checkpoint label — a label present in both is **overridden** by the checkpoint and keeps the base's position; a label new to the checkpoint appends in its own file order. Pure, ordered, no sorting, no set arithmetic, byte-identical across runs, same discipline as every other render path.

Unlabeled prose under either heading concatenates into `appearance_text` in the same order, exactly as `appearance.md` Decision 2 already specifies.

**Rejected — the checkpoint in the label** (`- age 7 / build: …`). It is genuinely zero code, because folk already treats labels as opaque strings, and that is its whole appeal. It is wrong anyway: the checkpoint becomes visible only to a consumer that shares a parsing convention folk has deliberately refused to own, which is the exact unaddressability problem `## Appearance` was built to fix in the first place. A convention folk will not parse is not a slot.

**Rejected — one person file per era** (`person:january-scaller-age-7`). It fragments a single identity into entities that `folk lookup` will correctly report as near-duplicates, multiplies every association edge by the number of eras, and makes a graph of a book's cast unreadable. `appearance.md` Decision 7's aside about "a distinct entity" was about a subject that is genuinely a different person-shaped thing, not about one person at two ages.

## Decision 3 — folk never enumerates checkpoint names

`age 7`, `chapter 1`, `after the fire`, `winter`, `dress uniform` — all equally valid, and folk stores the string without opinion. This is invariant 7's reasoning at the same level `appearance.md` Decision 2 already applied it to labels: the moment a checkpoint vocabulary exists in `person.py`, folk has appointed itself the owner of a taxonomy of how subjects vary, which is a worse job than owning a taxonomy of bodies and equally unasked-for.

Enforced the way the label rule already is — `tests/test_appearance.py::TestNoLabelNamesInFolkCode` greps `folk/`; this adds checkpoint names to the same grep rather than adding a second test with a second idea of the rule.

## Decision 4 — render selects one checkpoint; the default is base-only and never an implicit merge

```bash
folk -C characters render --format dream person:january-scaller --checkpoint "age 7" --json
```

- **No `--checkpoint`**: the base section alone. Merging every checkpoint by default would produce a figure who is seven and seventeen simultaneously, rendered confidently — the worst available failure, because it looks like output rather than like an error.
- **Unknown checkpoint**: hard error, naming the ref and listing the checkpoints that do exist. Falling back to the base would be a good render of the wrong thing, the failure class `compile.py`'s `!` lines exist to prevent.
- **New JSON keys**, after the existing appearance trio and in stable order: `checkpoint` (the selected name, `""` when none) and `checkpoints` (every available name, in file order, **always emitted**, so a consumer can enumerate without a second subprocess). A figure with no checkpoints emits `""` and `[]` and is otherwise byte-identical to today's output — no consumer breaks, same additive discipline `appearance.md` Decision 4 held to.
- **`appearance_fingerprint` hashes the merged text.** Each checkpoint therefore fingerprints distinctly and `appearance.md` Decision 9's render tracking keeps working per-checkpoint with no change to the adapter contract: "which version of the brief did this render consume" becomes "which version of *which* brief", answered by the same 12 hex characters.
- **The flag is format-agnostic** — `--format soul` accepts it too. Adding a per-format exception would be a special case earning nothing; a persona view of a figure at a named state is a coherent thing to want, and the merge is the same merge.

## Decision 5 — reading progress and the checkpoint set are the same axis

For a book being read, write only the checkpoints reached. Chapter 1 of the current companion yields exactly one, `age 7`; nothing later exists in the file, so nothing later can be rendered, and the spoiler barrier is a property of what has been written rather than a filter someone has to remember to apply.

This is worth stating because it was not designed for: the chapter-gated companion pattern and this mechanism were built for unrelated reasons and land on the same axis. The practical effect is that advancing your reading and extending a figure's renderable range are one action, and the safe default (a figure who can only be rendered as far as you have read) is what falls out of doing nothing.

## Decision 6 — interpolation between checkpoints is never folk's work

The requested capability has three names worth separating: **interpolation** between two known checkpoints, **extrapolation** beyond the outermost one, and — for faces specifically — **age progression** or **regression**. All three are generative, and all three are prohibited here by rules that already exist rather than by a new one:

- `folk render` is pure deterministic templating with no model call, byte-identical on unchanged input (`folk-render.md`), and the whole rebuild path is LLM-free (invariant 4).
- folk never opens an image file — `appearance.md` Decision 10 asserts this with a test that the scoring path imports nothing that could.

So the two artifacts route to the two paths folk already has:

- an interpolated **image** is a render, and lives in the render manifest as cache like every other render, promoted to canon only by a human (see `reference-images.md` Decision 4);
- an interpolated **text** brief is a proposal, and lands in `folk review` as a `level: bedrock` suggestion with a diff, accepted by a human — the ordinary path `appearance.md` Decision 1 already describes for any proposed appearance fact.

Neither needs anything built in folk. What folk contributes is that the bracketing checkpoints are addressable and individually fingerprinted, which is what makes an interpolation a well-posed request instead of a vibe — the generator can be told what it is interpolating *between*, and the result can be recorded against both endpoints.

## Worked example — chapter 1 only

The current reading ceiling is chapter 1, so this is the entire renderable set for this figure. `person:january-scaller`'s file gains:

```markdown
## Appearance
- skin: coppery, "an in-between sort of thing" by the world's reckoning of her (ch. 1)
- eyes: round and light, set wide (ch. 1)

## Appearance: age 7
- build: small for her age, sharp-elbowed (ch. 1)
- dress: chosen by Mr. Locke's money — good cloth, stiff, correct, never hers (ch. 1)
```

The `(ch. 1)` citations ride free: values are opaque to folk, so provenance costs nothing and no parser learns about chapters. They also keep the repo's standing rule that a book's own text stays out of git — cite the chapter, quote a phrase at most, never a sentence.

Note what is *absent* and must stay absent while the ceiling holds: no `age 17` checkpoint, no appearance detail sourced from any later chapter, and no checkpoint named after an event not yet read — a checkpoint name is itself a spoiler surface, since `checkpoints` is always emitted.

## Scope for v1

- `person.py`: parse `## Appearance: <name>` sections; a `checkpoints` structure alongside the existing `appearance` one; the ordered merge of Decision 2.
- `render.py`: `--checkpoint` on `--format dream` and `--format soul`; the two new JSON keys; merged-text fingerprinting; the unknown-checkpoint error.
- `cli.py`: the flag, and `folk show` displaying available checkpoint names (not their contents — `show` stays a summary).
- `web/`: `checkpoints` surfaced on the person page read path. No write path in this pass.
- Tests, including the grep test extension of Decision 3.
- Docs: the `folk` skill's Person File Format section; `dream-draft` §6, which will by then have just been corrected once already for `## Appearance` and must not be corrected into describing checkpoints before the compiler reads them.

**Deferred, deliberately:** any consumer-side change in the dream toolkit (its own repo, its own work — folk emitting the keys is useful to `folk show` and SOUL.md before a compiler reads a byte); any ordering, comparison, or arithmetic over checkpoint names; any inference of a checkpoint from a date, an age, or a tag; a checkpoint anywhere in the index or the journal — this is a person-file section, and no triple, predicate, or event shape changes.

## Open questions for a human

1. ~~Does `## Appearance: <name>` warrant a heading-suffix convention folk will reuse elsewhere?~~ **Resolved 2026-08-18 (maintainer): yes, parse the suffix generically now** — used for Appearance only today, but written once so a second consumer (`## Voice: <checkpoint>` is the obvious next request) needs no parser rework.
2. ~~`folk show`'s default.~~ **Resolved 2026-08-18 (maintainer): base-only**, with checkpoint names listed — per Decision 4's principle, no implicit merge, ever, including on `show`.

## Exit criteria

- A person file with a base `## Appearance` and two `## Appearance: <name>` sections round-trips through `folk show`, which lists the checkpoint names.
- The merge is base-then-override in file order, with an overridden label holding the base's position; verified by a fixture whose checkpoint overrides one label and adds one.
- `--checkpoint` on both formats; two consecutive runs of each are byte-identical; the fingerprint differs between checkpoints and is stable across runs for each.
- No `--checkpoint`: base only, provably not a merge (a fixture whose checkpoint contradicts the base renders the base's value).
- An unknown checkpoint exits non-zero, names the ref, and lists the available names.
- A person with no checkpoint sections emits `checkpoint: ""` and `checkpoints: []`, and resolves through `dreamkit/folkref.py` unchanged — non-empty `description`, matching `kind`, existing contract checks passing untouched.
- No checkpoint name appears anywhere in `folk/`, enforced by the extended grep test.
- Nothing in this path reads a wall clock, sorts a checkpoint set, or compares two checkpoint names.
- The worked example above renders at `--checkpoint "age 7"`, and `checkpoints` contains exactly that one name.
