#!/usr/bin/env python3
"""LLM promotion pass: scan a Hermes transcript, propose journal events.

The one LLM step in the pipeline. Emits the same event schema as the
hand-written reference (journal/2026-06-promotions.ndjson) so the two can be
compared. Output goes to llm/, NOT journal/ — LLM proposals only enter the
journal after review (or once the job is trusted).

    python3 promote_llm.py <session.jsonl> [--model gemma4:31b]
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

OLLAMA = "http://localhost:11434/v1/chat/completions"
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

PROMPT = """You are a memory promotion job for a personal agent system. Below is a conversation between Mara (the human, folk id person:mara) and her agent (folk id agent:hermes-main). Each message is numbered.

Your task: propose which durable facts from this conversation deserve to be remembered as knowledge-graph triples. Emit 5-10 events as NDJSON — one JSON object per line, no other text, no code fences.

Each event has exactly these fields:
- "kind": always "promotion"
- "evidence": "stated" (the fact was said directly — note MUST contain the exact quote, copied verbatim) or "interpreted" (your or the agent's reading of the conversation — note is a one-sentence summary)
- "level": "core" (ordinary durable fact) or "bedrock" (identity-level: childhood, defining moments, core values and beliefs — these are never auto-applied, only suggested to the human)
- "s": subject folk id (e.g. person:mara, agent:hermes-main)
- "p": predicate — USE ONE FROM THE VOCABULARY BELOW whenever one fits. Only if no listed predicate fits, coin a new lowercase snake_case predicate AND add "p_def": "<one-line definition>" to the event so it can be reviewed.
- "o": object folk id — slug with a type prefix from the vocabulary types, lowercase, hyphen-separated (e.g. topic:surfacing-art)
- "src": "msg:{stem}#N" where N is the number of the message the fact comes from
- "when": OPTIONAL but important — if the fact is anchored in time (a date, month, year, or "as of" moment mentioned in the conversation), record it here as YYYY, YYYY-MM, or YYYY-MM-DD. Dates are what make memories queryable later; do not drop them.
- "note": the evidence (see "evidence" above)

Predicate vocabulary (name: definition):
{vocab}

Object type prefixes: {types}

Rules: skip transient chit-chat and operational details that will be stale in a month (container restarts, config tweaks). Keep facts about people, their interests, values, history, and ongoing projects. Do not repeat the same fact twice.

Conversation (session conv:{stem}):

{dialogue}"""


def dialogue_of(path: Path):
    lines = []
    for idx, raw in enumerate(open(path)):
        e = json.loads(raw)
        role = e.get("role")
        if role not in ("user", "assistant"):
            continue
        content = e.get("content") or ""
        if isinstance(content, list):
            content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
        text = " ".join(THINK_RE.sub("", content).split())
        if not text:
            continue
        speaker = "Mara" if role == "user" else "Agent"
        lines.append(f"[{idx}] {speaker}: {text}")
    return "\n\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--model", default="gemma4:31b")
    args = ap.parse_args()

    path = Path(args.transcript)
    vocab = json.loads((Path(__file__).parent / "vocab.json").read_text())
    vocab_lines = "\n".join(f"- {k}: {v}" for k, v in vocab["predicates"].items() if k != "uttered")
    prompt = (PROMPT.replace("{stem}", path.stem)
              .replace("{vocab}", vocab_lines)
              .replace("{types}", ", ".join(t + ":" for t in vocab["types"]))
              .replace("{dialogue}", dialogue_of(path)))

    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps({
            "model": args.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=560) as resp:
        out = json.load(resp)["choices"][0]["message"]["content"]

    events, rejected = [], []
    for line in out.splitlines():
        line = line.strip().strip("`")
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
            assert e["kind"] == "promotion"
            assert e["evidence"] in ("stated", "interpreted")
            assert e["level"] in ("core", "bedrock")
            assert all(k in e for k in ("s", "p", "o", "src", "note"))
            events.append(e)
        except Exception:
            rejected.append(line)

    outdir = Path(__file__).parent / "llm"
    outdir.mkdir(exist_ok=True)
    outfile = outdir / f"{path.stem}.{args.model.replace(':', '-')}.ndjson"
    with open(outfile, "w") as f:
        for e in events:
            json.dump(e, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
    print(f"wrote {outfile}: {len(events)} valid events, {len(rejected)} rejected lines")
    for r in rejected:
        print("  rejected:", r[:100], file=sys.stderr)


if __name__ == "__main__":
    main()
