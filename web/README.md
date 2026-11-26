# folk web

The folk dashboard (`docs/design/web-ui.md`) -- a browsable, curatable view onto the same three records the CLI reads: person files (git), the journal (NDJSON), and the derived index (`~/.folk/triples.ndjson`). This subtree adds no authority of its own; it is a pure consumer of `folk` the library, imported in-process (`docs/design/web-ui.md` Decision 1), not a shell-out to the CLI. folk core's `pyproject.toml` gains zero dependencies from this -- everything here (FastAPI, Uvicorn, Svelte, Cytoscape) lives in `web/requirements.txt` / `web/ui/package.json` only.

Wave 1b of the initial build was **read-only end to end**: the collection browser, the tiered person profile, the Locus Map and Timeline views, and the ego-graph. Wave 2b adds the write side named in `docs/design/web-ui.md` Decision 1 -- person-file edit (staged diff -> git commit -> index rebuild) and the review-queue GUI (accept/reject -> journal review event / person-file diff -> index rebuild). This is the only part of folk web that writes anything, and the first place in folk's history a network-facing process (not a human at a terminal) triggers a `git commit` -- see "Write endpoints" below for the safety rules that govern it.

## Prerequisites

- A working folk collection (`folk list` should print something).
- At least one `folk index --rebuild` run against it -- this app reads `~/.folk/triples.ndjson`, never writes it (invariant 2), so a stale or missing index just means stale or missing data here, exactly as it would for `folk show`.
- `folk` itself installed (editable install from the repo root: `pip install -e .`) so `import folk` resolves from wherever you run `uvicorn`.

## Proof path: zero personal data

Point the collection selector at `characters` or `authors` -- the seeded collections from `docs/design/collections-and-graph.md` (task 1) (adjust to wherever your `~/.config/folk/collections` actually points; `GET /collections` will tell you). The whole UI is exercisable end to end against these with no personal data present, preserving the CLI's "try it without touching your own data" story. Loci are currently dormant in this seed data (no `loci/` subdirectory registered under `characters`/`authors` yet) -- the Loci page and Map/Timeline views render correctly on an empty registry (a clearly-labeled empty state, not an error) until a Locus file and a locus-declaring source adapter exist (see `docs/design/loci.md` Decision 2 and `docs/design/web-ui.md`'s Scope for v1, "Wiring at least one source adapter to declare `locus:home`" -- separate ops work, not part of this pass).

## Running without Docker

```
# terminal 1 -- API on :8500
cd web
pip install -r requirements.txt
uvicorn api:app --reload --port 8500

# terminal 2 -- Svelte dev server on :5175, proxying /api to :8500
cd web/ui
npm install
npm run dev
```

Open http://localhost:5175.

## Running with Docker

```
cd web
docker compose up --build
```

API on :8500, UI dev server on :5175. `docker-compose.yml`'s volume mounts are host-specific -- they bind-mount `~/.config/folk`, `~/.folk`, and wherever your collections live at identical absolute paths inside the container (folk's `config.py` resolves via `Path.home()` and `collections.json` stores absolute host paths, so path identity has to be preserved across the container boundary). Adjust the mount list to match your own `~/.config/folk/collections`.

**Don't edit the tracked compose file per machine — use a `docker-compose.override.yml`** (untracked; compose merges it automatically). Two gotchas the shipped file hits on any machine whose collections aren't under `~/people`: (1) the shipped `api` mount maps `~/people` to `/home/folkuser/people`, which is *not* an identical-path mount, so absolute paths in `collections` won't resolve in the container; (2) the default ports may already be taken (`ss -ltn | grep -E ':(8500|5175)\b'` before `up`). A merged `volumes:`/`ports:` list *appends* by default, so use the `!override` tag (Compose v2.24+) to replace rather than extend:

```yaml
services:
  api:
    volumes: !override
      - /home/you/.config/folk:/home/folkuser/.config/folk:ro
      - /home/you/.folk:/home/folkuser/.folk:ro
      - /data/people:/data/people:ro        # identical host:container path, one per collection
  ui:
    ports: !override
      - "5176:5175"                         # host port only; the container port stays 5175
```

Mount each collection directory individually rather than a parent tree, so a sibling directory with unrelated sensitive files is never visible to the container. The index is mounted read-only, so run `folk index --rebuild` on the *host* (after setting up `~/.config/folk/collections`) before starting, and again after any data pull — the container can't rebuild it. Verify with `docker compose ps` (both `healthy`), `curl localhost:8500/collections`.

## Ports

- API: `8500`, UI dev server: `5175` -- picked to avoid colliding with other services you might already be running; adjust freely.

## Endpoints

Read (v1, unchanged since Wave 1b):

