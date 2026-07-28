"""folk agenda -- the deterministic backing for reminders (docs/design/
web-ui.md Decision 4, the dashboard's flagship "Home" view: "don't forget
the birthday"). Reads every person file's `## Dates` section (person.py's
`_parse_dates` -- Bedrock, human-curated) across the given collections,
rolls each recurring month-day date forward against an injected `now`, and
returns the next occurrence of every dated event within a look-ahead
window, soonest first.

No model call, no writes, no side effects -- `now` is always a caller-
supplied parameter, defaulting to the wall clock only at the CLI boundary
(folk/cli.py's cmd_agenda), never read internally here. That is the same
determinism contract journal.staleness and surface.surface already hold:
call upcoming() twice with a fixed `now` and the output is byte-identical,
which is what lets `folk agenda --json` feed a session-start prompt or a
dashboard panel without becoming a second source of truth for anything --
it is a pure read over `## Dates`, nothing it returns is written back
anywhere.
"""

from datetime import date, datetime

from . import person


def _next_occurrence(month_day, now_date):
    """Roll a recurring MM-DD forward to its next occurrence on/after
    now_date (this year if it hasn't passed yet, else next year). A Feb 29
    anniversary in a non-leap target year rolls to Mar 1 rather than
    raising -- there is no Feb 29 that year, and that's the same convention
    most calendar apps use for a leap-day date.
    """
    month, day = (int(x) for x in month_day.split("-"))
    for year in (now_date.year, now_date.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            if (month, day) == (2, 29):
                candidate = date(year, 3, 1)
            else:
                raise
        if candidate >= now_date:
            return candidate
    raise AssertionError(f"unreachable: {month_day!r} did not roll forward from {now_date}")


def upcoming(collection_dirs, within_days=30, now=None):
    """Return every dated event across every person file in
    `collection_dirs` whose next occurrence falls within `within_days` of
    `now`, soonest first, ties broken by person name ascending (stable,
    deterministic -- never filesystem or dict order). Each item:
    {"date": "YYYY-MM-DD" (the next occurrence), "days_until": int,
    "label": str, "person": display name, "person_id": "person:<slug>",
    "file": str}. Malformed `## Dates` entries were already dropped at
    parse time (person._parse_dates); a date string that still fails to
    roll forward (an invalid MM-DD that slipped past the regex, e.g.
    "13-40") is skipped here rather than raising, same tolerance as the
    rest of the parsing chain. `now` defaults to the wall clock only when
    the caller omits it -- pass a fixed `now` for reproducible output.
    """
    now = now if now is not None else datetime.now()
    now_date = now.date() if isinstance(now, datetime) else now

    items = []
    for collection_dir in collection_dirs:
        for slug, fpath in person._person_files(collection_dir):
            info = person.show_person(fpath)
            for d in info["dates"]:
                try:
                    occurrence = _next_occurrence(d["month_day"], now_date)
                except ValueError:
                    continue
                days_until = (occurrence - now_date).days
                if days_until > within_days:
                    continue
                items.append({
                    "date": occurrence.isoformat(),
                    "days_until": days_until,
                    "label": d["label"],
                    "person": info["name"],
                    "person_id": f"person:{slug}",
                    "file": str(fpath),
                })

    items.sort(key=lambda it: (it["date"], it["person"]))
    return items
