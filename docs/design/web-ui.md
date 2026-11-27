# web UI — the folk dashboard (Phase 4)

**Status:** partly implemented in `web/` (checked 2026-11-25): the read endpoints for collections, people, graph, loci, agenda, and focus; the review-queue and person-file edit write endpoints; and the Home, Collections, Person, Loci/Locus (map and timeline), and Review views. Corkboard and Studio are deferred, as Decision 2 says. The exit criteria below were not verified in that check. Originally written 2026-07-26 as a DRAFT, the first design pass at Layer 5 / Phase 4, which every prior doc deliberately parked ("the big build, and it is last"). The four stop-and-asks from the first pass (subtree vs. sibling repo, import-vs-shell-out, v1 locus-view cut, the invariant-8 dependency sign-off) were confirmed by the maintainer 2026-07-26 — see "Decisions confirmed by the maintainer" below. This doc has not had the full-read-through confirmation that `journal-in-folk.md`-style specs get.
**Context:** the wider persona-agent architecture design (Layer 5 — the Locus GUI, the Focus Engine, "views as projection"); `docs/site/phases.html` ("Phase 4 — GUI: the visual views (Timeline, Corkboard, Map, Studio). The ranked lists exist first; glow and heat come later."); `docs/design/folk-surface.md` (the ranked-list engine the Focus panel visualizes); `docs/design/review-queue.md` (the write/curation flow this puts a face on); `docs/design/loci.md` (the locus views). Sibling future-direction draft: `docs/design/distributed-folk.md`.

## Why

Most people will never touch the CLI. The daily value of folk — "remember your people, don't lose the thread, don't forget the birthday" — wants a surface you open and browse, not a command you remember. Everything below the interaction layer already works in a terminal: three records, the journal, the review queue, the surface/decay engines. The web UI is **the multiplier, not the foundation** — it adds no new authority, invents no new storage, and can be deleted without losing a fact. It is a *view onto* and a *curation front-end for* data that lives, exactly as it does today, in person files (git), the journal (NDJSON), and the derived index.

The architecture named the endpoint (five views + a Focus Engine) but left it undesigned on purpose, so the testable terminal pieces could land first. They have. This doc designs the surface that sits on top of them.

## Decision 1 — the web UI is a separate client layer; folk core stays stdlib-only

folk core (the `folk/` package, its `pyproject.toml`, the CLI) does not change and gains no dependency — invariant 8 holds literally end-to-end for the thing that owns the data. The web UI is a **distinct layer that consumes folk**, living in a `web/` subtree with its own dependency manifest (FastAPI + Uvicorn backend, Svelte frontend, Docker to run — matching the house style of `digger`, `transcript`, `disptch`). folk's `pyproject.toml` stays empty of runtime deps; `web/`'s deps never leak into it. **Confirmed by the maintainer 2026-07-26: `web/` subtree in this repo**, not a sibling repo — versions in lockstep with the data model it renders; if multiple community web front-ends appear later, splitting one out is a fork, not a reason to hedge the first build.

The backend **imports folk as a library** (same machine, same Python) rather than shelling out — it gets `journal.person_profile`, `surface.surface`, `graph`, `review`, `render` directly, in-process, no subprocess or parse-the-CLI-output tax. That folk's importer (FastAPI) has dependencies does not violate invariant 8: the invariant governs folk, not its callers. **Confirmed by the maintainer 2026-07-26.**

**On the frontend dependency itself (the formal invariant-8 sign-off):** the maintainer confirmed 2026-07-26 that the standard stack (FastAPI + Svelte + Docker) is fine to proceed with — it's already the house style, not a new pattern. Two narrowly-scoped frontend libraries are worth naming now rather than hand-rolling, since they simplify exactly the two views that most need real UI work and are easy to swap or drop later without touching folk core or the backend's API shape:
- **An interactive graph/node-link library** (e.g. Cytoscape.js, or Svelte Flow) for the Map view — `folk graph --locus`/`--person` already emits Mermaid; the web UI's interactive version (pan/zoom/click-through to a person page) is a rendering choice on top of the same edge list the backend already returns as JSON, not a new data model.
- **A drag-and-drop library** (e.g. `svelte-dnd-action`) for the Corkboard view, when it's built (see Decision 2) — a corkboard move is a curation act that still goes through Decision 1's write path (a person/Locus file edit); the library only supplies the drag gesture.

