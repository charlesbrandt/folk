# Bulk/mechanical import — running a batch of source-adapter observations

**Status:** proposed and implemented this session (2026-08-30), not yet confirmed by the maintainer. Nothing here changes `docs/design/journal-schema.md`'s normative shape — that spec's "Source adapters (non-conversation writers)" section already specifies the event shape, the actor convention, and the identity-check discipline this doc just operationalizes into a runnable batch. Companion to `docs/design/locus-type.md` for Decision 3 below.
**Context:** `docs/design/journal-schema.md`'s "Source adapters" section (normative, quoted throughout below); `docs/design/locus-type.md` (the org-as-Locus modeling this doc recommends); `folk/journal.py`'s `append_event` (per-event lint-then-append, invariant 6) and `_near_duplicate` (the identity heuristic this doc calls out as a known-weak point); `folk/graph.py`'s `find_person` (the `folk lookup` backend); `folk/promotion.py` (the LLM-shaped pipeline this doc deliberately does *not* reuse, and whose all-or-nothing quarantine behavior this doc explicitly diverges from); `deploy/README.md` (the existing `folk promote` → sync → `folk index --rebuild` two-step pattern this doc follows).

## Why

The maintainer's real use case — tracking people, teams, and shared resources across a large organization, seeded from a bulk source like a scraped public directory rather than one conversation at a time — is a fundamentally different shape from every existing folk writer. `folk/sources/`'s `discover/mtime/load` contract and `folk/promotion.py`'s extract→LLM-promote→lint→append-or-quarantine pipeline exist specifically to turn a *conversation transcript* into *proposed* facts a human reviews. A directory scrape has no conversation, no LLM step, and no proposal to review: a person's title and department, read off a public profile page, are mechanically observed facts, not an interpretation of anything. `journal-schema.md`'s "Source adapters" section already says as much — this is the doc it describes, written down concretely with the open questions resolved rather than left as an exercise for whoever builds the first one.

## Decision 1 — skip-and-report per record, not all-or-nothing

`folk/promotion.py` quarantines an entire session's batch on any lint failure, and that is the right call *there*: promotion output is LLM-authored, the events in one session's batch share the same conversation and the same model call, and a lint failure on one event is a real signal that the rest of that batch might be suspect too (a hallucinated slug, a garbled quote-verification match, whatever produced the bad event could plausibly have touched its neighbors).

A bulk mechanical import has the opposite risk profile. Each row is an independent scraped record — a different person's profile page, a different day's export line — with no shared authorship and no shared reasoning chain. A scrape of a few hundred directory entries will, empirically, always have a handful of malformed pages: a missing name field, a department string that turns out empty, a stray HTML fragment nobody stripped. None of that says anything about the other 495 well-formed records. Treating one bad row as grounds to discard an entire run would make the importer *less* reliable than just re-running with more entries excluded, and would put a human in the position of debugging one bad row before getting any of the good ones in.

**Decision: a bulk import appends what lints clean and skips-and-reports what doesn't, per record.** This is not a lint-strictness relaxation — `journal.append_event`'s lint is unchanged and still runs, still hard-fails on a genuinely malformed event, and invariant 6 ("lint before append") is honored on every single event. What changes is the *batch* semantics wrapped around many calls to it: one bad record does not block its siblings. `folk/bulk.py`'s `import_batch` (below) is exactly this wrapper, and it is deliberately a thin one — it does not add a second, looser lint of its own.

## Decision 2 — `folk index --rebuild` runs once, after the batch, not per record

`folk/promotion.py` does **not** call `rebuild_index()` itself — confirmed by reading it; the deploy unit files (`deploy/folk-promote.service`, `deploy/README.md` step 5) run `folk promote` and `folk index --rebuild` as two separate steps, with a sync in between for the multi-host case. A bulk import follows the identical two-step pattern: append every record in the batch (via `folk/bulk.py` or the four-line loop it wraps), then run `folk index --rebuild` once, externally, when the batch is done.

