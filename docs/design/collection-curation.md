# Collection curation — who may *create* a person file

**Status:** implemented 2026-08-31 ; its first caller, `folk/bulk.py`'s `import_batch()`, landed later (commit c1b691a).
**Context:** `CLAUDE.md` invariant 5 (this doc is the "Mechanism" it points to); `skills/folk/SKILL.md`'s "Fiction Character Maps" section (the 2026-08-30 decision this doc formalizes: *"Whether a machine may mint a folk entity is the target collection's call,"* superseding the 2026-08-09 "no machine may create folk entities" rule); `docs/design/collection-registry-integrity.md` Decision 3 (reuses the same `COLLECTION.json` file for an unrelated purpose — a collection-existence check — and needs no new file format of its own); `folk/config.py`, `folk/person.py`, `tests/test_collection_curation.py`.

## Why

Person files are Bedrock (invariant 5): the human-curated tier, never silently overwritten by a machine. Until this decision, that meant no machine could create one either — folk's only way to get a new figure into a collection was a human writing the file by hand. That is the right default and stays the default everywhere, but it stopped being the only workable answer once bulk/mechanical import (`docs/design/bulk-import.md`) and fiction-extraction pipelines (the `characters` collection's actual use case) both wanted the same thing: seed a collection from hundreds of scraped or extracted records without a human hand-authoring each stub file first.

The fix is not a global switch — a `directory-scrape` job populating someone's `personal` collection with machine-authored files would be exactly the failure invariant 5 exists to prevent. The fix is per-collection: `characters` and a directory-scrape target are collections nobody's real identity depends on being human-gated, while `personal`/`other`/`musicians`/`authors` are exactly the collections where a wrong or premature machine-authored file about a real person is the harm invariant 5 was written for. The decision belongs to whoever owns the collection, stated once, on disk, next to the collection itself.

**This is a different axis from `appearance.md` Decision 6**, which explicitly rejected a per-collection boolean for whether `folk render` *emits* an existing, human-written `## Appearance` section — that would have been "a second, weaker copy of a decision the configuration already makes" about a fact a human already curated. This doc is not about rendering an existing fact; it's about whether a fact (a whole person file) may come into existence without a human writing it at all. Decision 6's collection-already-implies-purpose argument doesn't resolve that question — a `characters` collection existing to hold fictional figures says nothing about whether extraction may write those figures unattended — so a new, explicit, on-disk opt-in per collection is the right shape here even though it wasn't for Decision 6.

## Decision — `COLLECTION.json` with a `curation` field, fail closed to `human`

A collection may place a `COLLECTION.json` file in its own root:

```json
{"curation": "agent"}
```

- **Absent, unreadable, malformed JSON, a non-object document, or any `curation` value other than the literal string `"agent"`** — the collection resolves to `curation: "human"`, which is today's behavior for every collection that doesn't opt in. Every existing collection is protected without being touched. Unrecognized keys in the file are ignored, not carried through (one key, one decision).
- **`{"curation": "agent"}` exactly** — the collection opts in to letting an automated process create new person files in it.

`folk/config.py::load_collection_descriptor(collection_dir)` is the sole reader, and always returns one of exactly the two resolved strings — no caller has to re-derive "was the file missing or malformed" for itself.

The gate applies to **creation by a machine only**. It restricts nothing a human does: a human may create or edit any file in any collection, by any means, regardless of what `COLLECTION.json` says. No folk code path checks this policy on an edit. Once a human edits an agent-curated file, the file is theirs and an agent should stop rewriting it — a documented convention, deliberately not enforced in code, the same posture `appearance.md` Decision 6 and `folk-render.md` Decision 5 both take ("documented convention over code-enforced restriction").

`folk/person.py::create_person_file_as_agent(collection_dir, slug, display_name, body="")` is the one sanctioned creation path a machine caller uses. It:

1. Validates the slug against the same alphabet person files already require (`SLUG_RE`), raising `ValueError` before touching disk.
2. Reads the collection's descriptor and raises `person.CurationRefused` unless it resolves to `"agent"`.
3. Writes `{collection}/{initial}/{slug}/{slug}.md` and returns its `Path`. Refuses (`FileExistsError`) rather than overwriting if the file already exists — creation and update are different acts with different owners, and an existing file might already be a human's hand-edit.

No collection name is enumerated in either function (invariant 7) — `tests/test_collection_curation.py::TestNoCollectionNamesInFolkCode` asserts this by scanning `folk/` for the registered domain-collection names as whole words.

## Not done here

- **No collection ships a `COLLECTION.json` in this repo.** Placing `{"curation": "agent"}` at a collection's root (for example `characters`) is a one-line, no-code step for whoever wires up the first real extraction pipeline against it. Until that file exists in a given collection, that collection is `human`-curated.
- **One caller exists:** `folk/bulk.py`'s `import_batch` mints person files through `create_person_file_as_agent` when its target collection declares `curation: "agent"` (commit `c1b691a`). `folk/sources/directory_scrape.py` itself still leaves minting to its caller.
- **`collection-registry-integrity.md` Decision 3** (the same `COLLECTION.json` file doubling as a collection-existence marker) is a separate, still-unimplemented spec that happens to reuse this file format. Nothing here blocks it, and nothing here implements it.
