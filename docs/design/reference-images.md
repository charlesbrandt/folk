# Reference images — typed pointers, a likeness gate, and where the bytes actually live

**Status:** draft 2026-08-17, not implemented. Reopens `appearance.md` Decision 8 (reference images out of scope) and, separately, its Decision 6 (no emission gate) — which resolved for prose only and said in terms that a likeness reopens the question from scratch. This is that reopening.
**Context:** `docs/design/appearance.md` (Decisions 6, 8, 9, 10 — this spec answers the first two and changes neither of the last two); `docs/design/appearance-checkpoints.md` (the companion spec — a reference image is *of* a checkpoint, and without it this one can only describe a figure at one age); `docs/design/collections-and-graph.md` (collections are config, never code — invariant 7, which constrains the gate mechanism); the dream toolkit's `docs/design/folk-integration.md` and `collections-and-plugins.md` (the `COLLECTION.json` descriptor this reuses rather than reinvents), and its collections' `.gitignore`, which already solves the volume problem correctly for renders.

## Why

`appearance.md` says it up front and it has not stopped being true: **consistent text is not consistent likeness.** A diffusion model handed the same six clauses across twelve prompts produces twelve related-looking strangers. Face-level identity comes from a reference image, a trained embedding, or a pinned seed — and Decision 8 deferred all of it, on the reasoning that folk stores markdown in git and "a repo full of faces is a different tool."

That reasoning splits cleanly into two claims, and only one of them holds. **folk should not hold assets** — true, and this spec keeps it. **Therefore reference images are out of scope** — false, and it conflates folk holding a picture with folk knowing that a picture exists. A typed pointer is text. It is the same move `## Media` already makes for every other kind of artifact folk points at and does not own.

The gap is now load-bearing rather than theoretical: with `## Appearance` landed and checkpoints specified, a figure has an addressable brief and no way to anchor it, which is the ceiling `appearance.md` itself named as the honest limit of what a brief buys.

## Decision 1 — folk stores a pointer, never an asset

Unchanged from Decision 8, and this is the half of Decision 8 that was right. Person files stay markdown in git. folk gains no image code, opens no image file, computes no perceptual hash, and adds no dependency (invariant 8). The prohibition in `appearance.md` Decision 10 — nothing in the scoring path may read an image or call a model, asserted by a test on what the harness imports — extends to every path this spec touches, unweakened.

What changes is only that the pointer becomes **typed and addressable** instead of absent.

## Decision 2 — Git LFS is not available end-to-end here today, and that is a finding, not a preference

Measured 2026-08-17:

| Host | State |
|---|---|
| This machine | `git-lfs` **not installed** |
| Git server | `git-lfs 3.7.1` installed; `git-lfs-transfer` **missing**; `git-lfs-authenticate` **missing** |

The remotes in question are bare repositories over plain SSH. Classic LFS needs `git-lfs-authenticate` on the server to hand back an HTTP endpoint; pure-SSH LFS (client 3.0+) needs a `git-lfs-transfer` agent server-side. Neither exists, and the client binary sitting on the server does nothing for a bare repo by itself. So adopting LFS is standing up a transfer agent or an HTTP endpoint, plus installing the client on **every** host that clones — this machine, both GPU boxes, the server — not adding a line to `.gitattributes`.

The failure mode of partial adoption is the part that matters, and it lands precisely on the hosts that render: a clone on a host without the client silently produces ~130-byte pointer text files where images should be. A compiler then reads one as a reference image and the render proceeds — no error, wrong output. That is the same failure class the whole gate/`!`-line discipline exists to prevent, arriving through infrastructure instead of through a frame.

## Decision 3 — the volume instinct is right about renders and wrong about references; measure before adopting

The reflex that binary data bloats a repo is correct, and it is correct about **renders**: hundreds of multi-megabyte outputs, machine-produced, regenerable. The dreams collections already handle exactly that, correctly, with no LFS at all — `*/renders/*` is gitignored and `manifest.jsonl` is the bridge back to the bytes.

A **reference** set is a different population, because Decision 4 makes it one. It is bounded by human approval: every file in it is one a person chose. A curated set for a book's cast is tens of files at tens of kilobytes — an estimate, but not a close call: a 512×512 webp headshot runs roughly 40–80 KB, so ~20 figures × ~3 checkpoints × ~2 views ≈ 120 files ≈ 8 MB, against a notes repository whose `.git` already measures 182 MB. That is noise, and it is noise that compresses and dedupes like any other blob.

**Recommendation: do not adopt LFS now.** Adopt against a measured trigger instead, recorded here so the decision is revisited by measurement rather than by feeling: **any single reference store exceeding ~250 MB or ~500 files.** If that is ever hit, Decision 2's infra work is the price and it is worth paying at that size; below it, LFS buys a pointer-file failure mode on the render hosts in exchange for nothing.

