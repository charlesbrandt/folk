# `## Locus Type` — an open classifier for what kind of Locus this is

**Status:** proposed and implemented this session (2026-08-30), not yet confirmed by the maintainer — flag any objection during review rather than treating this as settled.
**Context:** `docs/design/loci.md` (the Locus entity itself — "a markdown file with a `## Genius Loci` section, identified as `locus:<slug>`"); `docs/design/appearance.md` Decision 2 (the precedent this spec copies almost exactly — an open, human-authored, unenumerated label set that folk parses but never validates); `folk/person.py`'s `_parse_free_text` (the exact parsing primitive reused here, already used for `## Archetype`/`## Voice`); CLAUDE.md invariant 7 (collections are config, never code — the same discipline applied one layer down, to a field value rather than a collection name).

## Why

A Locus was designed for narrative places — a Scene's setting, a `## Genius Loci` section describing mood and rules. But a Locus, structurally, is nothing narrative-specific: it is a markdown file with a name, a description, and curated associations to people. That shape is exactly what an organization, a team, a department, a research center, or a shared resource also is, when the use case is tracking people and their connections across a large organization rather than a story's cast.

Rather than inventing a second entity type for "organizational unit," the more honest move is to recognize that Loci already are that entity type, and the only thing actually missing is a way to say *what kind* of Locus a given file is — a department is not a narrative place, but both are Loci in the existing sense of "a dedicated entity, curated by a human, that people are associated with." `## Locus Type` is that one field: `department`, `research-center`, `resource`, `grant`, `lab`, `narrative-place`, or anything else a human decides to write.

The temptation is to make this an enum, because "type" fields usually are one. That temptation is exactly what invariant 7 and `appearance.md` Decision 2 already ruled out for a structurally identical problem: the moment folk validates `department|lab|resource` in code, adding `cohort` or `consortium` or `working-group` becomes a code change and a release, and folk has appointed itself the owner of a taxonomy of organizations — a job nobody asked it to do and one it will always be behind on, since organizational vocabulary is exactly as open-ended as the appearance-label vocabulary already was.

## Decision 1 — a single free-text value, not a labeled-lines section

`## Locus Type` is one line of free text under the heading, the same shape as `## Archetype`/`## Voice` — not a labeled-lines section like `## Appearance` or `## Dates`, because a Locus has exactly one type, not an open set of labeled facts about itself:

```markdown
## Locus Type

department
```

Parsed with the exact primitive already used for Archetype and Voice: `person._parse_free_text(sections, "locus type")`. No new parsing code — one more call in the dict `show_person` already returns.

**Rejected — a labeled-lines convention like `## Appearance`.** A Locus Type is not a bag of independent facts (build, hair, dress); it is one classification. Reusing `_parse_appearance_lines` for a single scalar would invite multiple `- type: ...` lines with no defined merge behavior, solving a problem this field doesn't have.

## Decision 2 — folk never enumerates or validates Locus Type values

Exactly `appearance.md` Decision 2's reasoning, one level down: no code path checks a Locus Type value against a list of recognized types, and no type-name string (`department`, `lab`, `narrative-place`, or any other) appears anywhere in `folk/`. The conventional set the maintainer has in mind — `department`, `research-center`, `resource`, `grant`, `lab`, `narrative-place` — is documented here and in the `folk` skill as guidance for humans, never as schema folk enforces. Enforced by a grep test mirroring `tests/test_appearance.py::TestNoLabelNamesInFolkCode`.

## Decision 3 — available on both person and Locus files, for free, via the shared parsing path

`locus.show_locus()` calls `person.show_person(fpath)` directly and returns its dict unchanged (`docs/design/loci.md` established Locus files as "same markdown conventions as person files, reused from person.py"; `appearance.md` extended that to Appearance parsing on "both person files and Locus files"). Adding `locus_type` to `show_person`'s returned dict makes it available on `folk show locus:<slug>` with no Locus-specific code, at the cost of the key also existing — empty — on every ordinary person file's `show_person()` result. This is the same shape `appearance`/`appearance_checkpoints` already have: present and empty on files where it means nothing, present and meaningful on the files it's for. No conditional, no Locus-only code path in `person.py`.

## Decision 4 — `folk show locus:<slug>` displays it; `folk show person:<slug>` does not need a display line

`cli.py`'s `_show_locus` gains one display block, following the same `if value: print(...)` pattern already used for Tags/Appearance in that function:

```
Locus Type: department
```

placed right after `File:` and before `Tags:` — a Locus's type is closer to its identity than its tags are. `cmd_show` (the person-file path) is left unchanged: `locus_type` will simply always be `""` there, and `cmd_show` already omits every empty field the same way. There is no scenario where a person file legitimately has a Locus Type, so no display line is added to that path — adding one would be dead code exercised by nothing.

## Scope for v1

- `person.py`: `"locus_type": _parse_free_text(sections, "locus type")` added to `show_person`'s returned dict.
- `cli.py`'s `_show_locus`: one display block for `Locus Type`, mirroring the existing Tags/Appearance pattern.
- `tests/test_locus.py`: a Locus file with `## Locus Type` parses correctly via `show_locus`; a Locus file with no such section returns `""`, not an error or a missing key; a grep test asserting no locus-type value string appears in `folk/`.
- Documentation of the conventional (non-enforced) type vocabulary in this doc and the `folk` skill.

**Deferred, deliberately:**

- Any validation, enum, or fixed list of recognized Locus Types anywhere in code — ruled out permanently by Decision 2, not just deferred, but noted here for symmetry with the rest of this section.
- `folk graph`/`folk list` filtering or visual styling by Locus Type (e.g. `folk graph --locus-type department`, or drawing department Loci differently from narrative-place Loci). This would need new query/rendering logic that does not currently exist for any Locus field other than the existing `--locus <slug>` scoping, and building it now would be scope creep ahead of a real second consumer. A human wanting this today can already get it by tagging the Locus file (`## Tags`) with its type and filtering on that, which costs nothing new.
- Any change to `folk lookup`/`graph.find_person` to search or disambiguate by Locus Type — orthogonal to this spec, and `docs/design/bulk-import.md` covers the identity-resolution angle for bulk-created Loci separately.
- A `locus_type` predicate in the triple index or the journal schema. This is a person-file-shaped display field, exactly like Archetype/Voice, not a fact that gets promoted or indexed — no triple, no `vocab.json` entry, no event shape change.

## Exit criteria

- A Locus file with a `## Locus Type` section round-trips through `folk show locus:<slug>`, displaying `Locus Type: <value>`.
- A Locus file with no `## Locus Type` section shows nothing for that field (no empty header, no error) and `show_locus()["locus_type"] == ""`.
- An ordinary person file's `show_person()["locus_type"] == ""` and `cmd_show` prints nothing extra for it.
- No Locus Type value string (`department`, `research-center`, `resource`, `grant`, `lab`, `narrative-place`, or any other) appears anywhere in `folk/`'s source, enforced by a test.
- `python3 -m unittest discover tests` is green.
