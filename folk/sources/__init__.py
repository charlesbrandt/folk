"""Transcript source adapters -- the pluggable front step from
session-promotion-job.md ("Transcript sources are pluggable"). Hermes is
source #1 (hermes.py); an OpenWebUI adapter is designed but not built here
-- it should slot in as one more module registered in ADAPTERS plus a
"sources" config block, with no changes to folk/promotion.py.

Contract each adapter module implements:

  discover(source_cfg) -> list of opaque ref objects. adapter-specific
      shape, but each ref must carry a raw, adapter-local session id at
      ref["session_id"] -- session_id_for() below namespaces it.

  mtime(ref) -> float, last-modified time of the underlying source, for the
      job's mtime-quiescence check (session-promotion-job.md "Trigger and
      idempotency": process sessions quiet for more than an hour).

  load(ref, source_cfg, session_id, conv) -> a normalized session dict:
      {
        "session_id": session_id, "conv": conv,
        "platform": str, "profile": str, "collection": str,
        "user_slug": str, "agent_slug": str, "counterparty": [str, ...],
        "locus": str | None,
        "mtime": float, "session_ts": str,
        "messages": [{"index": int, "role": "user"|"assistant",
                       "speaker": str, "text": str, "ts": str}, ...],
      }
      "locus" (loci.md Decision 2: "declared by surface, not inferred") is
      the locus:<slug> a source profile is bound to, or None/absent when
      it isn't bound to one -- promotion.extract() stamps it on every event
      the session produces, mechanically, never left to the promotion LLM.
      A message's "index" is the transcript's own stable 0-based record
      index (folk-proper: raw line number in the source file, including
      lines the adapter otherwise skips) -- the msg:<session-id>#<index>
      pointer contract (journal-schema.md) depends on it never shifting,
      so adapters must carry it through rather than renumbering.

Everything downstream (extract, promote, lint, append in folk/promotion.py)
consumes only this normalized shape and never imports an adapter module
directly.
"""

from . import hermes

ADAPTERS = {"hermes": hermes}


def get(name):
    try:
        return ADAPTERS[name]
    except KeyError:
        raise ValueError(f"no registered transcript source adapter {name!r}")


def session_id_for(source_name, ref):
    """Namespace a source's raw session id so sources never collide
    (session-promotion-job.md: conv:hermes-..., conv:owui-...).
    """
    return f"{source_name}-{ref['session_id']}"