## Decision 4 — a reference image is a promoted render, and promotion is a human act

This is the decision that makes Decision 3's premise true rather than lucky, so it is not merely a workflow note.

A render lands in `renders/` as cache, like every render. A human looks at the set, picks one, and *that act* copies it into the reference store and writes the pointer line into the person file. **Nothing mechanical ever writes a `## Reference` line** — same rule as every other Bedrock section, and the same graduation pattern the architecture runs everywhere else: the local cast directory is the unvetted nursery, folk entities are reference-only, and crossing between them is a human decision with a diff in front of it.

A proposal path exists if wanted and needs nothing new: a render adapter may write a journal `observation` that a candidate exists, and `folk review` shows it like any other suggestion. The accept is still the human's.

## Decision 5 — `## Reference`, a new section, rather than `## Media`

`appearance.md` Decision 8 said, in the event this ever landed, to reuse `## Media` and invent no new section. Recommend overriding that, on that same document's own precedent.

`## Media` parses as `- ref — note`: free text on both sides. Role and checkpoint would therefore live inside prose, and a consumer could not ask for "the age-7 headshot" without parsing a note folk does not own and will not validate. That is exactly the unaddressability argument that justified `## Appearance` over a paragraph of bio — *"a consumer cannot ask for hair without taking the whole bio"* — and it applies here without modification. `## Media` also keeps a meaning worth keeping: works this figure appears in. A reference image is not a work.

```markdown
## Reference
- headshot, age 7: refs/january-scaller/age-7-headshot.webp
- sheet, age 7: refs/january-scaller/age-7-sheet.webp
```

Same `- label: value` convention as `## Appearance` and `## Dates`, so it reuses a parser and a documented habit rather than adding a third line grammar. Labels are opaque and no label name appears in folk's code, per invariant 7's reasoning one level down — identical to the appearance-label rule and covered by the same grep test. Values are store-relative paths or URIs; folk does not resolve, fetch, size, or open them, and validates nothing beyond Decision 7.

The label convention that pairs with `appearance-checkpoints.md` is `<role>, <checkpoint>` — documented as guidance in the `folk` skill, never as schema, so a consumer that wants only `headshot` or only a checkpoint can match on its own terms.

## Decision 6 — the likeness gate is per-collection, fail-closed, and reuses the collection descriptor

`appearance.md` Decision 6 resolved that prose has no emission gate: the collection's registration already states what a figure is for, and a second flag would express the same intent twice. It also scoped that resolution explicitly — *"reference images are a materially different artifact… the question of who may emit one is reopened from scratch there."*

It should reopen to a different answer. A likeness is the one form of this data that makes a specific person reproducible by a machine, and the registered collections include real people alongside fictional ones. The asymmetry that made a prose gate redundant does not survive the change of artifact: the cost of a wrong emission is no longer a sentence traveling somewhere it need not, it is a face.

**Mechanism:** a `COLLECTION.json` descriptor in the collection root — the same file already proposed for `curation` in the dream toolkit's `collections-and-plugins.md`. Reuse it; do not invent a second per-collection policy mechanism, and do not enumerate collections in code (invariant 7).

```json
{"curation": "human", "likeness": "emit"}
```

`likeness` absent, unreadable, or any value other than `emit` ⇒ **withhold**. Every existing collection is therefore protected without being touched, which is the same fail-closed shape the `curation` decision already chose for minting. A fictional-character collection opts in with one line.

Withheld means `folk render` omits the `reference` key **entirely** rather than emitting an empty one, and the readable form says why — a consumer should be able to tell "this figure has no references" from "this collection does not emit them", and an empty list conflates them.

This gates **emission to a renderer**, not authorship: a human may always write a `## Reference` line, and `folk show` always displays what is written. The gate is about handing a likeness to a machine that will reproduce it.

## Decision 7 — one filesystem check, and only one

`folk index --verify` reports dangling reference pointers: a store-relative path with no file at it. This is a `stat`, not an open — no bytes read, no format checked, no dimensions, no hash. It costs nothing, adds no dependency, and catches the two failures that actually occur: a file moved out from under a pointer, and Decision 2's LFS pointer stub sitting where an image should be (a plausible size check on a path claiming to be an image is the cheapest possible detector for that, and is the one extension worth considering).

URIs pointing at an external store are reported as unverifiable rather than as broken. folk does not make network calls to check them.

## Decision 8 — where the bytes live is per-collection, and the first store is the boring one

**This is the stop-and-ask.** Four candidates:

