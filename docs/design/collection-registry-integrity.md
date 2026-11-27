# Collection registry integrity

**Status:** spec. Decision 2 is not implemented (checked 2026-11-25: `person._person_files` still yields nothing for a missing directory, and `folk -d <missing-path> list` prints "no people" and exits 0). Decision 2 (splitting the collection scanner's fail-open) is the immediately actionable piece; Decision 1 is a convention to apply on the next collection placement; Decision 3 rides on the `COLLECTION.json` file introduced by `collection-curation.md`, and needs no new file format of its own.
**Context:** `CLAUDE.md` invariant 7 (collections are config, never code); `docs/design/collections-and-graph.md` (how collections get registered); `docs/design/collection-curation.md` (the `COLLECTION.json` file this doc reuses); `folk/config.py`, `folk/person.py`

## Why

A collection is a registry entry pointing at a directory. Registration is cheap and deliberately so — invariant 7 depends on adding a collection being a one-line config change. The cost of that cheapness is that the registry entry and the directory it names are two separate facts that can silently drift apart: the directory can be renamed, moved into a different repo, never created on a second machine, or created but never committed, and none of that changes the registry entry. The registry says the collection exists; only the filesystem knows whether it does.

That drift would be a minor annoyance if folk noticed it. It doesn't. The collection scanner treats a registered directory that isn't there as *zero residents* rather than an error, so a collection pointing at nothing looks exactly like a collection that is simply empty — a state every new collection legitimately passes through. A collection can therefore be registered, queried, and reported on for a long time while holding no data at all and never having held any, and every command involved will exit 0. When the data does exist somewhere, this failure mode also actively hides it: the tool answers "nothing here" instead of "I can't find where here is," so nobody goes looking for the real copy.

The fail-open is not a bug someone introduced carelessly. It was added on purpose, to stop an unrelated crash: iterating every registered collection should not blow up because one of them happens to be absent on this machine right now. That is a real requirement. The mistake was letting one lenient rule cover two situations that want opposite answers.

## Decision 1 — a collection lives in the repo of whatever writes it

Placement is a design decision, not an implementation detail, because a collection inherits the visibility, backup, and sync behavior of the repository it physically sits in — not of whatever references it. A collection that only one project writes, but that lives in a tree only some machines clone, is a data-loss shape regardless of how correct the registry entry is.

To place a new collection, answer in order and stop at the first yes:

1. Do these entities already exist in some collection? Then don't make a new one — reference the existing collection by slug from the consuming project.
2. Are they wholly invented by, and used only within, one project? Colocate them with that project: a `folk/` subdirectory at the top of its repo, registered under that repo's own name.
3. Are they about the real world and referenced from more than one place? They belong in a shared domain collection in the general notes tree, and projects reference them by slug.
4. Otherwise the collection needs a visibility, retention, or access property that no existing repo can give it — only then does it get a dedicated repo, and only then is new sync plumbing justified.

Two constraints follow. A collection is inside exactly one git repository, and that repository is cloned on every machine that reads or writes it — the registry entry is not the record, the repo is; if you cannot name the repo a collection is meant to live in, the collection does not exist yet. And rule 2 says colocate with the *writer* rather than the reader precisely because visibility follows physical location: putting a collection in a repo that merely consumes it gives the data whatever exposure that consumer happens to have.

## Decision 2 — split the fail-open into the two cases it conflates

"A registered collection directory is missing" means two different things depending on how the collection was reached, and they get different handling:

- **Iterating all registered collections** (no collection was named — `folk list` across everything, a rebuild, a stats sweep). Stay tolerant: skip the missing collection and continue, because one absent collection must not break every other one on a machine that legitimately doesn't clone it. But *warn on stderr*, naming the collection and the path that isn't there. Tolerance means "keep going," not "say nothing." Stdout stays clean so the tolerant path remains pipeable.
- **A specific collection was explicitly requested** (`-C <name>`, or a directory passed directly). Hard-error, naming the collection and the resolved path, and exit nonzero. The caller asked about one collection by name; answering "it has no residents" when the truth is "that path does not exist" is a wrong answer, not a lenient one. This restores the crash-as-signal behavior for the case that actually needed it, without reintroducing the crash the tolerance was added to prevent.

The distinguishing input is available at the call site — whether a collection was named — so no new state or config is required to tell the cases apart; the scan just has to be told which mode it is running in rather than inferring leniency from the filesystem.

A missing directory and an unregistered name are still separate errors: an unknown collection name is a config error (the registry has no such entry), while a registered name with no directory is an integrity error (the registry is out of date, or the repo isn't cloned here). Say which one happened — the fixes are in different files.

## Decision 3 — `COLLECTION.json` doubles as the existence check

"The directory exists and is non-empty" is a weak test: an empty new collection passes for the wrong reason, and any unrelated directory that happens to sit at the registered path passes too. `collection-curation.md` introduces a small `COLLECTION.json` file in each collection's own root for a different purpose; its presence and parseability give the stronger positive test for free — *the registered path exists and declares itself a collection*.

The check is deliberately shallow, and stays that way:

- **Present and parseable** — the path is a collection. Proceed.
- **Absent, unreadable, or malformed** — treat exactly as `collection-curation.md` specifies for its own reading of the file (fail closed to the conservative default), and, in the tolerant iterate-all mode, warn. Do not hard-error on a missing marker alone: collections registered before this convention existed have no marker file and must keep working. The marker strengthens a positive answer; it is not a gate.

The point of reusing one file for both concerns is that a collection then has a single self-description to keep correct, rather than a curation file and a separate integrity file that can disagree. Nothing in this doc adds a key to it, and no code may enumerate collection names to decide any of the above — the marker is read from wherever the registry says the collection is, per invariant 7.

## Forward pointer — a verification command

The natural home for all of this as a single deliberate action is a read-only check (`folk doctor`, or `folk collections --verify`) that walks every registered collection and reports, per collection: the path exists; it declares itself with a `COLLECTION.json`; it is inside a git repository; and it has no uncommitted person files. Nothing about it touches an invariant — it writes nothing, derives nothing, and is stdlib-only — but it is a separate piece of work from the three decisions above and is specified here only so the shape is agreed before someone builds it. The decisions stand without it; the command is what turns them from conventions into something that gets checked.
