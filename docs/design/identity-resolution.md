# Identity resolution — deciding whether a name is someone folk already knows

**Status:** open design sprint, **not** confirmed by the maintainer. This is a **living reference**, not a one-shot spec: it is meant to be edited in place as implementation experience (starting with the bulk import landing in parallel) contradicts it. Anything here that survives contact with real data should be tightened; anything that doesn't should be rewritten in place with a line in the revision log at the bottom rather than quietly deleted. Nothing proposed here changes `journal-schema.md`'s frozen event shape or the index record shape; the parts that would need maintainer sign-off before implementation are collected in `## Open questions` rather than defaulted.
**Context:** `docs/design/journal-schema.md` ("Source adapters" — the `folk lookup` contract and the never-auto-merge rule); `docs/design/journal-in-folk.md` ("Entity resolution for object slugs" — the three-part fix whose part 2 is the mechanism this doc replaces, and whose part 3, the `aliases` map, this doc extends); `docs/design/review-queue.md` (item type 3, entity-resolution proposals); `docs/design/decay-and-supersession.md` (the closest prior art in this repo for resolving ambiguity without a score — its `functional`/supersession design is the pattern followed below); `docs/design/bulk-import.md` (sibling spec, written in parallel — the seam is stated explicitly in Decision 4); `folk/graph.py` `find_person`, `folk/journal.py` `_near_duplicate` / `lint_events_detailed`, `folk/review.py`.

## Why

folk is about to be asked to do something it has never done: absorb a large one-shot import of real people from an organizational directory, and then absorb the same source again months later without minting a second copy of everybody. Directory data produces exactly the cases the current mechanism handles worst — common surnames, the same person listed under two departments or two profile pages, credentials and titles riding along inside a scraped name field, "Last, First" ordering, middle initials that appear in one source and not another, and people who get retitled or move teams between scrapes so that everything *except* their name has changed. The same class of problem recurs in a companion project that reconciles music metadata from several sources (a band listed as `The X` in one source and `X, The` in another; romanization variants of the same artist), where the maintainer reports it as an unsolved, recurring pain point rather than a solved one.

folk's entire answer today is one function: a token-set Jaccard overlap over the slug string, thresholded at 0.6, returning a single best match. That is not a weak version of the right tool; it is a different tool, and the first half of this doc is about being precise about that, because the temptation is to "tune the threshold" or "add a weight," and both of those roads lead directly into invariant 5.

## What `_near_duplicate` actually does

`journal._near_duplicate(slug, known_slugs, threshold=0.6)` tokenizes a slug by splitting on `[-:]`, keeps only candidates sharing the same type prefix, computes `len(a & b) / len(a | b)` over those token *sets*, and returns the single highest-scoring candidate at or above 0.6. `graph.find_person` calls it once, after an exact-slug check and an exact-display-name check, and wraps the single result in a one-element `near_matches` list. `journal.lint_events_detailed` calls it on promotion events' object slugs. That is the whole mechanism, end to end, in both places it is used. Its concrete failure modes:

**Tokens are compared by exact string equality, so it detects no spelling variance whatsoever.** It is not a similarity measure; it is a set-containment detector over exact tokens. Two-token person slugs that differ in one token can reach at most `2/4 = 0.5` overlap (the shared type prefix is counted as a token — see below), which is under the threshold, so *no* pair of two-token names differing in one token is ever flagged. Every match it can find is either a reordering (`smith-jane` vs `jane-smith` → 1.0) or a strict superset (`jo-a-quill` vs `jo-quill` → 0.75; `jo-quill-md` vs `jo-quill` → 0.75). That is a real and useful class — it happens to cover middle initials and credential suffixes — but it is the *only* class.

**The type prefix is counted as a shared token, inflating every comparison.** `_slug_tokens` splits on `[-:]`, so `person:jo-quill` yields `{person, jo, quill}` and the `person` token is present in both sides of every comparison (candidates are already filtered to the same prefix). Every score is inflated by one guaranteed-shared token, and the inflation is larger for short names. This is invisible in the code's intent and load-bearing in its behavior.