Rebuilding per record would mean re-reading and re-deriving the entire index — every collection's person files, every journal segment, every Locus — once per scraped row, which is `O(n)` full rebuilds for one batch instead of one. There is no correctness reason to rebuild more often than that: invariant 1 already establishes the index as "a derived cache, deletable at any time," and nothing reads through the index mid-batch (an importer that needs `folk lookup` to check for an existing person, see Decision 3, reads through `find_person`'s live file walk over person files, not through the index at all — so a stale index between records is not a hazard here, unlike a review-queue flow that might read index state mid-session). One rebuild after the batch is both cheaper and exactly as correct as one after every record.

## Decision 3 — orgs, teams, and resources are Loci, not bare `org:` strings

`folk-schema.md`'s own worked example already writes `works_at` → `org:studio-b`: a bare `type:slug` association target works today, costs nothing, and is the right call for a one-off edge to something that will never need its own file. But a bulk import that is specifically building out organizational structure — departments, labs, research centers, shared resources — is minting the same handful of organizational entities over and over, once per person who belongs to them. Modeling those as bare `org:` strings means the organization itself is never a first-class file: it cannot carry a description, cannot be `folk show`n, cannot accumulate curated associations of its own (who runs it, what it's for), and cannot be typed.

`docs/design/loci.md` already generalized "a markdown file with a name, a description, and curated associations" past narrative places; `docs/design/locus-type.md` adds the one field needed to say *what kind* of Locus an organizational unit is. So: **a bulk importer creating organizational structure should mint `locus:<slug>` entities carrying `## Locus Type`** — `locus:iusm-neurology` typed `department`, `locus:nsf-award-1234567` typed `grant`, `locus:shared-microscope-core` typed `resource` — and point `works_at`/similar edges at those, rather than at bare `org:`/`resource:` strings. This gets the organization a real file, a real `folk show locus:<slug>`, and a place to hang its own curated cast (`## Associations`) the same way any Locus does. A quick one-off edge to something genuinely disposable can still use a bare `type:slug` target; that path stays available and is not being deprecated, it's just the wrong default for a bulk importer that is deliberately building out an org chart.

Minting the Locus file itself is a human/file-authoring step in this doc's v1 scope — organizational Loci (departments, labs, grants) stay hand-authored, the same discipline as any other Locus. This is now a narrower rule than the one in force for people: the maintainer has since confirmed (`docs/design/identity-resolution.md`, Open Questions, resolved 2026-08-30) that a mechanical importer *may* mint `person:` files directly — necessary for real batch-import work, since thousands of scraped people cannot each wait on a human to author a file by hand. That confirmation was not extended to organizational Loci here; nothing in this session asked the equivalent question for `locus:` entities, so the safer default (a handful of departments, hand-authored once) stays the v1 answer until it is. A bulk importer's realistic v1 shape is therefore: mint (or confirm the existence of) each organizational Locus file once, by hand or a one-time setup script, then mint each new person's file on first sight per the confirmed decision above — **landed 2026-09-01**: `folk/bulk.py`'s `import_batch()` now takes optional `collection_dir`/`person_names` arguments and mints a `person:<slug>` file, via `person.create_person_file_as_agent`, for any event's subject it hasn't already minted in that call, best-effort (see "Person-file minting" below) — and write `works_at`/`holds_title` observation events against `locus:<slug>` for every person the scrape finds there. See the worked example below.

## Decision 4 — identity resolution at scrape scale is a known-weak point, deferred to a dedicated spec

`journal-schema.md`'s "Source adapters" section already tells an adapter to check `folk lookup "<name>" --json` (backed by `folk/graph.py`'s `find_person`) before minting a new `person:<slug>`, and to never auto-merge a `near_matches` result. That heuristic — `folk/journal.py`'s `_near_duplicate`, a slug-token Jaccard-overlap check with a 0.6 threshold and nothing else (no fuzzy name matching, no email/handle cross-reference, no organizational-context tiebreak) — was designed for the conversational case, where a promotion LLM proposes a handful of entity slugs per session and a human reviews each one. Run per-record across a scrape of hundreds of directory entries, the same heuristic is doing much more disambiguation work with much less human attention per decision, and token overlap alone will both miss real duplicates (a name recorded two different ways) and flag false positives (two unrelated people whose slugs happen to share tokens) at a rate nobody has actually measured yet.

