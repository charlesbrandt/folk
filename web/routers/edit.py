"""Person-file write flow (docs/design/web-ui.md Decision 1 write path #1,
Decision 2c's inline edit): "Inline edit on any Bedrock section -> staged
diff -> commit."

POST .../edit/preview computes a diff without writing anything.
POST .../edit/commit re-derives the identical diff server-side (never trusts
a diff the client sent back), writes the file, commits it -- scoped to
exactly the one file changed, in the git repo that actually owns it (which
may not be the collection directory itself -- see _repo_root_for) -- and
triggers folk's index rebuild (invariant 2: nothing else may write the
index).

This generalizes review.preview_bedrock_edit/apply_bedrock_edit's
diff-then-confirm pattern -- same shape (difflib.unified_diff over
person._build_content()'s before/after), same "typist, not author" rule --
to arbitrary section text instead of one templated line. review.py's own
preview/apply pair is untouched and still owns the review-queue's three
templated shapes (tag/association/defining-moment lines from an accepted
promotion); this module is the new thing web-ui.md Part B asks for, a person
editing their own Bedrock sections freely.
"""
import difflib
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from folk import config, person, triples

router = APIRouter()

# Allowlist of Bedrock sections an inline edit may target (web-ui.md Part B
# step 1). "__main__" is person._parse_sections' key for the bio -- the body
# text before the first ## heading (including the file's own "# Name" H1
# line, which _build_content does *not* regenerate the way it regenerates
# "## Section" headers from a section's key -- see _replace_main below for
# why that makes "__main__" special-cased). Every other entry here is one of
# _parse_sections' lower-cased "## X" keys.
ALLOWED_SECTIONS = frozenset({
    "__main__", "tags", "associations", "media", "dates",
    "defining moments", "archetype", "voice", "appearance",
})


class EditBody(BaseModel):
    collection: str
    section: str
    # Raw new text for the section. For every section except "__main__" this
    # is used verbatim as the new lines (content.split("\n")) -- person.py's
    # _build_content re-adds the "## Section" heading from the section key,
    # so section bodies never carry their own heading line. "__main__" is the
    # one exception: it IS the file's H1 heading line plus the bio body, so
    # `content` there is treated as bio body text only (matching what
    # person.show_person's "bio" field already returns to a GET caller) and
    # the existing H1 line is preserved automatically -- see _replace_main.
    content: str


def _resolve_person_file(slug: str, collection: str):
    """Resolve slug + collection name to a person file path, exactly the way
    web/routers/people.py's get_person() already does -- never construct a
    path from client input directly. Raises HTTPException (404/400) on any
    failure; never falls back to guessing a path."""
    try:
        collection_dir, coll_name = config.resolve_collection_dir(collection_name=collection)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    fpath = person._find_person_file(collection_dir, slug)
    if not fpath:
        raise HTTPException(status_code=404, detail=f"'{slug}' not found in collection '{collection}'")

    # Defense in depth beyond "only ever resolved through folk's own lookup":
    # confirm the file folk's own lookup handed back is actually inside the
    # collection directory folk's own config resolved. person._find_person_file
    # only ever walks real directory entries under collection_dir (never
    # builds a path from the slug string), so this should be unreachable --
    # but a security-sensitive write path earns the redundant check anyway.
    resolved_fpath = fpath.resolve()
    resolved_coll_dir = collection_dir.resolve()
    if resolved_coll_dir not in resolved_fpath.parents:
        raise HTTPException(status_code=400, detail="resolved person file escapes its collection directory")

    return resolved_fpath, coll_name


def _replace_main(existing_main_lines, new_bio_text):
    """Rebuild the "__main__" section's lines: keep the file's own "# Name"
    H1 heading line(s) exactly as they are (see ALLOWED_SECTIONS' docstring
    for why -- unlike every other section, __main__'s heading is literal
    content, not something _build_content regenerates), and replace only the
    bio body with new_bio_text. Falls back to no heading if the file
    genuinely has none (an already-malformed file) rather than fabricating
    one."""
    heading_lines = [l for l in existing_main_lines if person.HEADING_RE.match(l)]
    body_lines = new_bio_text.split("\n")
    if heading_lines:
        return heading_lines + [""] + body_lines
    return body_lines


def _compute_diff(fpath: Path, section: str, content: str):
    """Returns (before, after, diff_text). Pure computation, no write --
    review.preview_bedrock_edit's exact shape (difflib.unified_diff over
    _build_content()'s before/after), generalized to accept arbitrary new
    section text instead of one templated line."""
    before = fpath.read_text(encoding="utf-8", errors="replace")
    sections = person._parse_sections(before)
    new_sections = dict(sections)
    if section == "__main__":
        new_sections["__main__"] = _replace_main(sections.get("__main__", []), content)
    else:
        new_sections[section] = content.split("\n")
    after = person._build_content(new_sections)
    diff = "\n".join(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=str(fpath), tofile=str(fpath), lineterm=""))
    return before, after, diff


