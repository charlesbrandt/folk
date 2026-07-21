"""Locus file operations (docs/design/loci.md).

A Locus is a markdown file with a ## Genius Loci section, identified as
locus:<slug> -- one more entity type prefix alongside person:, work:,
topic:. Same markdown conventions as person files (## Associations,
## Tags), reused from person.py, but a flatter directory layout:
{loci-root}/{slug}/{slug}.md, no {initial} subdirectory -- a loci root is
already scoped by registration (config.load_loci_roots(), Decision 4)
rather than holding an entire collection's roster.
"""

from pathlib import Path

from .person import _read_heading, show_person


def _locus_files(loci_root_dir):
    """Yield (slug, filepath) for every Locus file under one registered loci root."""
    loci_root_dir = Path(loci_root_dir)
    if not loci_root_dir.is_dir():
        return
    for slug_dir in sorted(loci_root_dir.iterdir()):
        if not slug_dir.is_dir():
            continue
        fpath = slug_dir / f"{slug_dir.name}.md"
        if fpath.is_file():
            yield slug_dir.name, fpath


def find_locus_file(loci_roots, slug):
    """Search every registered loci root for locus:<slug>. Returns Path or None."""
    for root in loci_roots:
        for s, fpath in _locus_files(root["path"]):
            if s == slug:
                return fpath
    return None


def list_loci(loci_roots):
    """Return list of (display_name, filepath) across every registered loci root."""
    results = []
    for root in loci_roots:
        for _slug, fpath in _locus_files(root["path"]):
            results.append((_read_heading(fpath), fpath))
    return results


def show_locus(fpath):
    """Structured view of a Locus file -- same shape as person.show_person
    (## Associations/## Tags/## Genius Loci are all just markdown sections).
    """
    return show_person(fpath)