This doc does not attempt to fix that — it is a materially harder problem than running a batch of appends, and deserves its own design pass rather than a paragraph here. **A separate, deeper design doc on identity resolution is being written in parallel: `docs/design/identity-resolution.md`.** Until it lands, a bulk importer's honest posture is: run `folk lookup` before minting, treat an exact `match` as safe to reuse, treat every `near_matches` hit as a queued human decision rather than a silent merge or a silent skip (the review queue's existing entity-alias proposal shape, `journal.lint_events_detailed`'s `entity_alias` proposals, is the closest existing mechanism — a bulk importer can lean on it by simply letting its `person:<slug>` choices flow through the same lint-time near-duplicate check every other writer gets, rather than only checking once at mint time), and expect this guidance to be revisited once `identity-resolution.md` exists. `import_batch`'s minting (below) does not run this check itself — it mints whatever subject its caller hands it, once, on the assumption the caller already ran `folk lookup` upstream; that assumption is exactly this decision's honest posture, not a new one.

## Person-file minting (landed 2026-09-01)

`folk/bulk.py`'s `import_batch()` gained two optional keyword arguments, `collection_dir` and `person_names`, and one new key in every outcome dict, `"minted"`. The creation path is entirely `person.create_person_file_as_agent` (`docs/design/collection-curation.md`) — `import_batch` decides only *when* to call it, never loosens what it refuses:

- **Without `collection_dir`, nothing changes** — every existing caller (including the tests written before this landed) keeps working exactly as before; minting is opt-in per call, not a default.
- **With `collection_dir`**, for each event that actually appends (a lint-skipped event mints nothing), if its subject is a `person:<slug>` this call hasn't already minted, `import_batch` looks up a display name in `person_names` (a plain `{subject_ref: display_name}` dict the caller builds — `bulk.py` has no record shape of its own to pull a name from, since that's the caller's raw record, already gone by the time it built the event, so the function asks rather than reverse-engineering a name out of the slug) and, if found, calls `create_person_file_as_agent`.
- **Minting is best-effort, never a reason to skip or fail the record itself** — a subject missing from `person_names`, a collection that isn't `curation: "agent"` (`CurationRefused`), an invalid slug (`ValueError`), or a file that already exists (`FileExistsError` — a person seen earlier in the same batch, or one a human already wrote by hand) all fall through to `"minted": None`. The event was already appended before minting was attempted; none of these change that.
- A subject is attempted at most once per `import_batch` call (an in-memory set, not a disk check), so two events about the same new person (the worked example's `holds_title` + `works_at` pair) mint one file, not an `IOError`-swallowing double-attempt.

This closes the gap this doc's "Not built" section originally flagged. Still true and unchanged by this: Decision 3 (organizational Loci stay hand-authored — this mechanism only ever mints `person:` files, never `locus:`), and Decision 4 (identity resolution stays the caller's job, upstream of the events and `person_names` this function receives).

## Worked example

Three fabricated (not real) scraped records, the shape a hypothetical directory-export adapter might produce:

```python
raw_records = [
    {"name": "Priya Anand", "title": "Research Scientist", "department": "Neurology", "profile_url": "https://example.org/directory/p-anand"},
    {"name": "Marcus Webb", "title": "Lab Manager", "department": "Neurology", "profile_url": "https://example.org/directory/m-webb"},
    {"name": "R. Okafor", "title": "", "department": "Neurology", "profile_url": "https://example.org/directory/r-okafor"},  # malformed: no title
]
```

Before the batch runs, the department gets its own Locus file (minted once, by a human or a one-time setup script — not by the per-record import loop):

```markdown
# Neurology

## Locus Type

department

## Genius Loci

A clinical department; people, not narrative, but the same "curated file with associations" shape.
```

For each record, `folk lookup "<name>" --json` is checked first (Decision 4); assume all three are genuinely new. `folk/sources/directory_scrape.py`'s `parse()` then produces, for the first record:

