# Immich as a source — people, photos, and a derived narrative

**Status:** proposed and implemented 2026-11-25, not yet confirmed by the maintainer. Every decision below is a default chosen while the maintainer was unavailable; the ones that need sign-off are collected in `## Open questions for the maintainer`, and the code takes the conservative path until they are answered.
**Context:** `docs/design/bulk-import.md` (the batch shape, skip-and-report, rebuild-once, and the lessons section this spec follows); `docs/design/journal-schema.md` ("Source adapters": actor, `src`, repeated observations, the `folk lookup` contract); `docs/design/collection-curation.md` (`COLLECTION.json` and `create_person_file_as_agent`); `docs/design/identity-resolution.md` (still a proposal; `graph.find_person` remains the lookup, and this spec does not depend on the proposed `identity.py`); `docs/design/folk-render.md` (Bedrock-only render, and why the narrative is a separate renderer); `docs/design/scope-boundary.md` (photos as media references, not folk content); `folk/sources/directory_scrape.py` (the parse/fetch shape reused here); `folk/bulk.py` (`import_batch`, minting). The `immich` operator skill was consulted for the v3 API facts and key-handling rules.

## Why

Immich already holds two things folk wants and cannot get anywhere else: named people (face clusters a human has labeled in Immich), and human-written descriptions of specific moments ("the lake trip", "Grandma's last visit"). Together with dates and places, they describe a person's life in photos. The goal is that folk can mint people from named Immich clusters and record, mechanically, where those people appear, with whom, when, and what the photo was about. From that the narrative is a derived, deterministic view of the journal, never a second authority.

Immich's labels are curated by a human, but folk reads them mechanically. That is the central trust question, and Decision 1 answers it.

## Decision 1 — mechanical observations, `observed` tier, never Bedrock sections

A person label in Immich is a human's statement in another system. Folk's `observed` tier is for deterministic, versioned tools with no LLM in the path, whose output is verbatim from their source. An Immich name read through the API and written as an event is exactly that. It is not a promotion, has no `evidence` field, and is not written into any Bedrock section of a person file. Events use the actor `import:immich:v1`, `kind: observation`, and the `src` pointer `immich:asset:<id>` on every event (journal-schema "Source adapters": `src` is required and is the drill-down path).

Consequence: an Immich description is evidence that a photo was described that way, not a claim that the description is true. The narrative quotes it as the source's words.

## Decision 2 — minting, and the collection's curation policy

The Immich collection is one collection, and its person files are minted by the adapter. Under `collection-curation.md`, that requires its root to hold `COLLECTION.json`. This spec does not ship that file in the repo (the collection-curation spec says no collection ships one). The operator places it in the collection directory:

```json
{"curation": "agent"}
```

Minting is performed by `bulk.import_batch`'s existing path and nothing else (`person.create_person_file_as_agent`). Its rules: one person file per **named** Immich person (unnamed face clusters are ignored, see Decision 3); a person already found by `folk lookup` as an **exact** match elsewhere is reused and never re-minted in this collection (identity is collection-agnostic, per `graph.find_person`'s own docstring); a person with a **near** match is held back, see Decision 6; and an existing file is never overwritten (`FileExistsError` falls through to "not minted").

Minting is limited to the people the events being written reference, as subject or object. A pair event's object can have no subject event of its own, so minting by subject alone would leave a dangling reference. This was found in the smoke run and fixed in `scripts/run_immich_import.py`'s `plan()`.

## Decision 3 — granularity: per-asset events only when the asset says something

A library of thousands of photos, each with one face, would flood the journal with single-person rows that say nothing about relationships or events. The rule: an asset yields events only when it has at least one named person **and** (a human description, **or** two or more named people, **or** a place). A lone face with no description, no companion and no place is not worth a journal line. (The place clause was added after a live survey found every sampled description empty: without it the narrative would have had almost nothing to say.) Unnamed clusters are dropped before counting, so they never make an asset look like a group photo. Names that slugify to nothing are dropped for the same reason.

Within an emitted asset, co-appearance is one event per **unordered pair**, not one per direction. The pair is stored with the lower slug as subject, and the renderer treats it as symmetric. Per-person events are emitted for place and description, one per named person.

Example, with fabricated names and an asset that has a description, two named people, a place, and a date:

```json
{"v":1,"ts":"2026-11-25T03:00:00","actor":"import:immich:v1","kind":"observation","s":"person:test-person-one","p":"pictured_with","o":"person:test-person-two","when":"2024-06-01","note":"a shared picnic by the lake","src":"immich:asset:<id>"}
```

## Decision 4 — predicates and types: a small set, registered per deployment

Three predicates, two new types, no edits to shipped config (see Decision 8 for where they go):

| Predicate | Subject → object | Meaning | Stability |
|---|---|---|---|
| `pictured_with` | person → person | Both appear in the same asset; `note` = the asset's description when there is one | unclassified (never decays) |
| `pictured_at` | person → locus | The asset was taken at this place (city, falling back to country) | unclassified |
| `described_in` | person → photo | A human wrote this description of a photo the person appears in; `note` = the description | unclassified |