**Generic tokens produce false positives, and they are exactly the tokens a scraped name field adds.** A scraped name field carrying a title or credential gives `person:dr-jo-quill` and `person:dr-ada-vane`: intersection `{person, dr, jo|ada…}` — concretely, `{person, dr}` plus nothing else is `2/6`, but add any shared given-name token and it clears the bar; `person:dr-jo-quill` vs `person:dr-jo-vane` is `3/5 = 0.6`, flagged, on the strength of the token `dr` alone. The mechanism has no notion that some tokens carry identity and some do not.

**Legitimately distinct people who are token-supersets of each other are flagged, and there is no way to say "no, these are two people."** `jo-quill` vs `jo-quill-jr` scores 0.75. A human can answer that once, but folk has nowhere to record the negative answer (see Decision 7), so the same pair is re-proposed on every subsequent run.

**Slugification is lossy in ways that create false negatives.** `graph.slugify` maps anything outside `[a-z0-9]` to a hyphen, so diacritics and apostrophes silently destroy tokens: a name with `ë` becomes a truncated token, `o'brien`-shaped names become `{o, brien}` and share nothing with `{obrien}`, and romanized forms with macrons truncate mid-token. These are precisely the music-metadata cases, and token-set overlap cannot see them at all. Worse, there are **four** slightly different name-normalizing code paths — `graph.slugify`, the inline `re.sub` in `journal._person_triples` and again in `journal._locus_triples`, and `person._find_person_file`'s `lower().replace(" ", "-").replace("_", "-")` — so "the slug for this name" is not a single well-defined thing today.

**Mononyms degrade to nothing.** Single-token names (common for musicians, occasional for people) share only the type prefix, `1/3`, never flagged, ever.

**No signal beyond the slug string is used.** The person file's bio, `## Tags`, `## Associations`, `## Dates`, and the `src` provenance of the record that provoked the question are all sitting right there, and none of them is consulted — not even to *show* the human deciding.

**One best match, no ranked list.** `find_person` returns at most one near match. If a common surname genuinely matches four existing people, the human is shown one of them and never learns the question was four-way.

**One magic number carries the whole design.** The 0.6 is in a default argument, undocumented as to how it was chosen, and does everything: it is simultaneously the answer to "how much spelling variance is tolerable," "how many extra tokens may a name carry," and "how generic may a shared token be." It is not forbidden by invariant 5 — that invariant is about *trust in facts*, not string comparison — but it is the same failure shape, and the obvious next step (weight the signals and sum them) would produce a confidence number by another name. The design below is built to make that step unnecessary rather than to make it tidy.

**Two live defects worth naming separately**, both found while reading the code for this doc, both fixed by the v1 scope below:

1. **Lint checks only the `o` field.** `lint_events_detailed` runs the near-duplicate check under `elif field == "o"`, so a promotion whose *subject* is a newly coined near-duplicate person slug is never flagged. Adapter-minted people are subjects far more often than objects.
2. **Rejecting an entity proposal silently deletes a good fact.** `review.record_review` writes a `kind: review` event whose `ref` is the *promotion event's* id, and `replay` drops all triples of any event with `verdict: reject`. For a vocab or bedrock item that is correct. For an entity item it is not: answering "these two are not the same person" also throws away the fact the promotion asserted. Reject currently conflates "this is not a duplicate" with "this fact is wrong."

## Decision 1 — resolution is a lookup against recorded anchors, not a measurement

The structural move, and the one that follows `decay-and-supersession.md` most directly: **stop trying to make the guess better and start making the human's answer durable.** In that spec, the machine does not decide whether two facts conflict — a human classifies the *predicate* once, in `vocab.json`, and rebuild then acts deterministically forever after. Identity resolution takes the same shape: a human decides once that two name strings denote the same person, that decision is recorded in the record that owns identity, and every subsequent lookup of either string is an **exact** match, not a similarity question.

Two anchor carriers, both human-tier, both ordinary person-file conventions in the style of `## Tags` and `## Dates`:

- **`## Also known as`** — one alternate name string per line (`- Quill, Jo`, `- Jo A. Quill, MD`). Curated Bedrock, human-owned like the rest of the file. At lookup and rebuild time these normalize (Decision 2) into an alias table mapping alternate → canonical slug.
- **`## Identifiers`** — one `namespace: id` per line (`- staffdir: 12345`), the stable external identity anchors of Decision 4.