```json
[
  {"v": 1, "ts": "2026-08-30T03:00:00", "actor": "import:directory-scrape:v1", "kind": "observation",
   "s": "person:priya-anand", "p": "holds_title", "o": "title:research-scientist",
   "note": "Research Scientist", "src": "directory-scrape:profile:https://example.org/directory/p-anand#title"},
  {"v": 1, "ts": "2026-08-30T03:00:00", "actor": "import:directory-scrape:v1", "kind": "observation",
   "s": "person:priya-anand", "p": "works_at", "o": "locus:neurology",
   "src": "directory-scrape:profile:https://example.org/directory/p-anand#department"}
]
```

(the second record, Marcus Webb, produces the analogous pair against `locus:neurology`.) The third record's empty `title` means `parse()` simply emits no `holds_title` event for it — an empty scraped field is not malformed, it is absent data, and `parse()` treats it that way rather than manufacturing a bad event only to have lint reject it. A genuinely malformed record (say, a missing `name`) would raise inside `parse()` before ever reaching `journal.append_event`, and the caller's loop is expected to catch that and record it as a skip alongside any lint-time skip — both are "this record didn't make it," reported the same way.

The caller (a script gluing `directory_scrape.fetch()` → `directory_scrape.parse()` → `folk/bulk.py`'s `import_batch()` together, none of which exists as a `folk` subcommand — this is glue code a deployment writes, the same way `deploy/`'s promotion unit files are glue around `folk promote`) then:

```python
from folk import bulk, journal

events = []
person_names = {}
for raw in raw_records:
    events.extend(directory_scrape.parse(raw, ts=run_ts))
    person_names[f"person:{directory_scrape._slug(raw['name'])}"] = raw["name"]

outcomes = bulk.import_batch(journal_root, "directory-scrape", events,
                              collection_dir=collection_dir, person_names=person_names)
for o in outcomes:
    if o["status"] == "skipped":
        print(f"skipped {o['src']}: {o['reason']}")
    elif o["minted"]:
        print(f"minted {o['minted']}")
```

and finally, once, after the whole batch: `folk index --rebuild`.

`works_at` and `holds_title` (and the `title:` type) are not in the shipped `vocab.json` — per `journal-schema.md`'s adapter registration commitment, a real deployment registers them (with a one-line `p_def`/type note) before the first real run, exactly as any other new predicate would; until registered, `lint_events_detailed` will soft-propose them (not hard-fail — new predicates/types are proposals, not errors) and they will queue in `folk review`.

## What was built, and what wasn't

**Built:** `folk/bulk.py`'s `import_batch()` — evaluated honestly against "would this be a premature abstraction," and kept because the skip-and-report contract (Decision 1) is exactly the kind of behavior that drifts if every caller reimplements the try/except loop by hand; one canonical implementation with its own tests is cheaper than N slightly-different copies. It is deliberately thin: no batching, no retries, no rebuild call (Decision 2 — that stays external and explicit), no identity-resolution logic (Decision 4 — out of scope here). **Landed 2026-09-01:** optional person-file minting (see "Person-file minting" above) — still no batching, retries, rebuild call, or identity-resolution logic; the addition is exactly the one gap the original pass left open, nothing more.