- `GET /collections` -- every collection folk knows about.
- `GET /people?collection=X&tag=Y` -- the people grid (wraps `person.list_persons`).
- `GET /people/{slug}?collection=X` -- full tiered person profile (`person.show_person` + `journal.person_profile`, staleness computed at read time, superseded records collapsed) -- the same data `folk show <name>` prints, JSON instead of text.
- `GET /graph/person/{slug}?depth=N` -- ego-graph edge list as `{nodes, edges}` JSON, for the Map view's node-link rendering.
- `GET /graph/locus/{slug}` -- a Locus's cast-graph edge list, same shape.
- `GET /loci` -- every registered Locus.
- `GET /loci/{slug}` -- a Locus's tiered profile (same rendering path as a person page, per `docs/design/loci.md` Decision 3).
- `GET /loci/{slug}/timeline` -- locus-scoped journal events sorted by date (`when`, falling back to `last_reinforced` when a source adapter didn't supply an in-story date).

Write (Wave 2b, `routers/review.py` and `routers/edit.py`):

- `GET /review` -- wraps `review.pending_items()` unchanged, plus a computed-not-written diff preview attached to each `bedrock` item (`review.preview_bedrock_edit`, read-only) and a `description` field (`review.describe_item`) for display.
- `POST /review/action` -- body `{item, verdict}`, `verdict` one of `accept`/`reject`. `item` is a single object, never a list -- the containment rule (`docs/design/web-ui.md` Decision 2e: counterparty-sourced items can never be batch-accepted) is enforced by this request shape itself, not by a runtime check or by the UI simply not offering a batch button. Branches on `item["type"]` exactly like `folk/cli.py`'s `cmd_review`/`_run_interactive_review`, so an accept/reject here produces byte-identical journal `review` events and person-file diffs to the same action at the terminal.
- `POST /people/{slug}/edit/preview` -- body `{collection, section, content}`, `section` validated against an explicit allowlist (`routers/edit.py`'s `ALLOWED_SECTIONS`). Returns `{diff}` via `difflib.unified_diff` over the file's current vs. edited content. Writes nothing.
- `POST /people/{slug}/edit/commit` -- same body, re-derives the diff server-side (never trusts a diff the client sent back), writes the file, commits it in the git repo that actually owns it (found via `git rev-parse --show-toplevel`, which may not be the collection directory itself), scoped to exactly that one file (`git add`/`commit -- <path>`, never `-A`), then runs `folk index --rebuild`. Returns `{committed, commit_sha, diff}`, or `{committed: false, reason: "no changes"}` when there's nothing to write.

Both write endpoints resolve `slug` + `collection` through folk's own lookup (`config.resolve_collection_dir` + `person._find_person_file`) exactly like `GET /people/{slug}` already does -- never a client-supplied filesystem path. See `routers/edit.py`'s module docstring and `tests/test_edit_write.py` for the full set of safety properties this is meant to hold, and `tests/test_review_containment.py` for a live proof that the single-item request shape rejects a batch before any handler code runs.

## Frontend stack and choices

Svelte 4 + Vite, hash-based routing (no router library -- same house pattern as `digger`/`transcript`'s `App.svelte`), plain `fetch`-based API client (`ui/src/lib/api.ts`). The Map view uses **Cytoscape.js** for the interactive node-link graph (Decision 1 named it alongside Svelte Flow as an option) -- picked over Svelte Flow because it's a plain imperative library that mounts onto a `<div>` in `onMount`, no Svelte-specific wrapper dependency to track, and its styling/layout API is a good match for a small cast graph (dozens of nodes, not hundreds). `views/Review.svelte` (Wave 2b) is the review-queue GUI: items grouped by type (mirroring `folk/cli.py`'s `REVIEW_LABELS`/`REVIEW_ORDER`), each with its own accept/reject button firing the single-item endpoint -- there is no "select all" control anywhere in this view, for any item type, matching the API's single-item shape.

## Web-side tests

`web/tests/` (plain `unittest`, run with `cd web && python3 -m unittest discover tests`) -- isolated from real folk config and the real `~/.folk/triples.ndjson` throughout (temp git repos, monkeypatched `config.load_collections`/`triples.index_rebuild`). `test_edit_write.py` covers the person-file write path: section allowlist rejection, 404s (missing person, unknown collection, path-traversal-shaped slugs), preview-vs-commit diff agreement, commit scoping to exactly one file, the bio/`__main__` heading-preservation special case, and repo-root resolution when the collection dir is nested under a larger git repo. `test_review_containment.py` covers the review-queue dispatch (accept/reject per item type, matching the CLI) and proves the containment rule structurally (constructing a list-shaped request body raises a Pydantic `ValidationError` before the handler runs).

## What's explicitly not here

Corkboard, Studio, any UI for Part B's arbitrary-Bedrock-section inline edit beyond the two endpoints themselves and the `api.ts` client methods (`editPreview`/`editCommit`) -- `docs/design/web-ui.md` Part A explicitly asks for a `Review.svelte` view; Part B does not name a specific Person-page UI component, so none was added this pass to avoid touching `views/Person.svelte` while a sibling build wave is concurrently working in `web/`. See `docs/design/web-ui.md` "Scope for v1" for the fuller list and rationale.