Both are parsed exactly like `## Dates` is today (`person._parse_dates` is the template: tolerant line regex, malformed lines skipped, returns plain dicts). Neither adds an index record field, and neither needs to emit triples in v1 — they build a derived map, so nothing becomes authoritative in two places (invariant 1). `vocab.json`'s existing `aliases` map stays exactly as it is for entity types that have no file (`topic:`, `work:`); for entities that *do* have a file, the file is the authority and `aliases` is not written.

Why the file rather than config: an aka is a fact about a person, it belongs in the record a human curates and git tracks, it survives deleting the index, it is visible in the diff when someone reviews an import, and it makes `folk lookup` correct without a rebuild having run.

**The machine never merges two person files.** Accepting a match writes at most an aka line; two markdown files are merged by a human with an editor and git. That is invariant 1, and it is also the honest position: a merge destroys curated text and is not recoverable from any derived record.

## Decision 2 — matchers are named, discrete, and ordered by config; there is no combined score

Candidate *generation* and candidate *presentation* are different problems, and today's code conflates them (one function both finds and decides). Split them.

Generation is a set of **named matchers**, each a deterministic predicate that either fires or does not, each returning a short reason string when it fires. Which matchers are enabled, and in what precedence order, is data in config (an `identity` block in `vocab.json`, alongside `stability`/`functional`/`decay` — same file, same load/save path, no new config file for v1). No matcher name is enumerated in folk's code as a policy decision; the code registers implementations, the config decides which are on and how they order (invariant 7's spirit).

Starter matcher set, all stdlib, all deterministic:

- `exact_slug`, `exact_display_name` — what `find_person` already does.
- `identifier` — an external id from `## Identifiers` matches (Decision 4). Highest precedence.
- `aka` — the query normalizes to a recorded alternate name.
- `normalized_name` — **the workhorse.** Normalize both sides (NFKD-fold diacritics via `unicodedata`, drop apostrophes rather than splitting on them, lowercase, drop tokens present in a config-curated `generic_tokens` list of titles/credentials/particles, sort the remaining tokens) and test for **equality**, not overlap. This one predicate covers "Last, First", credential suffixes, diacritic variants, and apostrophe variants — most of the directory cases — and it is a discrete yes/no, not a threshold.
- `initials_expansion` — token multisets equal after treating single-letter tokens as optional. Covers the middle-initial case discretely.
- `surname_and_given_initial` — deliberately weak, off by default; the case where one source abbreviates the given name.
- `fuzzy_string` — the only ratio-based generator (stdlib `difflib.SequenceMatcher`; `difflib` is already imported in `review.py`). **Off by default**, its cutoff in config, and structurally demoted: it may only *propose* candidates, its ratio never appears in any output, and its candidates always sort last and are always labeled as machine-guessed. It exists so the design has an escape hatch for variance nothing else catches, not as the mechanism.

Candidates come back as an **ordered list** — `[{"slug", "name", "reasons": [...]}, ...]` — ordered lexicographically by the precedence of the matchers that fired, exactly the way `TIER_RANK` orders trust tiers today. That ordering is not a score and must not become one, by this test, which is the invariant-5 line for this doc:

> **Discrete, named, ordered kinds of evidence are fine — that is precisely what trust tiers are. A continuous magnitude, computed from several signals, compared across unrelated pairs, and thresholded, is a `conf` number regardless of what it is called.**

Concretely, that forbids: summing or weighting matcher outputs; exposing any ratio in `folk lookup --json`, in `folk review` output, or in an index record; and ranking a pair from one source against a pair from another by a common numeric yardstick. It permits: a fixed precedence order over named matchers, and a per-matcher configured cutoff internal to that one matcher.

## Decision 3 — attributes corroborate for the human's eyes; they never feed ranking

The obvious next thought is to use `## Tags`, `## Associations`, and `## Dates` as additional match signal. Reasoned through against folk's actual data, that is right for presentation and wrong for generation, for a base-rate reason: in a directory import, *everyone* shares the department tag and the employer association, so tag overlap is near-worthless as identity evidence exactly where it would be used most. Making rare agreement count more requires a rarity measure, a rarity measure is a count, and a thresholded count over combined signals is the `conf` number again.