| Store | Fits | Cost |
|---|---|---|
| **(a) Plain git, in the collection's own repo** | a curated, bounded, text-adjacent set — a book's cast | none today; revisit at Decision 3's trigger |
| (b) Git LFS, same repo | a set that outgrows (a) | Decision 2's infra work, on every host |
| (c) A non-git content store, folk holding URIs | real people; anything already photographed | an integration; the photo/media server in the stack is the natural one and already has a backlog item |
| (d) The dreams collection repo | figures that exist only to be rendered | already visibility-partitioned; wrong home for anything folk-canonical |

**Recommendation:** (a) for a fictional-character collection now, (c) for any real-person collection if that ever happens — a likeness of a real person belongs in the system that already holds their photographs, under whatever access control that system has, not newly duplicated into a notes repository. Re-evaluate against Decision 3's trigger, not before.

Note the store is a per-collection choice and folk does not need to know which was chosen: a pointer is a pointer. The only thing folk needs is a per-collection base path for resolving store-relative values, which the descriptor of Decision 6 is already the natural place for.

## Decision 9 — render tracking is unchanged

`appearance.md` Decision 9 already specifies it and this spec adds no machinery: the render-side adapter (`import:dream:v1`, mechanical, observed tier) writes `person:<slug>` — `depicted_in` — `dream:<project-slug>`, with the consumed brief's fingerprint in the `note`. The one extension, and it is the rendering side's to make: the note should also carry which reference labels conditioned the render, so "these renders used the age-7 sheet" is a query rather than an archaeology project — the same argument that put the fingerprint there.

`depicted_in` is already registered in `vocab.json` with `stability: identity`. Nothing here changes the predicate, the event shape, or the index.

## Scope for v1

- `person.py`: parse `## Reference` on person and Locus files, reusing the `- label: value` convention.
- `config.py`: read `COLLECTION.json` if present; expose `likeness` and an optional store base path. Absent or unreadable ⇒ fail closed.
- `render.py`: a `reference` key in `--format dream --json`, present only when the collection emits; omitted entirely otherwise, with the readable form stating why. `--format soul` does **not** carry references — a system prompt has no use for an image path and every reason not to carry one.
- `index --verify`: dangling-pointer reporting per Decision 7.
- `web/`: references shown on the person page read path, respecting the gate. No write path in this pass, and no image proxying — the web UI displaying a likeness is its own decision with its own exposure question.
- Tests, including the label-name grep extension and a fail-closed test per gate state.
- Docs: the `folk` skill (the section, the label convention, the gate, and the storage recommendation); `appearance.md` annotated to point at this spec where Decisions 6 and 8 are superseded.

**Deferred, deliberately:** any image scoring, perceptual hashing, or vision model, behind any flag (`appearance.md` Decision 10, unweakened); embeddings, LoRA training, or any likeness anchoring machinery — that is entirely the rendering side's, and folk's contribution is the pointer; interpolation of any kind (`appearance-checkpoints.md` Decision 6); folk fetching, copying, resizing, or writing an image byte anywhere, ever; a reference anywhere in the index or journal beyond Decision 9's existing predicate.

## Open questions for a human

1. **Decision 8's store** — the stop-and-ask above. Plain git in the collection repo is the recommendation and nothing else can be built until it is settled, because the pointer values' meaning depends on it.
2. **Overriding `appearance.md` Decision 8's "reuse `## Media`"** (Decision 5 here). The addressability argument is strong and it is that document's own, but it is still a reversal of a written decision and should be an explicit yes.
3. **Decision 3's trigger numbers** (~250 MB / ~500 files). Chosen to be obviously safe rather than tuned; worth a second opinion since their whole job is to be checked later rather than argued about now.
4. **Whether a real-person collection ever gets `likeness: emit` at all.** The gate makes it possible. Nothing in this spec recommends it, and the default answer being "no, forever" is a coherent and probably correct position worth stating on the record either way.

## Exit criteria

- A person file with `## Reference` round-trips through `folk show`, on a person and on a Locus.
- With `{"likeness": "emit"}`, `--format dream --json` carries a `reference` list in stable order after the appearance keys; two consecutive runs are byte-identical.
- With the key absent, unreadable, malformed, or set to anything else, the `reference` key is **absent** from the JSON — not empty — and the readable form says the collection does not emit likenesses. Tested per state, including a `COLLECTION.json` that is not valid JSON.
- A collection with no `COLLECTION.json` at all behaves exactly as today, byte-for-byte, on every format.
- `--format soul` never emits a reference under any configuration.
- `folk index --verify` reports a pointer with no file behind it, reports a URI as unverifiable, exits non-zero only under the existing verify semantics, and opens no file.
- No label name and no collection name appears in `folk/`, enforced by the extended grep test.
- No import anywhere in folk's source can read an image; asserted the same way `appearance.md` Decision 10 asserts it for the harness.
- A figure whose collection withholds likenesses still resolves cleanly through `dreamkit/folkref.py` — non-empty `description`, matching `kind` — so the gate is never a compile break.