`photo:<slug-of-asset-id>` is a new type whose object is an Immich asset (the stable object for drill-down); `locus:` is the existing Locus type (`docs/design/loci.md`), so places get a file if a human ever writes one and otherwise stay as slugs. Dates ride on `when` (the local date from Immich). The `src` is `immich:asset:<id>`.

**Why unclassified, not `situational`:** `decay-and-supersession.md` makes "situational" predicates age. A photo of two people together does not go stale. Leaving them unclassified means they never decay, which is the safe default there.

**Why these three:** each answers one question a narrative needs (who was with whom, where, and what the photo was about), and none duplicates another. Co-appearance without a description is still useful, so `pictured_with` is not gated on a description.

## Decision 5 — idempotency: dedupe on the event identity, not the run

`id` hashes `ts`, which changes every run, so it is not a re-import key (journal-schema). Dedupe is by `(src, s, p, o, note)` against every `import:immich:v1` event already in the collection's journal root, plus duplicates within the batch (a page boundary can return an asset twice). Keyed on `src` alone is not enough, because one asset yields several events sharing a `src`.

Including `note` makes an edited Immich description append a later observation instead of being silently dropped. The narrative's rule is that the last event by `ts` wins for scalar fields, so the correction takes effect. The original stays in the journal (append-only, invariant 3). This is the only case where a re-run writes anything, and it is intentional.

## Decision 6 — identity: exact reuse, near match held and logged, never auto-merged

For each named person the script calls `graph.find_person(name)`, the same discipline as `bulk-import.md` Decision 4. An exact match is reused: its events are written under the existing slug and it is not minted. A near match is never auto-reused and never auto-created: every event that references the person (subject or object) is held back, and one record per person is appended to `near-matches.jsonl` in the collection directory. This is the lesson `bulk-import.md` learned the hard way: a skipped near match must leave a durable trace, or it is lost when the terminal scrolls. The record holds the Immich name, slug, candidate matches, and a held-event count. It holds no key and no description text.

Two different Immich people whose names fold to one slug are indistinguishable to folk. The script reports such spellings (`name_variants`) and does not resolve them. That is a human's call.

## Decision 7 — the narrative: a deterministic renderer over the journal

The narrative is derived markdown, written to an explicitly chosen `--out`, and never into a person file. Two reasons it is not an extension of `folk render`. First, `folk-render.md` Decision 3 makes render Bedrock-only by design, and this is Observed, not Bedrock. Second, the narrative is a timeline and a roll-up over events, which render's person-file templating does not model.

Module: `folk/immich_narrative.py` (`load_events`, `assemble`, `render`, `write`). Script: `scripts/immich_narrative.py`. It reads only the registered journal roots for its collection (`journal.iter_segments`), filtered to `import:immich:v1`, never the index (invariant 1), and it has no clock and no LLM, so two runs are byte-identical (invariant 4). Output:

- `people/<slug>.md`, one per person: a chronological timeline (date, description or "(no description)", others present, place, `src`), with undated photos last.
- `summary.md`: a roll-up by year and by place, with the people seen.

`--out` must not sit inside the collection directory (the script refuses), and stale `people/*.md` files are removed so the directory always equals a fresh render.

An optional later LLM narrative step would be a *promotion proposal* (`kind: promotion`, `evidence: interpreted`, under a non-mechanical actor), queued in `folk review`, never written to person files, and not built here.

## Decision 8 — vocab registration: a per-deployment snippet, not a shipped file

`vocab.json` lives at `~/.config/folk/vocab.json` (`config.VOCAB_FILE`), per deployment. Nothing in the repo ships a live vocab, and `eval/vocab.json` is the frozen eval fixture and must not change (promotion-eval.md Decision 4). So the registration is a documented snippet an operator merges into their live vocab before the first real run:

```json
{
  "types": ["photo", "locus"],
  "predicates": {
    "pictured_with": "two named people appear in the same photo; note is the photo's description when there is one",
    "pictured_at": "a person appears in a photo taken at this place (city, or country as fallback)",
    "described_in": "a human-written description of a photo the person appears in; note is the description"
  }
}
```

Merge, do not replace: keep the existing `types`, `predicates`, `aliases`, and other keys. Until merged, the predicates and types still append (lint proposes them, it does not reject them) and queue in `folk review`.

## Decision 9 — configuration and secrets

The glue script takes configuration from flags or environment, and nothing is hardcoded: `--base-url` or `FOLK_IMMICH_BASE_URL`, `--api-key-file` or `FOLK_IMMICH_KEY_FILE`, `--api-key-var` (default `IMMICH_API_KEY`), `--page-size`, `--since`, `--collection-dir` (required). The API key is read from a `VAR=value` env file or the environment, sent only in the `x-api-key` header, and never printed, logged, or put in an exception message (the tests assert this for the HTTP error path). Per the immich skill, the key needs `asset.read` only: the search endpoint returns people and exif with it. `/api/people` is not called, so no extra permission is required. Create the key with `immich_key.py`, not by hand.

Immich's search is restricted to `IMAGE` assets. Videos are out of scope for v1.

## Decision 10 — `## Media`: skipped