def _validate_section(section: str):
    if section not in ALLOWED_SECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown section {section!r}; allowed: {sorted(ALLOWED_SECTIONS)}",
        )


@router.post("/people/{slug}/edit/preview")
def preview_edit(slug: str, body: EditBody):
    _validate_section(body.section)
    fpath, _coll_name = _resolve_person_file(slug, body.collection)
    _before, _after, diff = _compute_diff(fpath, body.section, body.content)
    return {"diff": diff}


def _repo_root_for(fpath: Path) -> Path:
    """The git repo root that actually owns fpath -- NOT necessarily the
    collection directory (docs/design/web-ui.md's "Git commit" section: the
    characters/authors collections live under a media/ subdirectory of a
    much larger notes repo). `git -C <dir> rev-parse --show-toplevel` is
    correct for nested/mixed layouts; fpath.parent is itself server-resolved
    (never client-supplied), so this subprocess call's argument is safe by
    construction."""
    result = subprocess.run(
        ["git", "-C", str(fpath.parent), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"person file is not inside a git repo: {result.stderr.strip()}",
        )
    return Path(result.stdout.strip())


@router.post("/people/{slug}/edit/commit")
def commit_edit(slug: str, body: EditBody):
    _validate_section(body.section)
    fpath, _coll_name = _resolve_person_file(slug, body.collection)

    # Never trust a diff the client sent back -- recompute it fresh from the
    # current file state, the same way a checkout never trusts a client-sent
    # price. If preview and commit are called back to back with no other
    # writer touching the file in between, this is byte-identical to what
    # /preview returned; if the file changed underneath (another writer, or
    # a stale UI), the diff (and therefore what gets written) reflects
    # reality, not a stale client view.
    before, after, diff = _compute_diff(fpath, body.section, body.content)

    if not diff:
        # Mirrors review.preview_bedrock_edit's "already present, nothing to
        # add" no-op case: nothing to write, nothing to commit.
        return {"committed": False, "reason": "no changes"}

    repo_root = _repo_root_for(fpath)
    try:
        rel_path = fpath.relative_to(repo_root)
    except ValueError:
        raise HTTPException(
            status_code=500,
            detail=f"person file {fpath} is not inside its own git repo root {repo_root}",
        )

    fpath.write_text(after, encoding="utf-8")

    # If anything from here on fails, undo the working-tree write (and
    # unstage, best-effort, in case `git add` had already succeeded before a
    # later step failed) rather than leave a half-applied edit sitting in
    # someone else's git repo with no commit and no explanation. The
    # unstage is best-effort because its own failure must never mask the
    # real error being reported.
    def _rollback():
        fpath.write_text(before, encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repo_root), "reset", "--", str(rel_path)],
            capture_output=True, text=True,
        )

    add = subprocess.run(
        ["git", "-C", str(repo_root), "add", "--", str(rel_path)],
        capture_output=True, text=True,
    )
    if add.returncode != 0:
        _rollback()
        raise HTTPException(status_code=500, detail=f"git add failed: {add.stderr.strip()}")

    # Defense in depth, not the primary safety mechanism (the pathspec-scoped
    # add/commit below is): confirm only the one file we just wrote shows up
    # as modified for that pathspec before committing. Surprising here would
    # mean something unexpected is going on -- error out rather than commit
    # blindly.
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--", str(rel_path)],
        capture_output=True, text=True,
    )
    status_lines = [l for l in status.stdout.splitlines() if l.strip()]
    if len(status_lines) != 1:
        _rollback()
        raise HTTPException(
            status_code=500,
            detail=f"unexpected git status for {rel_path} -- refusing to commit: {status.stdout!r}",
        )

    message = f"folk web: edit {body.section} on {fpath.stem}"
    commit = subprocess.run(
        ["git", "-C", str(repo_root), "commit", "-m", message, "--", str(rel_path)],
        capture_output=True, text=True,
    )
    if commit.returncode != 0:
        _rollback()
        raise HTTPException(
            status_code=500,
            detail=f"git commit failed: {commit.stderr.strip() or commit.stdout.strip()}",
        )

    rev_parse = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    if rev_parse.returncode != 0:
        # The commit itself succeeded -- this is only a failure to report its
        # sha, not a reason to roll back a commit that already landed.
        raise HTTPException(status_code=500, detail=f"git rev-parse failed after commit: {rev_parse.stderr.strip()}")
    sha = rev_parse.stdout.strip()

    # The only thing that ever writes ~/.folk/triples.ndjson (invariant 2) --
    # called exactly once, after the commit succeeded, never before.
    triples.index_rebuild()

    return {"committed": True, "commit_sha": sha, "diff": diff}
