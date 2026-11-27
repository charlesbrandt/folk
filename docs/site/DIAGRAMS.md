# Diagram manifest — docs/site

This manifest is the tracking half of the site's diagram discipline: **no diagram ships without a defined utility**, and every figure in the site has exactly one row here. If you add a figure, add its row (id, page, utility) in the same change; if a figure's utility can't be stated as a question the diagram answers, the figure shouldn't exist.

## Process

- **Default form is hand-authored inline SVG**, styled by `folk.css` variables so every diagram adapts to light/dark automatically. This is a deliberate echo of folk's own values: deterministic, diffable in git, editable by the next agent, no binary blobs, no external assets, no build step — the site is plain files opened in a browser.
- **AI image generation is permitted but scoped**: it is the wrong tool for schematics (unreliable text rendering, not editable, not diffable), so it is reserved for *evocative/illustrative* art where precision doesn't matter — e.g. a mood illustration for a Locus or a hero image. None exist yet. If one is added: (a) the generated file goes in `docs/site/images/`, (b) the generation workflow/prompt is committed alongside it as `<name>.prompt.json` (ComfyUI workflow or equivalent) so it can be regenerated, and (c) it gets a row here with form `generated` and a stated utility like any other figure.
- **Source of truth is the design specs.** Every diagram depicts claims made in `docs/design/*.md` or `CLAUDE.md` invariants — the "source" column names them. When a spec changes a depicted behavior, the diagram is stale and this manifest is the checklist for finding which ones.
- Figures are addressable: each `<figure>` carries the `id` listed below (e.g. `promotion.html#fig-containment`).

## Figures

| id | page | form | utility — the question it answers | source |
|----|------|------|-----------------------------------|--------|
| `fig-system-map` | `index.html` | inline SVG | How do all the pieces fit on one screen — who writes what, what derives from what, and why person files have only two inbound arrows? | README storage model; `docs/design/journal-in-folk.md` |
| `fig-three-records` | `three-records.html` | inline SVG | Which record is authoritative for what, who is allowed to write each, and why the index is drawn dashed (deletable)? | CLAUDE.md invariants 1–2; `journal-in-folk.md` |
| `fig-rebuild-pure` | `three-records.html` | inline SVG | Why is rebuild trustworthy without being an authority — what goes in, what determinism means (run twice ≡ byte-identical)? | CLAUDE.md invariant 4; `journal-in-folk.md` "Rebuild" |
| `fig-tier-ladder` | `trust.html` | inline SVG | What is the trust ordering, what earns each tier, and why does `bedrock` sit outside the ladder entirely? | `journal-schema.md` "Trust tiers"; CLAUDE.md invariant 5 |
| `fig-append-only` | `journal.html` | inline SVG | How does an append-only log get corrected — what do `review` and `redaction` events point at, and how do their effects differ at replay? | `journal-schema.md` per-kind rules; CLAUDE.md invariant 3 |
| `fig-roots-segments` | `journal.html` | inline SVG | Where do journal files physically live — how do per-domain roots keep domains separate and per-writer filenames make multi-machine sync conflict-free? | `journal-in-folk.md` "Layout"; `session-promotion-job.md` transport |
| `fig-promotion-pipeline` | `promotion.html` | inline SVG | What is the nightly path from conversation to journal — where the only LLM sits, why it has no arrow to the journal, and what the two exits (append-all / quarantine-all) are? | `session-promotion-job.md` per-session flow; CLAUDE.md invariant 6 |
| `fig-containment` | `promotion.html` | inline SVG | Why is the review queue a security boundary — how does honestly-recorded poison get stopped before durability, and why are external-counterparty sessions never batch-accepted? | `review-queue.md` "Why" (MINJA); `journal-schema.md` `counterparty` |
| `fig-domain-islands` | `domains.html` | inline SVG | How do separate collections stay separate while still linking — cross-domain by predicate, not by schema? | `collections-and-graph.md`; README "Collections" |
| `fig-locus-barrier` | `domains.html` | inline SVG | What is the difference between an ephemeral guest appearance and a durable `guest_of` edge, and what does "the barrier is enforced on the Locus side" mean concretely? | `loci.md` Decisions 1–3 |
| `fig-phase-timeline` | `phases.html` | inline SVG | What has shipped, what is specced, and what is deliberately undesigned — the project's current position at a glance? | spec status lines in `docs/design/*.md` (build order: `collections-and-graph.md`, `journal-in-folk.md`, `review-queue.md`, `session-promotion-job.md`; Phase 4 status: `web-ui.md`) |
| `fig-decay-supersession` | `phases.html` | inline SVG | Why do staleness and supersession need opposite mechanisms (read-time lens vs rebuild projection), and what are the guards (tier guard, exact-tie, opt-in classification)? | `decay-and-supersession.md` Decisions 1–3 |
| `fig-surface-rrf` | `phases.html` | inline SVG | How does surfacing rank without a model — four total orders, RRF, and the two filters — inside a fixed budget? | `folk-surface.md` Decisions 1–2 |
| `fig-appearance-merge` | `appearance.html` | inline SVG | When a checkpoint is selected, which base labels survive, which are overridden in place, and which are appended — so what text does a render actually see? | `appearance-checkpoints.md` Decision 2; `folk/person.py` `merge_appearance_checkpoint` |
| `fig-curation-gate` | `import-and-curation.html` | inline SVG | Which path can create a person file, what does an automated caller get in a human-curated collection, and why does a human edit meet no gate at all? | `collection-curation.md` Decision; `folk/config.py` `load_collection_descriptor`; `folk/person.py` `create_person_file_as_agent` |
| `fig-batch-skip` | `import-and-curation.html` | inline SVG | When one scraped row is malformed, what happens to it and to its neighbors, and when does the index get rebuilt? | `bulk-import.md` Decisions 1–2; `folk/bulk.py` `import_batch` |
| `fig-read-write-lanes` | `views-and-web.html` | inline SVG | Which views only read the records, which web endpoints can write, and what does each write land as (a journal event or a one-file commit) before the index is rebuilt? | `folk-surface.md` Decision 3; `web-ui.md` Decisions 1 and 5; `web/README.md` endpoints |

## Non-SVG annotated figures

Two figures are annotated code blocks rather than SVG (HTML `<pre>` with colored spans); they're tracked here for completeness because they serve a diagram's role:

| page | figure | utility | source |
|------|--------|---------|--------|
| `journal.html` | annotated promotion event | Which fields make up an event, grouped by role (claim / actor / evidence chain / identity)? | `journal-schema.md` field table |
| `three-records.html` | person file example + index record example | What do the human-tier source and the derived record actually look like? | README person-file format; `journal-in-folk.md` index shape |
