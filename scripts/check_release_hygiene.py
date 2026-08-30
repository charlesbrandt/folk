#!/usr/bin/env python3
"""Release-hygiene check: scan tracked files for infra/identity fingerprints
that shouldn't ship in the public folk repo.

Run before every commit/push once this repo (or its public export) is
public-facing:

    python3 scripts/check_release_hygiene.py

Exits 1 and prints file:line for every match; exits 0 if clean. Not wired
up automatically -- if you want it to run on every commit, symlink it in:

    ln -s ../../scripts/check_release_hygiene.py .git/hooks/pre-commit

Some files are legitimately private-repo-only (real deployment history,
audit notes that never ship in the public export) and are exempt by
default -- see PRIVATE_ONLY below. Pass --include-private to check
everything, e.g. right before deciding what to carry into a public mirror.

Real given/family names (yours, family members', anyone's) are NOT
hardcoded here -- a public checker script that embeds the exact names
it's protecting would defeat its own purpose the moment it ships. Instead
they live in scripts/release_hygiene_names_local.py (gitignored, never
committed), a plain Python file defining LOCAL_PATTERNS as a list of
(label, compiled-regex) pairs in the same shape as PATTERNS below. Create
it once per machine:

    cat > scripts/release_hygiene_names_local.py <<'PY'
    import re
    LOCAL_PATTERNS = [
        ("real person name", re.compile(r"\bCharles\b")),
        ("real person name", re.compile(r"\bBrandt\b")),
        ("real person name", re.compile(r"\bTessa\b")),
    ]
    PY

Without that file, this script still catches infra fingerprints (IPs,
machine codenames, vault paths) but not real names -- keep the local file
current as new names turn up in the repo (this is exactly how the
2026-08-30 audit found `person:tessa-bent` sitting in a design doc).
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()

# Files allowed to carry real infra/ops detail because they never ship to
# the public export -- they document this private repo's own real
# deployment history, not the generic tool. Keep this list in sync with
# whatever actually gets excluded when building the public mirror.
PRIVATE_ONLY = {
    "docs/HANDOFF.md",
    "docs/design/history-scrub.md",
    "docs/design/collection-registry-integrity.md",
    "journal.md",
    "todo.md",
}

# Each entry: (label, compiled regex). Extend this as new fingerprints turn
# up -- keep patterns narrow enough to avoid flagging legitimate generic
# examples (e.g. match the real homelab's specific /24, not all of
# RFC1916 192.168.0.0/16, so a placeholder like 192.168.1.50 in a deploy
# example doesn't trip this).
PATTERNS = [
    ("real homelab subnet", re.compile(r"192\.168\.2\.\d{1,3}")),
    ("machine codename APU", re.compile(r"\bAPU\b")),
    ("machine codename elle", re.compile(r"\belle\b")),
    ("machine codename plex", re.compile(r"\bplex\b")),
    ("real repo path segment", re.compile(r"hermes-agent")),
    ("personal vault path", re.compile(r"~/combined\b")),
    ("container mount path", re.compile(r"/opt/repos\b")),
    ("real home directory", re.compile(r"/home/account\b")),
]

# Real given/family names load from a local, gitignored file if present --
# see the module docstring. Never hardcode real names in this file itself:
# this script ships in the public repo.
try:
    from release_hygiene_names_local import LOCAL_PATTERNS  # type: ignore
except ImportError:
    LOCAL_PATTERNS = []
PATTERNS = PATTERNS + LOCAL_PATTERNS


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [REPO_ROOT / p for p in out.stdout.splitlines() if p]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--include-private", action="store_true",
        help="also check files listed in PRIVATE_ONLY (use before curating a public export)",
    )
    args = ap.parse_args()

    hits = []
    for path in tracked_files():
        if path.resolve() == SELF:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if not args.include_private and rel in PRIVATE_ONLY:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    hits.append((rel, lineno, label, line.strip()[:120]))

    if hits:
        print(f"{len(hits)} release-hygiene hit(s):\n")
        for rel, lineno, label, snippet in hits:
            print(f"  {rel}:{lineno}  [{label}]  {snippet}")
        print("\nIf a file here is meant to be private-repo-only, add it to PRIVATE_ONLY.")
        print("If a pattern is over-broad, narrow it -- don't just delete the finding.")
        return 1

    scope = "all tracked files" if args.include_private else "public-facing files"
    print(f"clean -- no known fingerprints found in {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