**Built, as a skeleton only:** `folk/sources/directory_scrape.py` — `parse()` is real and tested; `fetch()` is a documented stub, since actually reaching a real site needs an HTTP client and HTML/JSON extraction folk has no dependency sign-off to add (invariant 8), and no specific site or organization is named or hardcoded anywhere in it (this is a public repo; the maintainer's own use case is illustrative context for this doc, not something baked into shipped code).

**Not built, on purpose:**
- Any change to `folk/sources/__init__.py`'s `ADAPTERS` registry or its `discover/mtime/load` contract — that contract is for conversational transcript sources feeding `folk/promotion.py`, and a bulk import needs none of it (no LLM, no promotion, no quarantine).
- A `folk` subcommand for running a bulk import — the two building blocks (`bulk.import_batch`, an adapter's `fetch`/`parse`) are library functions a deployment's own glue script calls, the same way `deploy/`'s promotion units are glue around `folk promote` rather than folk owning the scheduling.
- Identity resolution beyond what `journal-schema.md` already specifies (Decision 4) — deferred to `docs/design/identity-resolution.md`; `import_batch`'s minting still does not call `folk lookup` itself, per that decision.
- Any enumeration of organization names, department names, or Locus Type values in code — `directory_scrape.py` takes all of that from the raw record and the caller, never hardcodes any of it (consistent with `docs/design/locus-type.md` Decision 2 and invariant 7).
- Locus-file minting by the importer — Decision 3 stands unchanged; `import_batch`'s new minting path only ever creates `person:` files, never `locus:`.

## Lessons from the first real deployment (iusm-directory, 2026-09-02)

The worked example above computes `person_names`' dict key via `directory_scrape._slug(raw['name'])` — calling the adapter's own slug helper directly, separately from whatever slug a caller's `folk lookup` step derived. In the real deployment this doc anticipated, that split turned out to be a live footgun, not just a style choice:

- **An adapter's own slug helper must be the same function `folk lookup`/`graph.find_person` uses, not a parallel reimplementation.** `directory_scrape.py`'s original `_slug()` only collapsed whitespace (`"-".join(text.lower().split())`), unlike `folk/graph.py`'s real `slugify()` (NFKD-fold, strip all non-alnum punctuation). A credentialed name like `"Namita Agrawal, MD"` slugified to `namita-agrawal,-md` — comma intact — which fails `journal.append_event`'s lint (`malformed slug ... want type:lower-hyphen`) on *every* event built from it. Run across a real batch (26 departments, 310 people), this was a 100% failure rate: every event lint-skipped, nothing appended, nothing minted — while the batch script still printed a normal-looking summary and exited 0. Fixed by making `directory_scrape._slug()` delegate to `folk.slug.slugify()` directly, which has the further benefit of guaranteeing it agrees with whatever slug a caller's own `graph.find_person()` call already computed for the same name — before the fix, nothing enforced that agreement, so even a name that happened to lint clean could in principle end up minted under a different slug than the one identity lookup checked. **Any adapter defining its own slug/text-normalization helper for subject or object refs should import and reuse `folk.slug.slugify()`, never hand-roll an equivalent.**
- **A batch importer's own "Done: N appended, M skipped" summary is not proof anything was written** — it's exactly as reliable as the logic that produced the counts, and in the failure above, that logic was internally consistent (every event really was accounted for) while the outcome was total silent failure. After any real `--confirm`-style run, verify against ground truth external to the run's own tally — `folk -C <collection> list | wc -l`, a `folk show` on a spot-checked record — not just the script's printed numbers.
- **A skipped near-match (Decision 4) leaves no trace anywhere in folk's own state** — not the review queue (`folk review` only surfaces events that actually appended with a coined predicate/type), not the journal (no event was ever built for it), nothing. The only record is whatever the caller happens to print to stdout, gone once the terminal scrolls past it. This doc's Decision 4 already treats a near-match as "a queued human decision, never a silent merge or skip" — worth being explicit that "queued" needs a caller-side durable log to actually mean anything past the end of that terminal session. iusm-directory's fix: `scripts/run_department_import.py` appends one JSON-Lines record per skipped near-match (department, the new record's name/title/profile URL/source id, and what it was matched against) to a collection-local `near-matches.jsonl` — a pattern worth reusing rather than re-inventing per adapter.

## Exit criteria

- `folk/bulk.py::import_batch` given a mix of good and lint-failing event dicts appends the good ones, skips the bad ones with a reason, and raises nothing for a lint failure (a non-lint exception, e.g. an unwritable root path, still propagates).
- `folk/bulk.py::import_batch` given `collection_dir` and `person_names` mints a person file for a new subject in an agent-curated collection, reports its path as `"minted"`, mints at most once per subject per call, and falls through to `"minted": None` (never a raised error, never a skipped/failed record) when the collection is human-curated, the file already exists, the slug is invalid, or no display name was supplied.
- `folk/sources/directory_scrape.py::parse` given a well-formed raw record produces well-formed `kind: observation` events with a correct mechanical `actor`, an adapter-namespaced `src`, and a `locus:` (not bare `org:`) target for the organizational edge; given a record with an empty optional field, omits the corresponding event rather than emitting a malformed one.
- Both are covered by tests using fabricated fixture data only — no real names, sites, or organizations anywhere in the test fixtures.
- `python3 -m unittest discover tests` is green.