Both are additive, frontend-only, and swappable — neither is load-bearing for anything folk core does, so picking the "wrong" one later costs a rewrite of one view, not a data-model change.

**The read model:** the backend reads person files + the triple index through folk's existing library functions. It never re-derives trust, staleness, or supersession — it renders exactly what `folk show`/`folk surface` already compute, so a person page and `folk show <name>` can never disagree (an exit criterion).

**The write model — the load-bearing part:** the web UI's only write paths are the three folk already sanctions, and nothing else:

1. **Person-file edits → git commit.** Curated, human-tier facts (bio, archetype/voice, associations, tags, dates, defining moments). The UI stages the edit, shows the exact diff (the "typist, not author" rule from `review-queue.md` applies to the UI the same as the CLI), the human confirms, the file is written, `git commit`, then `folk index --rebuild`. **The git commit is the "full ingestion" gate** the user asked for — an edit is visible in the working tree as a staged diff and only becomes durable history on commit.
2. **Journal appends (lint-gated).** Any programmatic append goes through `journal.append_event(..., run_lint=True)` — lint before append (invariant 6), all-or-nothing, quarantine on hard failure. The UI never writes a journal segment directly (invariant 3) and never hand-edits one.
3. **`folk index --rebuild`.** The only thing that writes the index (invariant 2). The web UI triggers a rebuild after a write; it **never writes an index line itself** — a directly-written index line is destroyed by the next rebuild, silently, so the UI must not be tempted to "optimistically" patch the index for snappy feedback. Snappy feedback comes from re-reading the rebuilt index (rebuild is fast and deterministic) or from optimistic client-side state that a rebuild confirms.

No `conf` numbers anywhere (invariant 5) — trust is the tier badge the read model already carries. The web UI cannot make anything authoritative in two places (invariant 1): it edits person files *or* appends journal events, never both for the same fact, never a third store of its own.

## Decision 2 — v1 is a unified dashboard: people, loci, focus, reminders as peers

Not person-first-then-loci-later; the home is a **dashboard spanning both** from the start (the broadest of the three shapes considered, chosen deliberately). **Correction to the initial draft:** Loci are not, in fact, entirely dormant — a real Locus already exists (`locus:home`, in the `folks` collection, created 2026-07-23; cast: a family member via `appears_in`). What's still missing is the other half of task 5/9's precondition: **no source adapter declares `locus` on any journal event yet**, so `locus:home` has a curated cast member but no locus-tagged history flowing through it — the Map/Timeline views would render correctly but nearly empty, and `folk surface --locus home` has nothing cross-context to find. Per `loci.md` Decision 2, locus tagging must be **declared by the source adapter, never inferred** — so making the Locus Model real is a small, deterministic wiring step (a Hermes profile, or a session, bound to `locus:home` in `promotion.json`, mechanically stamping the field), not a UI concern. **The maintainer confirmed 2026-07-26 this is worth doing now, not deferred as someone else's ops task** — the whole point of pairing the web UI with real locus data is to actually exercise the Locus Model instead of shipping it dormant a third time (after tasks 5 and 9). This is called out explicitly in Scope for v1, below.

The dashboard's five regions:

### 2a. Home — reminders + focus + queue
- **Upcoming reminders** — the flagship "don't forget the birthday" view. A deterministic read-time query over `## Dates` (see Decision 4) + injected `now`: the next N dated events across all collections, soonest first. No writes, no LLM, byte-identical given `now` — the same discipline as `folk surface`/`journal.staleness`.
- **Focus** — the attention panel (Decision 3): people/loci ranked by the Focus Engine, shown as a list first, glow/heat later.
- **Review queue badge + recent activity** — count of pending review items; recently-touched people/loci.

### 2b. Collection browser
People grid, filterable by tag and collection/context (`folk list --context`/`--locus` with a face). Switch collections the way `folk context` does. Runs against the seeded `characters`/`authors` collections with zero personal data, preserving the CLI's "try it without touching your own data" story (an exit criterion).

### 2c. Person page
The full `journal.person_profile` rendered visually: bio, archetype/voice, associations (as an interactive ego-graph, `folk graph --person`), media gallery, dates, defining moments, and the **tiered profile** — curated / observed / stated / interpreted as distinct visual weights, with `[aging]`/`[stale]` markers and a collapsed "superseded (not current)" section exactly as `folk show` groups them (task 8's read model, unchanged). Inline edit on any Bedrock section → staged diff → commit (Decision 1's write path).

