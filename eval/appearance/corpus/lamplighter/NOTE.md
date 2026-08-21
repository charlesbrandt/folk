# lamplighter — fixture provenance

An invented figure, not a real person and not drawn from any real person (CLAUDE.md's no-real-names rule, and the same reasoning applies with more force to a physical description than to a name). It exists to exercise every branch of `## Appearance` parsing in one file:

- five labeled lines, including a two-word label (`distinguishing marks`) — the case that rules out any "labels are single words" shortcut;
- one unlabeled prose line, which must land in `note` rather than being dropped;
- an `## Archetype`/`## Voice` pair, so the golden `description` and the golden `appearance_text` can be checked not to bleed into each other (appearance.md Decision 4 — they are siblings, and a regression that folds one into the other must fail a check, not pass quietly).

`prompts/` holds two fixture compiled prompts standing in for a renderer's output. They are hand-written, not produced by any pipeline: the propagation check only asks whether a compiled artifact still contains the figure's current brief, which needs a file with the brief in it and nothing else about how it got there.

- `01-frame.txt` — current: contains the brief verbatim, and passes.
- `02-stale-frame.txt` — deliberately stale: it carries an older brief (`hair: cropped close, dark at the temples`), the exact failure the propagation check exists to catch — a brief edited in folk, a prompt never recompiled, and a render that drifts for a reason that has nothing to do with the model. It is *expected* to fail propagation; `labels.json` records that expectation so the harness can assert the check fires rather than merely reporting green.

`labels.json` also holds the human likeness grades. There are two, both against `01-frame.txt`'s fingerprint, and they are the only judgment in the harness — nothing scores them, nothing derives a metric from them, and no model ever reads the image they refer to (appearance.md Decision 10). They are here so the *shape* of an attributed grade is pinned by a test at corpus size 1, which is the size this harness has to be useful at.
