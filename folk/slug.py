"""Slug derivation: the one place a display name / free text becomes the
slug folk would derive for it.

Extracted out of graph.py (docs/design/unicode-slugs.md) so journal.py's
association-fallback slug derivation can share it without graph.py and
journal.py importing each other in a cycle (graph.py already imports
journal). Expected to be superseded by folk/identity.py's broader
normalization authority if docs/design/identity-resolution.md ever lands;
until then this is the single definition.
"""

import unicodedata


def slugify(name):
    """person display name / free text -> the slug folk would derive for it.

    Lowercase, then NFKD-fold to drop combining diacritics (Bjoerk -> bjork,
    cafe -> cafe) -- the same recipe docs/design/identity-resolution.md
    already uses for name matching, applied here too so an accented name
    produces a plain slug rather than a mangled one. A character that
    survives folding and still isn't a plain letter/digit is either a
    non-Latin script character with nothing to decompose (Japanese,
    Cyrillic, Greek, Arabic, ...) -- kept as-is, so those names still get a
    real, addressable slug instead of being stripped to near-nothing -- or
    genuine punctuation/whitespace/underscore, which collapses to a single
    "-" exactly as before.
    """
    folded = unicodedata.normalize("NFKD", name.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    pieces = []
    for ch in folded:
        if ch.isalnum():
            pieces.append(ch)
        elif pieces and pieces[-1] != "-":
            pieces.append("-")
    return "".join(pieces).strip("-")