### 2d. Locus views — pared to the essential two for v1
Per the architecture's "views as projection," each a rendering of the same triples, in build order. **The maintainer confirmed 2026-07-26: v1 ships only the two views that are already fully backed by existing engines** — the point is to get the real `locus:home` data (Decision 2, above) in front of a browser quickly, not to build all four before either wiring or a UI exists for either:
- **Map** — `folk graph --locus <slug>` (the cast graph; Mermaid today, an interactive node-link graph in the UI via the library named in Decision 1). **v1.**
- **Timeline** — locus-scoped events by date (`folk list --locus` sorted by `when`/`ts`). **v1.**
- **Corkboard** — Kanban-style columns over the locus's scenes/cast. **Deferred to v2** — the first genuinely UI-native view (drag-drop has no terminal equivalent), real build work, not just a rendering choice over an existing engine. When built, a corkboard *move* is a curation act and travels the Decision 1 write path (it edits a person/Locus file), never a hidden index write.
- **Studio** — the 3D "movie set." **Explicitly deferred, possibly forever** — the architecture's own note: "the first four views cover 90% of the value."

### 2e. Review queue — the GUI for `folk review`
The web UI is a **second front-end to the exact same `review.py` queue**, never a parallel mechanism: vocab proposals, entity near-duplicate merges, bedrock suggestions (with diffs), and quarantined lint failures. Accept/reject emit the identical journal `review` events and/or person-file diffs the CLI produces. **The containment rule carries over unchanged and is a security property, not a UX preference:** promotions from sessions with an external `counterparty` are surfaced one at a time and never batch-accepted — the memory-poisoning boundary must hold in the UI exactly as in the CLI. "Select all → accept" is forbidden for counterparty-sourced items by construction.

## Decision 3 — the Focus Engine reuses the surface engine; `folk focus` is its terminal-first form

The dashboard's Focus panel is the visual sibling of `folk surface`. The architecture's four attention signals (momentum, gravity, recurrence, attention-history) overlap almost exactly with `surface`'s four rankers (tier, recency, recurrence, gravity) — the difference is *what gets ranked*: `surface` ranks **triples** (facts to brief a session with), the Focus Engine ranks **containers** (people/loci to attend to). This is precisely the deferred `folk focus` command from `loci.md`/`folk-surface.md` — "a thin second caller of this engine that ranks containers rather than triples."

So the build order stays terminal-first, per the architecture ("the ranked lists exist first; glow and heat come later"): **build `folk focus` as a CLI command over the shared RRF engine, deterministic and testable, then the UI visualizes its output** (list → glow/heat). No new ranking logic is invented in the web layer; the web layer never becomes a place where scoring lives. If `folk focus` isn't built, the Focus panel shows recently-touched + reminders and nothing is lost. (Momentum and attention-history as *new* signals beyond surface's four are an open modeling question — deferred; v1's Focus panel can ship on the existing four.)

## Decision 4 — dates are a new Bedrock section, not new schema

Reminders need one new datum folk doesn't track today: dates (birthday, anniversary, "met on"). This lands as human-curated Bedrock — a **`## Dates` section in the person file**, parsed the same way `## Tags`/`## Archetype` already are (add to `person.py`'s known sections; surface in `folk show`). Format is a curation convention, not schema — e.g. `- birthday: 03-14` (month-day, year optional). **No change to `journal-schema.md`** — dates are person-file facts, not journal events; if the implementation seems to need a journal event kind or an index field for dates, that is escalation item 1 (stop and ask).

The "upcoming" query is terminal-first too: a `folk agenda [--within 30] [--now ISO] [--json]` command computes the next dated events deterministically (recurring month-day rolled forward against injected `now`), the web dashboard visualizes it. Pure read, no LLM, no writes — the same shape as `staleness`/`surface`. Proactive *push* ("Telegram: birthday tomorrow") is **not** the web UI's job — that's the agent layer (Hermes/cron) consuming `folk agenda --json`, noted here only to draw the boundary: the web UI *shows* reminders; it does not *send* them.

## Decision 5 — local-first, single-user, git as the audit log

