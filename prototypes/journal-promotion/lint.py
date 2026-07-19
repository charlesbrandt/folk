#!/usr/bin/env python3
"""Deterministic lint for promotion event files. No LLM.

Checks every event against the transcript and vocab.json:
  HARD errors (exit 1) — schema violations, src pointing at a message that
  does not exist, evidence quotes that do not appear in the src message,
  duplicate (s,p,o), malformed slugs.
  PROPOSALS (exit 0) — predicates not in vocab.json. Not errors: they are
  the flexibility valve. They queue here for human review; accepting one
  means adding it to vocab.json with a definition.

    python3 lint.py <events.ndjson> <transcript.jsonl>
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
SLUG_RE = re.compile(r"^[a-z]+:[a-z0-9][a-z0-9-]*$")
SHINGLE = 5  # consecutive words that must match to verify a quote


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def message_texts(transcript: Path):
    msgs = {}
    for idx, line in enumerate(open(transcript)):
        e = json.loads(line)
        if e.get("role") not in ("user", "assistant"):
            continue
        c = e.get("content") or ""
        if isinstance(c, list):
            c = " ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in c)
        msgs[idx] = (e["role"], words(THINK_RE.sub("", c)))
    return msgs


# Who speaks as which transcript role. A stated fact about a subject must be
# sourced from a message that subject spoke — a verbatim quote inside someone
# else's message (e.g. the agent citing memoir material) is not a statement
# by the subject and must be downgraded to interpreted.
SPEAKER_ROLE = {"person:mara": "user", "agent:hermes-main": "assistant"}


def quote_found(note, msg_words):
    """Any SHINGLE consecutive words of the note appearing in order in the message."""
    nw = words(note)
    if len(nw) < SHINGLE:
        return True  # too short to verify meaningfully
    msg_join = " " + " ".join(msg_words) + " "
    return any(
        " " + " ".join(nw[i:i + SHINGLE]) + " " in msg_join
        for i in range(len(nw) - SHINGLE + 1)
    )


def main():
    events_path, transcript_path = Path(sys.argv[1]), Path(sys.argv[2])
    vocab = json.loads((HERE / "vocab.json").read_text())
    known_preds = set(vocab["predicates"])
    known_types = set(vocab["types"])
    msgs = message_texts(transcript_path)

    errors, proposals, seen = [], [], set()
    n = 0
    for lineno, line in enumerate(open(events_path), 1):
        if not line.strip():
            continue
        n += 1
        try:
            e = json.loads(line)
        except json.JSONDecodeError as ex:
            errors.append(f"L{lineno}: invalid JSON ({ex})")
            continue
        for field in ("kind", "s", "p", "o", "src", "note"):
            if field not in e:
                errors.append(f"L{lineno}: missing field {field!r}")
        if e.get("kind") == "promotion":
            if e.get("evidence") not in ("stated", "interpreted"):
                errors.append(f"L{lineno}: evidence must be stated|interpreted, got {e.get('evidence')!r}")
            if e.get("level") not in ("core", "bedrock"):
                errors.append(f"L{lineno}: level must be core|bedrock, got {e.get('level')!r}")
        for field in ("s", "o"):
            slug = e.get(field, "")
            if not SLUG_RE.match(slug):
                errors.append(f"L{lineno}: malformed slug {slug!r} (want type:lower-hyphen)")
            elif slug.split(":")[0] not in known_types:
                proposals.append(f"L{lineno}: new type {slug.split(':')[0]!r} in {slug!r}")
        pred = e.get("p", "")
        if pred and pred not in known_preds:
            proposals.append(f"L{lineno}: new predicate {pred!r}" + (f" — def: {e['p_def']}" if e.get("p_def") else " (no p_def given)"))
        key = (e.get("s"), e.get("p"), e.get("o"))
        if key in seen:
            errors.append(f"L{lineno}: duplicate triple {key}")
        seen.add(key)
        src = e.get("src", "")
        m = re.match(r"msg:.+#(\d+)$", src)
        if not m:
            errors.append(f"L{lineno}: unparseable src {src!r}")
            continue
        idx = int(m.group(1))
        if idx not in msgs:
            errors.append(f"L{lineno}: src points at message #{idx}, which has no user/assistant text")
            continue
        role, msg_words = msgs[idx]
        # Quote verification binds only evidence=stated: those events claim a
        # direct statement, so their note must contain it. Interpreted notes
        # are summaries; the src pointer alone is their audit trail.
        if e.get("evidence") == "stated":
            if not quote_found(e.get("note", ""), msg_words):
                errors.append(f"L{lineno}: stated evidence not found in msg #{idx} — no {SHINGLE}-word run of the note appears there")
            expected = SPEAKER_ROLE.get(e.get("s"))
            if expected and role != expected:
                errors.append(f"L{lineno}: stated fact about {e['s']} cites a {role} message (#{idx}) — the subject didn't say this here; downgrade to interpreted or re-source")

    print(f"{events_path.name}: {n} events — {len(errors)} errors, {len(proposals)} vocab proposals")
    for e in errors:
        print("  ERROR", e)
    for p in proposals:
        print("  PROPOSAL", p)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