`folk media <name> --immich` is named in `skills/folk/SKILL.md` but has no implementation in `folk/`, so there is no established `## Media` reference format for Immich. A cover reference could be written as `- immich:asset:<id> — cover`, which the media parser would accept. But it would write into a Bedrock section of a file this spec mints, and an opaque asset id is not a useful reference for a human reader. The spec therefore mints no `## Media` lines. This is the cleaner of the two options the brief allowed, and it is revisited when `folk media --immich` is actually designed.

## What was built

- `folk/sources/immich.py`: `fetch` (urllib POST to `/api/search/metadata`, paged on `nextPage`, with an injectable `request_fn` and `opener`), `load_api_key`, `parse`, `named_people`, `person_names`, `name_variants`, `dedupe_key`, `existing_keys`, `dedupe`, `split_by_identity`.
- `folk/immich_narrative.py`: `load_events`, `assemble`, `render`, `write`.
- `scripts/run_immich_import.py`: dry-run by default; `--confirm` writes through `bulk.import_batch`, logs near matches, and prints a summary with a ground-truth reminder. It never rebuilds the index.
- `scripts/immich_narrative.py`: renders the narrative to an explicit `--out`.
- `tests/test_immich_source.py`: 32 tests on fabricated fixtures only (placeholder asset ids, invented names, fictional places, a placeholder key). They cover parse, pagination, the key never appearing in errors, idempotent re-run, edit-as-later-event, near-match hold and log, lint-clean names with punctuation and diacritics, and narrative byte-identity.
- The `docs/design/immich-source.md` row in `skills/folk/SKILL.md`'s design-doc table.

## What was not built, on purpose

- No `folk` subcommand (glue scripts, as for `bulk-import`).
- No change to `folk/sources/__init__.py`'s `ADAPTERS` (not a transcript source).
- No `## Media` references (Decision 10).
- No `COLLECTION.json` shipped in the repo (collection-curation).
- No LLM step. The narrative is deterministic, and any interpreted layer would be a future promotion proposal.
- No resolution of near matches. A human decides, and the held events are then re-run through the script (a re-run after the person is resolved will write them, since dedupe is on the event key).
- No `identity.py`. This spec uses `graph.find_person` as it is today.

## Open questions for the maintainer

1. **Curation for the Immich collection.** The spec assumes this collection is `curation: "agent"`, so minting works. If it should stay human-curated, the script still runs, and minting just refuses (`CurationRefused`, which the code already treats as "not minted"). Which is intended?
2. **Place fallback.** Decision 4 uses city, falling back to country, in one `locus:` namespace. That mixes granularity in the place roll-up. Is a country-level `locus:` acceptable, or should countries be dropped?
3. **Pair direction.** Co-appearance is stored once per unordered pair (lower slug as subject). If a later consumer needs per-direction events, the change is small, but it would change the journal shape for already-written pairs. Is one-per-pair the right long-term form?
4. **Description corrections.** A changed description appends a later event, and the narrative takes the last one. Is "append, never rewrite" the right answer for a corrected description, or should a changed description retire the old one through a `review` event?
5. **Same-name people.** Two different Immich people with one name fold into one slug and are reported, not resolved. Is that acceptable until `identity-resolution.md` lands, or should the script refuse to mint a name with variants?
6. **Held events.** There is no tool yet to release held events after a human decides a near match. Re-running the script does that, but only once `folk lookup` stops returning the near match. Is that the intended flow, or should there be an explicit decline?
7. **Live API shape (partly resolved).** A read-only survey of the live v3.4.2 server confirmed the field names below; the adapter was reconciled (hidden/locked/trashed/offline assets are filtered client-side; granularity widened so a named person with a place alone emits `pictured_at`, because the survey found every sampled `exifInfo.description` empty, so descriptions alone cannot drive the narrative yet). Still true: `/api/people` needs `person.read`, which the admin key lacks, so person data comes from search results' `people` arrays. A full ascending walk did not finish in 900 s, so use `--since` for large runs. Original note: this was built against the v3 facts in the `immich` skill and the response field names as documented there (`people[].name`, `exifInfo.description/city/country`, `localDateTime`, `assets.nextPage`). The brief's survey file (`immich-survey.md`) was not present when this was written, so these names are unverified against a live v3.4.2 response. A dry run against the real server should be the first step before `--confirm`.
8. **Trust of descriptions.** Descriptions are free text, and an attacker-controlled description could contain names. Only a folk journal event is written, and no Bedrock content, so the blast radius is the journal. Is that containment sufficient?

## Exit criteria

- A dry run against the real Immich server reports a plausible plan with no writes, and the counts match a manual check of a few assets.
- A `--confirm` run writes only `import:immich:v1` observations, mints only named people in an agent-curated collection, and writes `near-matches.jsonl` for every held person.
- Re-running the same `--confirm` appends nothing (dedupe).
- `folk index --rebuild`, run once afterwards, indexes the events and is byte-identical on a second run.
- `scripts/immich_narrative.py` run twice on the same journal writes byte-identical output, and refuses an `--out` inside the collection.
- `python3 -m unittest discover tests` is green, and `scripts/check_release_hygiene.py` is clean.