v1 runs on localhost / the homelab, single-user, unauthenticated-behind-the-network like the other house apps — because it is a **write surface** (it triggers git commits and lint-gated journal appends), not a public read-only site. Exposing it to other people is the whole subject of the sibling `distributed-folk.md` draft and is out of scope here. Every durable change the UI makes is a git commit or a journal event, so the audit trail is the one folk already has — no separate "web activity log" store (that would violate invariant 1). This keeps the UI honest: if you can't see a change in `git log` or the journal, the UI didn't really make it.

## Scope for v1

- `web/` subtree: FastAPI backend importing folk as a library; Svelte frontend (+ a node-link graph library and, once Corkboard is scheduled, a drag-and-drop library — Decision 1); Docker Compose to run. folk's own `pyproject.toml` unchanged.
- Read endpoints backed by existing folk library functions: collection list, person profile (tiered, with staleness/supersession), ego-graph, locus map/timeline (Map + Timeline only — Corkboard/Studio deferred), surface/focus output, agenda.
- Write flows, all through Decision 1's three sanctioned paths: person-file edit → staged diff → git commit → rebuild; review-queue accept/reject → journal review event / person-file diff.
- `folk focus` (CLI, over the surface RRF engine, ranking containers) and `folk agenda` (CLI, deterministic upcoming-dates) as the terminal-first backing for the Focus and Reminders panels.
- `## Dates` parsed in `person.py`, surfaced in `folk show`.
- **Wiring at least one source adapter to declare `locus:home`** (Decision 2) — a config-level binding (e.g. a Hermes profile → `locus:home` mapping in `promotion.json`, or an explicit per-session override), mechanically stamped, never LLM-inferred, per `loci.md` Decision 2. Small and deterministic, but necessary so the Map/Timeline views and `folk surface --locus home` have real cross-context data to show rather than an empty-but-correct shell.
- Runs against the seeded `characters`/`authors` collections end-to-end with no personal data, as a parallel proof path that needs no adapter wiring.

**Deferred, deliberately:** Corkboard (to v2) and the Studio (3D) view (possibly forever); proactive push notifications (agent layer, not the UI); multi-user / federation / any network exposure (`distributed-folk.md`); mid-conversation surfacing (a latency problem on the same engine, already deferred in `folk-surface.md`); momentum/attention-history as new Focus signals beyond surface's four; real-time collaborative editing; embeddings or any model-derived ranking anywhere in the UI.

## Decisions confirmed by the maintainer (2026-07-26)

All four stop-and-asks from the initial draft are resolved:

1. **`web/` subtree**, not a sibling repo — split out later only if multiple community front-ends actually appear.
2. **Backend imports folk as a library**, not shell-outs to the CLI.
3. **v1 locus views pared to Map + Timeline** — Corkboard/Studio deferred — with the explicit condition that the real `locus:home` data actually gets exercised (the source-adapter wiring in Scope for v1), not left dormant a third time after tasks 5 and 9.
4. **Standard stack (FastAPI + Svelte + Docker) confirmed** — the house pattern from `digger`/`transcript`/`disptch`; two narrow library suggestions (graph rendering, drag-and-drop) named in Decision 1 rather than left to be hand-rolled, since they simplify the two views that most need real UI work.

## Open questions (remaining)

1. **Which config surface declares an adapter's locus** — a per-profile mapping in `promotion.json`, a per-session override, or both. Small, not a design fork; resolve when the wiring task in Scope for v1 is actually implemented.

## Exit criteria (for whenever this is built — proposed, testable gates)

- A person page renders the same tiers, staleness/supersession markers, associations, and sections that `folk show <name>` prints for the same person — no divergence, because both call the same library functions.
- After any web-driven write, `folk index --rebuild` run twice is byte-identical, and the resulting index equals a clean rebuild from person files + journal — proving the web layer wrote no index line and no second authority (invariants 1, 2).
- Every durable web change appears in `git log` (person-file edits) or as a journal event (review/promotion decisions); nothing durable exists that neither records.
- Review actions taken in the UI produce byte-identical journal `review` events and person-file diffs to the same actions in `folk review`; counterparty-sourced promotions cannot be batch-accepted in the UI.
- The reminders/agenda panel is byte-identical across runs given a fixed `now`, and performs no write.
- folk's `pyproject.toml` gains no runtime dependency; folk core still runs and tests green with the web layer absent.
- The whole UI is exercisable against the seeded `characters`/`authors` collections with no personal data present.
