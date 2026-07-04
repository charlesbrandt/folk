"""Context report generation.

Reads .folk-context.json from a person directory and assembles
a structured report for rapid orientation in an AI session.

Config example (placed in the person directory):

    {
      "version": 1,
      "sections": [
        {"file": "person-name.md", "label": "Person File"},
        {"file": "prompts.md", "select": "latest", "label": "System State"},
        {"file": "conversations.json", "select": "last", "count": 15,
         "label": "Recent Messages", "format": "conversation"}
      ]
    }
"""

import json
import re
from pathlib import Path

DATE_HEADER = re.compile(r"^# \d{4}\.\d{2}\.\d{2}")


def load_config(person_dir):
    """Load .folk-context.json from *person_dir*, or None."""
    config_path = person_dir / ".folk-context.json"
    if not config_path.exists():
        return None
    return json.loads(config_path.read_text())


def generate_report(person_dir):
    """Return list of (label, content) pairs from a person's .folk-context.json."""
    config = load_config(person_dir)
    if not config:
        return None

    sections = []
    for sec in config.get("sections", []):
        label = sec.get("label", sec["file"])
        fpath = person_dir / sec["file"]
        if not fpath.exists():
            sections.append((label, f"(file not found: {sec['file']})"))
            continue

        select = sec.get("select", "all")
        if select == "latest":
            content = _extract_latest_block(fpath)
        elif select == "last":
            content = _extract_last(fpath, sec.get("count", 10), sec.get("format"))
        else:
            content = fpath.read_text(encoding="utf-8", errors="replace")

        sections.append((label, content))

    return sections


def _extract_latest_block(fpath):
    """Return the first date-delimited block (most recent entry in a journal-style file)."""
    text = fpath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    first = None
    for i, line in enumerate(lines):
        if DATE_HEADER.match(line.strip()):
            first = i
            break
    if first is None:
        return text

    second = len(lines)
    for i in range(first + 1, len(lines)):
        if DATE_HEADER.match(lines[i].strip()):
            second = i
            break

    return "\n".join(lines[first + 1:second]).strip()


def _extract_last(fpath, count, fmt=None):
    """Return the last *count* items from a JSON array, optionally formatted."""
    data = json.loads(fpath.read_text())
    if not isinstance(data, list):
        return json.dumps(data, indent=2)

    items = data[-count:]

    if fmt == "conversation":
        return _format_conversation(items)
    else:
        return "\n".join(json.dumps(item, indent=2) for item in items)


def _format_conversation(items):
    """Format message objects as readable conversation lines."""
    parts = []
    for item in items:
        sender = item.get("sender", "?")
        ts = item.get("timestamp", "")
        msg = item.get("message", "")
        meta = []
        if ts:
            meta.append(f"[{ts}]")
        tip = item.get("metadata", {}).get("tip", "")
        if tip:
            meta.append(f"[Tip: {tip}]")
        meta_str = " ".join(meta)

        parts.append(f"{sender}  {meta_str}" if meta_str else sender)

        reply = item.get("reply_context")
        if reply:
            quote = reply.get("quote", "")[:60]
            parts.append(f"  (Replying to: {quote})")

        if msg:
            for line in msg.splitlines():
                parts.append(f"  {line}")

        parts.append("")

    return "\n".join(parts)
