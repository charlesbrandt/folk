# `characters` + `authors` collections, and `folk graph`

**Status:** implemented (collection registry in `folk/config.py`, graph in `folk/graph.py`; covered by `tests/test_config.py` and `tests/test_graph.py`). Was roadmap item 2, the Phase 0 remainder. Supersedes `fictional-collection-and-graph.md` (2026-07-19, after discussion with the maintainer and the digger community-layer decisions).
**Context:** the wider persona-agent architecture design (Layer 0 gap, Phase 0); `~/repos/digger/docs/design/community-layer.md` ("Decisions (2026-07-19)" — domain collections, identity minting); `folk/config.py`

## Why

Phase 0's exit criterion — `folk show` returns a useful profile — is met for real people but not fictional ones, because no character collection is registered. And `folk graph` is the first projection view (Map View, Layer 5) plus a debugging aid for the journal work. Both are self-contained folk features that can proceed in parallel with the journal track.

## The collection decisions (settled with the maintainer, 2026-07-19)

**Collections are domains, and real vs. fictional is a domain boundary.** Per the digger doc's domain-collections decision (`musicians` now; `artists`, `actors` on the radar), the persona-agent architecture's "`fictional` collection" is realized as a `characters` collection, and creators get their own `authors` collection — **separate, never merged**, linked in the graph by `created_by` / `appears_in` edges ("cross-domain by predicate, not by schema"). This keeps domains from muddying each other, which is the maintainer's explicit priority.

Both directories already exist in the notes tree:

| Collection | Path | State |
|------------|------|-------|
| `characters` | `~/notes/fiction/characters/` | Already uses folk's `{initial}/{slug}/{slug}.md` layout (one resident: `c_c_sama`) |
| `authors` | `~/notes/fiction/authors/` | Six files (Eco, Vonnegut, PKD, Doctorow, Hofstadter, Gibson) in flat `{initial}/{slug}.md` layout — migrate each to `{initial}/{slug}/{slug}.md` so folk supports exactly one layout |

**Identity across collections** follows the digger doc's minting decision: one canonical person file, symlinks from secondary collections — collections are memberships, not identities. (An author who is also, say, a musician gets one file and a symlink, not two files.)

## Part 1: register and populate

1. Add both entries to `~/.config/folk/collections`. Collections stay pure config — nothing in code may enumerate collection names (CLAUDE.md invariant 7; the future `loci` collection depends on this).
   - Also register `musicians` → `~/notes/music/people/` (digger community-layer ask 1 — it was previously named in prose here but owned by no task). Registration is the one-line config change; note the tree is only *near* folk layout today (`{initial}/{slug}/` dirs exist, but inner filenames don't match `{slug}.md` — e.g. `a/jane-doe/jane-doe-journal.md`, `a/john_smith/john_smith.md` — and some slugs use underscores). The conformance migration of those files is digger's stage-1/Wave-4 work, not this task's; register the collection and let `folk list` simply find fewer residents until then.
2. Migrate the six author files to folk layout (git mv within the notes tree, preserving content).
3. Verify every command works against both collections: `list`, `show`, `link`, `tag`, `random`, `stats`, `context`, `index`.
4. Person-file conventions: same format as real people. Characters carry `appears_in` → their source `work:`; works carry `created_by` → their author; characters may carry media associations (theme music, portrait) that `folk render` later inherits into SOUL.md. Ordinary `## Associations` entries — no schema change.
5. **Seed set** (approved 2026-07-19; drawn from books actually read — see the notes tree's read-log and the book-genie skill for the ecosystem):
   - `authors`: Haruki Murakami.
   - `characters`: Toru Watanabe, Midori Kobayashi, Naoko, Reiko Ishida (Norwegian Wood); the Calcutec narrator, the Librarian (Hard-Boiled Wonderland and the End of the World); the boy, the Sheep Man (The Strange Library — the Sheep Man recurs across Murakami's world, note that in his file).
   - `work:` entities for the three novels, with `created_by` → Murakami and `appears_in` edges from each character.

## Journal roots (forward pointer)

Each registered collection directory may contain a `journal/` subdirectory; when present, it is a journal root scoped to that collection (spec: `journal-in-folk.md`). Nothing to build in this item — just don't create anything at these paths that would collide with that convention.

## Part 2: `folk graph`

Mermaid output over the triple index, terminal-first:

```
folk graph                          # active collection, association edges
folk graph --person <slug> [--depth N]   # ego graph, default depth 2
folk graph --context <tag>          # filter to people carrying a tag
```

- Output: a `graph TD` Mermaid document on stdout. Nodes labeled with display names; edges labeled with the relationship type (`mentor`, `created_by`, `appears_in`, …).
- **v1 scope: human-tier edges only** (person-file `## Associations`, i.e. what today's index already holds). A `--tier` flag to include observed/stated/interpreted edges comes after the journal lands in folk proper — design the edge-collection function so tiers are a filter parameter, not a rewrite.
- Default scope is the active collection; cross-collection edges (e.g. character → author's work) render when either endpoint is in scope, so domain separation holds without hiding deliberate links.
- Guardrail: at more than ~75 nodes, print a warning suggesting `--person` or `--context` instead of emitting an unreadable diagram.
- No rendering pipeline — Mermaid text is the deliverable. A `--html` self-contained output can come later if wanted.

## Exit criteria

- `folk context characters && folk show sheep-man` returns a useful profile: description, `appears_in` → The Strange Library, tags.
- `folk -C authors show haruki-murakami` shows his works; `folk graph --person haruki-murakami --depth 2` emits valid Mermaid reaching the characters through the works.
- The six migrated author files pass `folk show`; all existing commands pass against both collections; nothing in code enumerates collection names.
