# folk vs. a project — the scope boundary, written down once

**Status:** written 2026-08-30, following a scope review with the maintainer after folk's public release. Not a new invariant — it names a boundary that CLAUDE.md's invariants and several already-landed decisions were independently enforcing without ever stating it as a rule, so a future contributor (human or agent) doesn't have to re-derive it from precedent before extending `locus-type.md`'s org modeling.
**Context:** `docs/design/locus-type.md` and `docs/design/bulk-import.md` (both landed today — the real use case behind both is "tracking people, teams, and shared resources across a large organization," i.e. collaborators and orgs, not the work product); `docs/design/appearance.md` (the precedent this doc generalizes: "does this change between two frames of the same piece"); `docs/design/distributed-folk.md` (federation scoped to the people-graph, a sibling case of the same line); `eval/vocab.json` (a `project` entity type and `worked_on`/`prioritizes` predicates already reserved as the cross-reference surface, unused as anything but a reference target); the "Proposed Consumer" section of the `folk` skill (the dream-generation project as the working example of a satellite project consuming folk by reference).

## Why

The maintainer has a separate line of research interest — research-project tracking, electronic-lab-notebook-style provenance, task/project management, portable identity via AT Protocol — with its own history (old notes on Appflowy/Asana/Taiga, on LabArchives and git-based lab notebooks, and `distributed-folk.md`'s own study of AT Proto/SSB/Nostr as prior art). None of that is being built into folk. It belongs in a separate, dedicated project — resolved 2026-08-30 as `~/repos/projectloop` (also `github.com/charlesbrandt/projectloop`), revived from a dormant prior implementation rather than a new repo; see its `projectloop` skill and `docs/design/research-project-type.md` for the full trail. This doc exists so that decision is on record, and so the boundary it implies is explicit rather than something every future design doc has to rediscover on its own — which is exactly what `locus-type.md`'s `grant`/`lab`/`research-center` types made newly tempting to blur, by giving orgs a file for the first time.

## The rule

**folk owns identity and relationships that are true independent of any one project. A project owns everything specific to itself, and references folk's `person:`/`locus:` slugs for identity rather than folk absorbing the project's content.** This is `appearance.md`'s "does this change between two frames of the same piece" line, generalized past physical description to the whole repo: a person's durable facts, their orgs, and who they're connected to are folk's; what a specific research effort produced, tracked, or decided is the project's.

## Precedent already drawing this line, independently

- `eval/vocab.json` reserves a `project` entity type and predicates (`worked_on`, `prioritizes`) that let a person be linked *to* a project by reference — nothing in the schema describes what happens inside one.
- `appearance.md` drew the identical line for physical description: durable traits are folk's, per-piece staging is the project's, and reuses the language this doc borrows.
- The dream-generation project (`folk` skill, "Proposed Consumer" section) is the working example: it references `person:<slug>`/`locus:<slug>` via `folk render --format dream`, keeps every rendering-only field (negative prompt hints, reference weights) on its own side, and writes back a single `depicted_in` observation triple rather than growing folk to understand renders.
- `locus-type.md` and `bulk-import.md` scope organizational Loci to identity — a name, a description, curated associations (who's in it, who runs it) — not to what the org produced.

## The watch point: Locus descriptions

`loci.md`'s Decision 3 lets a Locus file's description say "what it's for." That's the one crack in an otherwise clean boundary: `appearance.md`'s own history shows this exact shape drifting before — "a human can already stuff physical description into a bio, and some do," which is why `## Appearance` had to be carved out as its own addressable section years after person files already existed. A `locus:some-grant` file is one loosely-worded description away from accumulating actual research narrative with nothing in the design stopping it. Nobody has done this yet; it is a foreseeable failure mode, not a current violation, and needs no fix today — noting it here is the fix, so a future reviewer of a Locus file with a paragraph of research findings in its description recognizes it as the same pattern this doc named, not a new problem.

## The interface for projectloop (the separate project, resolved 2026-08-30)

`~/repos/projectloop` should consume folk the same way the dream-generation project does: reference `person:<slug>` and `locus:<slug>` for identity, mint its own `project:<slug>` (already reserved in `vocab.json`'s type list), and write `worked_on`/`prioritizes`-style edges back into folk exactly as `depicted_in` does today — an observation triple from a mechanical, versioned adapter, never a folk-side feature that understands the project's content. If it wants a locus->grant funding edge or similar, that is a one-line `vocab.json` predicate addition (config, not code, per invariant 7), not a schema change. Everything else — hypotheses, protocol steps, results, task/kanban state, provenance chains, compliance-grade timestamping or witnessing for IP/grant data-sharing requirements — is that project's own record, in its own repo, never inside `~/.folk/` or a folk person/Locus file.

## Not folk's job

Named explicitly so a future design doc doesn't have to reconstruct why these were rejected:

- **Notebook content** — hypotheses, protocol steps, results, provenance narrative. folk's journal triples are relationship-shaped (`subject — predicate — object` about people and orgs); a lab notebook's unit of record is observation/experiment-shaped, a different data model entirely.
- **Task/project management** — deadlines, kanban, dependencies. Not a folk gap so much as a different tool's whole job (the old Appflowy/Asana/Taiga survey in the maintainer's notes was already evaluating standalone tools for exactly this, years before folk existed).
- **Compliance-grade integrity** — timestamping, witnessing, immutable provenance for IP or grant (e.g. NIH) data-sharing obligations. folk's one "forget" mechanism (`kind: redaction`) is privacy-first — built to make a fact stop existing on request. A compliance notebook needs close to the opposite guarantee: proof a fact existed, unaltered, at a given time. Building both into one tool would put them in tension for no reason; they belong to different records with different owners.

## The federation angle stays scoped too

`distributed-folk.md` studies AT Protocol, SSB, Nostr, and ActivityPub as prior art for federating folk's *people graph* specifically — "what would it mean for many people, each running their own folk, to share the parts they choose about the connections between them." That scope holds under this doc's rule without any change needed. If a future project-tracker wants its own portable-identity or federation story, it should independently borrow the append-only-log/content-addressed-event *pattern* the same prior art suggests — not depend on folk's federation machinery once (if ever) it exists. Federating identity and federating research content are different problems with different consent models; conflating them was never proposed, and this note is here so it stays that way.
