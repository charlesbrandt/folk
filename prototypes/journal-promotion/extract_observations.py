#!/usr/bin/env python3
"""Mechanically derive journal observation events from a Hermes session JSONL export.

Deterministic: same transcript in, same events out. No LLM involved — this is
the "observed" trust tier. Usage:

    python3 extract_observations.py <session.jsonl> [--user person:mara] > journal/YYYY-MM-observations.ndjson
"""
import argparse
import json
import re
import sys
from pathlib import Path

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
SNIPPET_LEN = 200


def text_of(content):
    if isinstance(content, list):
        content = " ".join(
            c.get("text", "") if isinstance(c, dict) else str(c) for c in content
        )
    return " ".join((content or "").split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--user", default="person:mara", help="folk id of the human participant")
    ap.add_argument("--agent", default="agent:hermes-main", help="folk id of the agent")
    args = ap.parse_args()

    path = Path(args.transcript)
    conv = "conv:" + path.stem  # e.g. conv:20260601_025800_7f3ac9e2
    events = []

    for idx, line in enumerate(open(path)):
        e = json.loads(line)
        role = e.get("role")
        ts = e.get("timestamp", "")
        if role == "session_meta":
            events.append({
                "ts": ts, "actor": "extract:v1", "kind": "session",
                "s": conv, "p": "opened_on", "o": "platform:" + (e.get("platform") or "unknown"),
                "session": conv,
                "note": f"model={e.get('model')}",
            })
            for who in (args.user, args.agent):
                events.append({
                    "ts": ts, "actor": "extract:v1", "kind": "observation",
                    "s": who, "p": "participated_in", "o": conv, "session": conv,
                })
            continue
        if role not in ("user", "assistant"):
            continue
        text = text_of(e.get("content"))
        if role == "assistant":
            text = " ".join(THINK_RE.sub("", text).split())
        if not text:
            continue
        speaker = args.user if role == "user" else args.agent
        events.append({
            "ts": ts, "actor": "extract:v1", "kind": "observation",
            "s": speaker, "p": "uttered", "o": f"msg:{path.stem}#{idx}",
            "session": conv,
            "note": text[:SNIPPET_LEN],
        })

    for ev in events:
        json.dump(ev, sys.stdout, ensure_ascii=False, sort_keys=True)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