So the rule is: **corroborating attributes are rendered next to a candidate for a human to read, and are not inputs to whether the candidate exists or where it sorts.** Two exceptions, both discrete and both about *separation* rather than support, both allowed because they can only suppress or annotate, never rank:

- **Conflicting `## Dates`** — two records with different birthdays are not the same person. A matching birthday is strong corroboration and is displayed prominently; a conflicting one suppresses the candidate outright and says why.
- **Same-source distinct identifier** — two records from the same source namespace carrying two different stable ids. Analyzed honestly, this is *weaker* than it looks: the motivating directory case is one person with two profile pages, so two ids from one source frequently means one person. It is separation evidence only when the source guarantees one row per real person, which is a property of the source, not of folk — so it is declared per namespace in config (`unique_per_person`), defaults to unknown, and only when declared true does it suppress. Undeclared, it is shown to the human as context and nothing more.

`src` provenance is otherwise presented, not computed on: the review item shows both sides' `src` pointers so the human can open both source rows. That is the cheapest large improvement available and it costs no new machinery.

## Decision 4 — external stable identifiers are the anchor for re-scrape, and name matching should not be involved at all

"Is this scrape row the same person as last time?" and "is this scrape row a duplicate of somebody already in folk?" are different questions, and conflating them is why re-imports are scary. The first question has an exact answer available whenever the source has a stable per-record identifier (a profile URL, a directory id): **record the identifier at mint time, and every later run resolves by dictionary lookup, never by name.** Names change — people marry, get credentialed, get retitled, get re-romanized — and identifiers do not; resolving re-scrapes by name is solving a hard problem when an easy one is sitting next to it.

Mechanically: the identifier lives on the person file's `## Identifiers` section (Decision 1), one line per `namespace: id`, and many ids may map to one person (the two-department case is *expected* and is represented by two lines on one file). `identity.py` builds `(namespace, id) → slug` at lookup time. Two hard conflicts, neither of which the machine resolves:

- **One id, two person files** — a real contradiction (a bad merge, or a recycled id at the source). Reported at rebuild and surfaced in review; no guess, in the same spirit as supersession's exact-anchor tie leaving the slot untouched.
- **Identifier match disagrees with a strong name match** — the identifier wins for resolution, and the disagreement is surfaced as a review item rather than swallowed.

