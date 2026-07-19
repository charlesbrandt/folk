"""Hermes session-file source adapter -- source #1 (session-promotion-job.md).

Normalizes a Hermes session JSONL export (e.g. ~/agent/sessions/) to the
ordered, speaker-attributed message shape every adapter must produce (see
folk/sources/__init__.py's contract docstring). Ported from
prototypes/journal-promotion/extract_observations.py's transcript parsing
(text_of/THINK_RE stripping, msg index = raw line number), generalized to
take the human/agent slugs and destination collection from per-profile job
config instead of hardcoding a specific person/agent slug (per
session-promotion-job.md's "Out of scope": design the extract step to take
actor as a parameter).

Config shape (one entry per Hermes profile, job config's "sources.hermes"):
    {
      "profiles": {
        "hermes-main": {
          "sessions_dir": "~/agent/sessions",
          "user_slug": "person:sam",
          "agent_slug": "agent:assistant-main",
          "collection": "personal",
          "counterparty": [],
          "locus": "locus:home"
        }
      }
    }

"locus" is optional (docs/design/loci.md Decision 2: "declared by surface,
not inferred" -- a profile bound to a Locus stamps every event it produces
with that locus, mechanically, never left to the promotion LLM to guess).
Omit it for a profile that isn't bound to any Locus.
"""

import json
import re
from pathlib import Path

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _text_of(content):
    if isinstance(content, list):
        content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return " ".join((content or "").split())


def discover(source_cfg):
    """One ref per *.jsonl session file across every configured profile's
    sessions_dir, sorted for determinism (never filesystem enumeration order).
    """
    refs = []
    for profile, pcfg in (source_cfg.get("profiles") or {}).items():
        sessions_dir = Path(pcfg["sessions_dir"]).expanduser()
        if not sessions_dir.is_dir():
            continue
        for f in sessions_dir.glob("*.jsonl"):
            refs.append({"profile": profile, "path": f, "session_id": f.stem})
    return sorted(refs, key=lambda r: str(r["path"]))


def mtime(ref):
    return ref["path"].stat().st_mtime


def load(ref, source_cfg, session_id, conv):
    profile = ref["profile"]
    pcfg = source_cfg["profiles"][profile]
    user_slug = pcfg["user_slug"]
    agent_slug = pcfg["agent_slug"]
    path = ref["path"]

    platform = "unknown"
    session_ts = ""
    messages = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        role = e.get("role")
        ts = e.get("timestamp", "")
        if role == "session_meta":
            platform = e.get("platform") or "unknown"
            session_ts = ts
            continue
        if role not in ("user", "assistant"):
            continue
        text = _text_of(e.get("content"))
        if role == "assistant":
            text = " ".join(THINK_RE.sub("", text).split())
        if not text:
            continue
        speaker = user_slug if role == "user" else agent_slug
        messages.append({"index": idx, "role": role, "speaker": speaker, "text": text, "ts": ts})

    return {
        "session_id": session_id, "conv": conv,
        "platform": platform, "profile": profile, "collection": pcfg["collection"],
        "user_slug": user_slug, "agent_slug": agent_slug,
        "counterparty": pcfg.get("counterparty") or [],
        "locus": pcfg.get("locus"),
        "mtime": path.stat().st_mtime,
        "session_ts": session_ts or (messages[0]["ts"] if messages else ""),
        "messages": messages,
    }