**The seam with `bulk-import.md`.** This doc owns: the `## Identifiers` convention and its parser; the `(namespace, id) → slug` map; resolution precedence and the conflict rules; the config shape for namespaces including `unique_per_person`. The bulk-import spec owns: which field of a given source is its stable id and what its namespace string is; what a re-scrape is permitted to change on an existing person; and batching, throttling, and dry-run mechanics. Whether an importer may create person files at all is no longer open — **confirmed by the maintainer (2026-08-30): yes**, a mechanical importer may mint person files directly on first encounter, which is necessary for real batch-import work rather than a nice-to-have (see Open Questions below). What a *re-scrape* of an already-known person is permitted to change on their existing file is a narrower, still-open question this doc continues to assume conservatively: *nothing directly* — a re-scrape appends `kind: observation` events under a mechanical actor and lets the human accept anything that belongs in the file, which keeps invariant 1 intact. The contract between them is one function and one file convention: given a source record, `identity.resolve(...)` returns exactly one of *this existing person*, *genuinely new*, or *ambiguous, here are the ordered candidates and why* — and an importer must never collapse the third into the first (`journal-schema.md`'s never-auto-merge rule, unchanged).

**Practical note the importer will hit immediately:** `folk lookup` currently rescans every person file in every collection per invocation, so an importer shelling out per row is quadratic in corpus size. v1 should expose a batch entry point (names in on stdin, one JSON result per line out) so the corpus is scanned once per run. This is small and it is the difference between a usable and an unusable import.

## Decision 5 — no LLM in `folk lookup`, ever; an offline proposal pass is the only legal home for machine judgment

Worth taking seriously, because name variance is genuinely a world-knowledge problem: an LLM knows that a diminutive maps to a formal given name, that a romanization variant is the same artist, that a maiden name and a married name can be one person. Nothing in the stdlib knows any of that. And folk already has a shaped home for machine judgment — `kind: promotion`, `evidence: interpreted`, queued in `folk review`, never auto-applied.

Against, decisively for the synchronous path:

- **Invariant 4 and reproducibility.** Aliases are consumed at rebuild time, and rebuild must be byte-identical on a re-run. LLM output may reach the alias table only through a human decision recorded in a person file — never directly.
- **`folk lookup` is called in a loop over thousands of rows.** An LLM call per row is slow, expensive, and non-reproducible, which also breaks the adapter's own idempotency story: the same input must produce the same answer on a re-run or a re-scrape is not a re-scrape.
- **Invariant 5 pressure.** Asked "are these the same person," a model volunteers a likelihood. Keeping that number is how `conf` gets reinvented; the prompt must ask for *reasons* and a same / different / unsure verdict, with "unsure" a first-class answer.
- **Poisoning surface.** A scraped bio containing "also known as …" is attacker-controlled text that could induce a merge. `review-queue.md`'s containment argument applies unchanged: the human decision is the boundary, so machine identity claims must arrive as queue items, never as writes.

So: the mechanical path stays purely deterministic, and the sanctioned future shape for LLM involvement is a **separate, opt-in, batch command** that reads only the already-generated ambiguous candidate sets and writes `kind: promotion`, `evidence: interpreted`, `level: bedrock` events proposing an aka line, with the note carrying the reasoning in words. That fits the existing machinery almost exactly — bedrock accept already previews a person-file edit and applies it as a typist — and needs only that `review._bedrock_target_section` learn to route the aka predicate to the `## Also known as` section. It is **deferred out of v1** deliberately: it should be designed after there is a real corpus of hard cases to evaluate it against, not before.

## Decision 6 — ambiguity is preserved, never resolved by the machine

Directly inherited from supersession's exact-tie rule. If two candidates fire the same matchers, folk shows both, in a stable order, and asks. If an identifier conflicts with itself across two files, folk reports and refuses. If a `## Also known as` line normalizes to a slug that already belongs to a different person file, that is a hard conflict reported at rebuild — never silently applied, because applying it would fold two people together in the index. Rebuild's stats line gains an identity-conflict count for the same reason it reports supersession counts: a surprising jump should be visible.

## Decision 7 — both answers must be durable; today's reject path is wrong for entity items

An identity question a human has already answered must never be asked again. Accept is already durable under Decision 1 (an aka line, or an `aliases` entry for file-less types). **Decline is not durable today at all**, and the current path actively causes harm (defect 2 above): the review event's `ref` resolves the whole promotion event, so "not a duplicate" drops the promotion's triples from the index.

Proposal: for entity items specifically, a decline writes a **`distinct` pair list** into the `identity` config block — the negative counterpart of `aliases`, curated data in exactly the same style — and writes **no** review event, because the only review event available would over-resolve. This mirrors the existing, deliberate asymmetry the review module already documents for vocab proposals ("accepting is what actually silences a predicate, by updating `vocab.json`"), and it is the same hole `decay-and-supersession.md` flagged in its Deferred section: a proposal derived from a *pattern* rather than from a single event has no clean event id for a review event to reference. Here the proposal is pattern-derived (it is about a pair of slugs, not about the truth of one event), so the config is the right place to record it.

This does mean departing from `review-queue.md`'s "Reject (any type) → review event only," which is why it is listed in `## Open questions` rather than assumed.

## What changes in the review flow

Concrete, function by function — the entity item type stays; no new queue item type is added (following `decay-and-supersession.md` Decision 4's precedent of reusing `proposal_kind` inside an existing type).

- **`folk/identity.py` (new)** — the single home for name normalization, the matcher registry, `candidates()`, the aka/identifier map builders, and `resolve()`. Also becomes the *only* normalization authority: `graph.slugify`, the inline `re.sub` in `journal._person_triples` and `journal._locus_triples`, and `person._find_person_file`'s ad-hoc lowering all call into it, so "the slug for this name" is one definition.
- **`journal._near_duplicate`** — deleted, or reduced to a thin shim over `identity.candidates` for one release. Its 0.6 default goes with it.
- **`journal.lint_events_detailed`** — calls `identity.candidates`; runs the check on the **`s` field as well as `o`** (defect 1); suppresses a proposal whose pair is already resolved by an alias, an aka, or a `distinct` entry (today it re-proposes an already-resolved pair forever, because accepted aliases rewrite the index's slugs, so the alias slug is never in `known_object_slugs` again and the proposal refires on every run); emits `{"kind": "entity_alias", "slug", "candidates": [{"slug", "reasons"}, ...]}` instead of a single `dup_of`.
- **`review.pending_items`** — unchanged in shape, but the entity branch carries `candidates` through instead of `dup_of`, and gains an `identifier_conflict` `proposal_kind` for Decision 4's conflicts.
- **`review.describe_item`** — the entity branch grows from its current single line (`'{slug}' looks like a near-duplicate of existing '{dup_of}'`) into a block: the proposed slug, then each candidate with its reason list, its display name, its collection, and its corroboration (shared/conflicting `## Dates`, shared tags and associations, both sides' `src` pointers). Needs a small read-only helper that pulls a candidate's person-file context (`person.show_person` already returns everything required).
- **`review.accept_entity`** — currently `vocab["aliases"][slug] = dup_of`. Gains an explicit chosen candidate (there is no longer exactly one) and a branch: if the canonical entity has a person file, write the aka line to that file through the existing preview/confirm/apply path (`preview_bedrock_edit` / `apply_bedrock_edit`, with `_bedrock_target_section` learning the aka section) so the human sees a diff before their curated file changes; only file-less entity types fall through to `vocab["aliases"]`.
- **`review.decline_entity` (new)** — writes the `distinct` pair per Decision 7. Deliberately not named `reject`, because it is not the existing reject.
- **`cli._run_interactive_review`** — the entity item's prompt changes from `[a]ccept / [r]eject / [s]kip / [q]uit` to a numbered choice over candidates plus a "none of these" decline, since accept now needs to know *which*. This is the only CLI change of substance.
- **`graph.find_person`** — returns `{"query_slug", "match", "candidates": [...]}`, with `near_matches` kept as an alias of `candidates` for one release so existing adapters do not break. `match` keeps its current, load-bearing meaning: set only when it is safe to reuse silently — now also set on an identifier or aka hit, which is the whole point. `journal-schema.md`'s "Source adapters" bullet describing this contract needs a one-line update when it lands.

## Scope for v1

Buildable with no new dependency, no schema change, and no index record change:

1. `folk/identity.py`: normalization (NFKD folding, apostrophe handling, config `generic_tokens` stoplist), the matcher registry with `exact_slug` / `exact_display_name` / `identifier` / `aka` / `normalized_name` / `initials_expansion` enabled and `surname_and_given_initial` / `fuzzy_string` present but off, ordered candidate output with reason strings, and `resolve()`.
2. The `identity` block in `vocab.json`: `generic_tokens`, enabled matchers and their precedence, `distinct` pairs, `id_namespaces` (with `unique_per_person`). Seeded by hand with the maintainer, the same way `stability`/`functional` were.
3. Person-file conventions and parsers: `## Also known as`, `## Identifiers` — `person._parse_dates` is the template.
4. `find_person` rewritten onto `identity.resolve`, plus `folk lookup --batch` reading names on stdin and emitting one JSON result per line.
5. Lint fixes: check `s` as well as `o`; suppress already-resolved pairs; emit candidate lists.
6. Review: richer entity display, candidate choice on accept, aka written to the person file behind a confirmed diff, `distinct` written on decline (pending the open question below).
7. Rebuild: aka/identifier maps participate in alias resolution deterministically, before supersession, so slots key off canonical slugs exactly as they do today; identity conflicts counted in the stats line; byte-identical-on-rerun preserved (nothing here reads a clock).
8. Tests, as a fixture table of name pairs with a documented expected outcome each: credential suffix, `Last, First`, middle initial, diacritic and apostrophe variants, mononym, the `-jr` false positive, the generic-token false positive (`dr`), a re-scrape resolving purely by identifier, and one identifier conflict.

## Deferred

- **The generalized cross-domain problem.** Music metadata is *not* the same problem wearing a hat: `work:` and `topic:` entities have no file, so Decision 1's anchor carrier does not exist for them, and the question is frequently about releases and credits rather than about a name at all. Nothing here should be claimed to solve it. Whether the anchor generalizes as a file-less "entity record," or whether those domains need their own spec, is genuinely open and should be answered after v1 has run against real directory data.
- **The LLM identity-proposal pass** (Decision 5) — sketched, not built. Design it against a real corpus of hard cases.
- **Phonetic matching** (Soundex/Metaphone/NYSIIS). Would need `jellyfish` or similar — **a new dependency, flagged here as a separately-approvable option, not assumed**, since invariant 8 requires the maintainer's sign-off. A hand-rolled Soundex is ~20 lines of stdlib, but it is English-biased, which makes it actively counterproductive for the romanization cases, so the honest recommendation is: do neither in v1, and revisit once real collisions show whether phonetics would have helped.
- **Transitive/cluster merges** (A~B and B~C implying A~C). Requires a merge policy and a cycle story; out of scope while every decision is pairwise and human.
- **A real `folk merge` for two person files.** Deliberately absent; the human merges files.
- **Caching the identity maps.** Full-corpus scans are fine at current scale and `--batch` covers the import case; a cache must never become a second authority, so it needs its own justification.
- **Household and family disambiguation** (shared surname, shared address, same-name generations) — the `-jr` case is handled only by a human decline today.
- **Source id recycling detection** and any notion of an identifier's validity window.

## Open questions

1. ~~May a mechanical importer create person files at all?~~ **Resolved by the maintainer (2026-08-30): yes.** A mechanical importer may mint person files directly — confirmed as necessary for any real batch-import run, not a fallback where thousands of newly-minted people would otherwise have to queue through `folk review` one at a time. This was the question that most changed the shape of everything else, and it now settles Decision 4's seam on its harder half: a bulk import is reviewable as a git diff and identity anchors (`## Identifiers`) exist from the first run. Still open, and narrower: whether a *re-scrape* of an already-known person may also edit fields on their existing file directly, or must still go through observation events plus human promotion — Decision 4 continues to assume the conservative "nothing directly on re-scrape" answer for that case until it, too, is asked.
2. **May an entity decline skip the review event** (Decision 7), given `review-queue.md` says reject writes a review event for every type? The current behavior is a genuine defect — declining a duplicate proposal deletes a good fact — so something has to change; whether the fix is "no review event for entity declines" or a narrower change to what a review event on an entity item resolves is the maintainer's call.
3. **`## Also known as` vs. `## Identifiers` as two sections or one.** Two is cleaner to parse and to read; one `## Identity` section with typed lines is fewer conventions to remember. Low stakes, easy to change later, worth deciding before files are written at scale.

## Exit criteria

Deliberately modest — this is a first step against a problem the maintainer has already found hard, not a claim to have closed it.

- The fixture table from scope item 8 produces the documented outcome for every pair: an exact `match`, an ordered candidate list with named reasons, or no match — and no numeric value appears in any of that output.
- Running `folk index --rebuild` twice against a fixture containing aka lines and identifiers is byte-identical, and deleting the index and rebuilding reproduces every alias — the anchors live in files, not in the cache.
- Re-running the same fixture import a second time resolves every row by identifier, mints zero new slugs, and adds zero items to the review queue.
- Accepting an aka in `folk review` appends to the person file behind a confirmed diff, and the *next* `folk lookup` of the alternate name returns an exact `match` — the same question is never asked twice.
- Declining a near-duplicate pair stops that pair being proposed on subsequent runs **and** leaves the promotion's triples in the index (the current defect, regression-tested).
- With `dr` in `generic_tokens`, two people who share a title and a given name but not a surname produce no candidate; with a middle initial or a credential suffix, they do.
- `folk lookup --batch` over N names scans the corpus once.
- Nothing in code enumerates a matcher policy, a generic token, a source namespace, or a collection name; every one of those is config.

## Revision log

- **2026-08-30** — maintainer confirmed Open Question 1: a mechanical importer may mint person files directly. Decision 4's seam and Open Questions updated in place; the narrower re-scrape-edits-an-existing-file question remains open and conservative.

*(Nothing yet — this doc is written expecting to be corrected. Append dated entries here as implementation contradicts the decisions above, and edit the decisions in place rather than leaving stale text standing.)*
