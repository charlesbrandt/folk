#!/usr/bin/env python3
"""Promotion evaluation harness -- docs/design/promotion-eval.md (Phase 2, task 7).

Scores `folk promote`'s output against human-labeled reference sets. No LLM
judge anywhere in the scoring path (that would reintroduce the same
unmeasurability this exists to remove) -- labels are hand-authored JSON.

Two modes share one scorer:
  - replay(): scores a *stored* NDJSON output against a corpus session's
    labels. Fully deterministic, no network -- this is what tests/ runs.
  - live():   runs the real promotion.process_session() against a configured
    Ollama model on a corpus session's transcript, scores the fresh output,
    and stores it as a new dated snapshot. Never part of the test suite.

Dev tool, not a `folk` subcommand (Decision 4) -- stdlib only (invariant 8).
"""

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from folk import journal
from folk import promotion
from folk.sources import hermes as hermes_source

CORPUS_DIR = REPO_ROOT / "eval" / "corpus"
BASELINE_PATH = REPO_ROOT / "eval" / "baseline.json"
EVAL_VOCAB_PATH = REPO_ROOT / "eval" / "vocab.json"


def load_eval_vocab():
    """The harness's own frozen vocab.json (eval/vocab.json), deliberately
    separate from ~/.config/folk/vocab.json -- scoring must be reproducible
    across machines and time, never silently drifting with someone's live,
    uncommitted config (invariant 7: this is committed config, like
    eval/baseline.json, not a lookup into the caller's environment).
    """
    data = json.loads(EVAL_VOCAB_PATH.read_text(encoding="utf-8"))
    data.setdefault("types", [])
    data.setdefault("predicates", {})
    data.setdefault("aliases", {})
    return data


SRC_LINT_MARKERS = (
    "stated evidence not found",
    "has no known utterance",
    "unparseable src",
    "the subject didn't say this here",
)
INDEX_LABEL_RE = re.compile(r"^#(\d+) ")


# ---------------------------------------------------------------- matching --

def _alias(slug, aliases):
    return aliases.get(slug, slug) if slug else slug


def triple_key(event, aliases):
    """(s, p, o) after alias canonicalization -- the same slug->canonical
    projection journal.replay() applies at rebuild (aliases apply to s/o
    only, never p; predicate drift is a real finding, not something this
    harness papers over).
    """
    return (_alias(event.get("s", ""), aliases), event.get("p", ""), _alias(event.get("o", ""), aliases))


def _matches_known_false(cand, false_entries, aliases):
    """A candidate violates a known_false entry when its (s, p, o) matches
    AND, if the entry pins an "evidence" value, the candidate's evidence
    matches too -- lets a label file flag a fact as false *at a given
    evidence tier* (e.g. asserted as directly stated) while the same
    triple at a lower tier is a legitimate reference fact. Coverage
    matching stays evidence-agnostic throughout (Decision 2); this is a
    narrower, opt-in refinement only for known_false.
    """
    ckey = triple_key(cand, aliases)
    for fe in false_entries:
        if triple_key(fe, aliases) != ckey:
            continue
        if "evidence" in fe and fe["evidence"] != cand.get("evidence"):
            continue
        return True
    return False


# ---------------------------------------------------------------- scoring --

def score_candidates(candidates, labels, vocab):
    """Coverage + faithfulness (triple-level) for one session's candidates
    against its label file. See _src_lint_stats for the stated-evidence
    faithfulness floor, folded into the faithfulness section separately.
    """
    aliases = (vocab or {}).get("aliases", {})
    reference = labels.get("reference", [])
    acceptable = labels.get("acceptable_extras", [])
    known_false = labels.get("known_false", [])

    ref_keys = {triple_key(r, aliases) for r in reference}
    acc_keys = {triple_key(a, aliases) for a in acceptable}

    cand_keys = [triple_key(c, aliases) for c in candidates]
    matched_ref = sorted({k for k in ref_keys if k in cand_keys})
    missed_ref = sorted(k for k in ref_keys if k not in cand_keys)
    coverage_ratio = (len(matched_ref) / len(ref_keys)) if ref_keys else 1.0

    violations, ungraded = [], []
    for c, key in zip(candidates, cand_keys):
        # known_false is checked first: it may pin an evidence tier (e.g. a
        # fact that's fine as interpreted but false if asserted as directly
        # stated), which is *more specific* than a plain (s, p, o) reference
        # match and must not be shadowed by one -- see _matches_known_false.
        if _matches_known_false(c, known_false, aliases):
            violations.append(key)
        elif key in ref_keys or key in acc_keys:
            continue
        else:
            ungraded.append(key)
    n = len(candidates)
    faithfulness_ratio = ((n - len(violations)) / n) if n else 1.0

    return {
        "coverage": {"ratio": coverage_ratio, "matched": matched_ref, "missed": missed_ref,
                     "n_reference": len(ref_keys)},
        "faithfulness": {"ratio": faithfulness_ratio, "violations": sorted(set(violations)),
                         "ungraded": sorted(set(ungraded)), "n_candidates": n},
    }


def _src_lint_stats(candidates, transcript_texts, vocab, known_object_slugs=None):
    """Fraction of "stated" candidates that pass journal's real lint (quote
    verification + speaker attribution) -- computed by running the actual
    lint used before every append, not a reimplementation. This is the
    "deterministic faithfulness floor" Decision 2 names for stated events.
    """
    stated_idx = {i for i, c in enumerate(candidates, 1) if c.get("evidence") == "stated"}
    if not stated_idx:
        return {"pass_rate": 1.0, "n": 0, "failures": []}

    errors, _proposals = journal.lint_events(candidates, transcript_texts=transcript_texts,
                                              vocab=vocab, known_object_slugs=known_object_slugs)
    failing = set()
    for err in errors:
        m = INDEX_LABEL_RE.match(err)
        if not m:
            continue
        idx = int(m.group(1))
        if idx in stated_idx and any(marker in err for marker in SRC_LINT_MARKERS):
            failing.add(idx)

    n = len(stated_idx)
    return {"pass_rate": (n - len(failing)) / n, "n": n,
            "failures": [candidates[i - 1] for i in sorted(failing)]}


def score_session(candidates, labels, vocab, transcript_texts=None, known_object_slugs=None):
    """Full report for one session: coverage, faithfulness (triple-level +
    src-lint floor). transcript_texts=None means this corpus item has no
    raw transcript on hand -- src_lint is reported as None (not applicable),
    never silently scored against an empty self-contained fallback.
    """
    report = score_candidates(candidates, labels, vocab)
    if transcript_texts is not None:
        report["faithfulness"]["src_lint"] = _src_lint_stats(
            candidates, transcript_texts, vocab, known_object_slugs)
    else:
        report["faithfulness"]["src_lint"] = None
    return report


# ------------------------------------------------------------ preservation --

def check_preservation(before_lines, after_lines):
    """Preservation holds iff every index line present before a session was
    added is still present, byte-identical, after (Decision 2: "verify
    every index record derivable without the new session is byte-identical
    before and after"). A pure subset check over two lists of already
    canonical (sort_keys, no wall clock) json lines.
    """
    after_set = set(after_lines)
    missing = [ln for ln in before_lines if ln not in after_set]
    return (len(missing) == 0), missing


def run_preservation(session, vocab, promote_call, collections, roots, tmp_dir,
                      quarantine_dir=None, model="eval", ollama_url="unused"):
    """Full pipeline over a temp copy of the index: rebuild BEFORE (existing
    collections/roots only), run process_session into a staging root layered
    on top, rebuild AFTER (collections/roots + staging), then compare.
    """
    tmp_dir = Path(tmp_dir)
    quarantine_dir = Path(quarantine_dir) if quarantine_dir else tmp_dir / "quarantine"
    index_before = tmp_dir / "before.ndjson"
    index_after = tmp_dir / "after.ndjson"
    staging_root = tmp_dir / "staging" / session["collection"]

    journal.rebuild_index(collections=collections, roots=roots, index_path=index_before)
    before_lines = index_before.read_text(encoding="utf-8").splitlines()

    outcome, counts, _wall, errors = promotion.process_session(
        session, vocab, index_before, staging_root, quarantine_dir,
        model, ollama_url, promote_call=promote_call)

    all_roots = list(roots) + [{"path": staging_root, "collection": session["collection"]}]
    journal.rebuild_index(collections=collections, roots=all_roots, index_path=index_after)
    after_lines = index_after.read_text(encoding="utf-8").splitlines()

    preserved, missing = check_preservation(before_lines, after_lines)
    return {"outcome": outcome, "counts": counts, "errors": errors,
            "preserved": preserved, "missing": missing}


# -------------------------------------------------------------- corpus io --

def _session_dir(session_id):
    d = CORPUS_DIR / session_id
    if not d.is_dir():
        raise FileNotFoundError(f"no corpus session {session_id!r} under {CORPUS_DIR}")
    return d


def load_labels(session_id):
    return json.loads((_session_dir(session_id) / "labels.json").read_text(encoding="utf-8"))


def load_meta(session_id):
    meta_path = _session_dir(session_id) / "meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def load_ndjson(path):
    events = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def _latest_output(session_id, filename=None):
    outputs_dir = _session_dir(session_id) / "outputs"
    if filename:
        return outputs_dir / filename
    candidates = sorted(outputs_dir.glob("*.ndjson"))
    if not candidates:
        raise FileNotFoundError(f"no stored outputs under {outputs_dir}")
    return candidates[-1]


def _transcript_texts_for(session_id, meta):
    transcript = meta.get("transcript")
    if not transcript:
        return None
    tpath = _session_dir(session_id) / transcript
    if not tpath.exists():
        return None
    return journal.build_transcript_texts(tpath, meta["user_slug"], meta["agent_slug"])


# ------------------------------------------------------------------ modes --

def replay_score(session_id, output_filename=None, vocab=None):
    """Score a stored output, no network. The regression gate lives in tests/."""
    labels = load_labels(session_id)
    meta = load_meta(session_id)
    vocab = vocab if vocab is not None else load_eval_vocab()
    output_path = _latest_output(session_id, output_filename)
    candidates = load_ndjson(output_path)
    transcript_texts = _transcript_texts_for(session_id, meta)

    report = score_session(candidates, labels, vocab, transcript_texts=transcript_texts)
    report.update({"session_id": session_id, "mode": "replay", "output_file": output_path.name})
    return report


def live_run(session_id, vocab=None, model=None, ollama_url=None, promote_call=None, tag=None):
    """Runs the real pipeline (extract -> promote -> lint) against a corpus
    session's transcript through promotion.process_session, scores the fresh
    candidates, and stores them as a new dated output snapshot. Touches
    Ollama unless promote_call is supplied -- never called from tests/.
    """
    meta = load_meta(session_id)
    if not meta.get("transcript"):
        raise ValueError(f"corpus session {session_id!r} has no transcript -- live mode needs one")
    session_dir = _session_dir(session_id)
    transcript_path = session_dir / meta["transcript"]
    labels = load_labels(session_id)
    vocab = vocab if vocab is not None else load_eval_vocab()
    model = model or promotion.DEFAULT_MODEL
    ollama_url = ollama_url or promotion.DEFAULT_OLLAMA_URL

    source_cfg = {"profiles": {"eval": {
        "sessions_dir": str(transcript_path.parent),
        "user_slug": meta["user_slug"], "agent_slug": meta["agent_slug"],
        "collection": meta.get("collection", "personal"),
    }}}
    ns_session_id = meta.get("session_id", session_id)
    conv = f"conv:{ns_session_id}"
    ref = {"profile": "eval", "path": transcript_path, "session_id": transcript_path.stem}
    session = hermes_source.load(ref, source_cfg, ns_session_id, conv)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        staging_root = tmp_path / "staging" / session["collection"]
        quarantine_dir = tmp_path / "quarantine"
        index_path = tmp_path / "index.ndjson"  # absent -> empty known-slug set, fine for eval

        outcome, counts, wall, errors = promotion.process_session(
            session, vocab, index_path, staging_root, quarantine_dir,
            model, ollama_url, promote_call=promote_call)

        staged = []
        for f in sorted(staging_root.glob("*.ndjson")) if staging_root.is_dir() else []:
            staged.extend(journal.read_segment(f))
        candidates = [e for e in staged if e.get("kind") == "promotion"]

    transcript_texts = journal.build_transcript_texts(transcript_path, meta["user_slug"], meta["agent_slug"])
    report = score_session(candidates, labels, vocab, transcript_texts=transcript_texts)
    report.update({"session_id": session_id, "mode": "live", "outcome": outcome,
                   "wall_seconds": wall, "counts": counts})

    date_tag = tag or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_model = model.replace("/", "_")
    out_path = session_dir / "outputs" / f"{date_tag}.{safe_model}.ndjson"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, sort_keys=True, ensure_ascii=False) + "\n")
    report["output_file"] = out_path.name
    return report


# --------------------------------------------------------------- baseline --

def load_baseline():
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _trim(report):
    return {
        "coverage": {"ratio": report["coverage"]["ratio"]},
        "faithfulness": {"ratio": report["faithfulness"]["ratio"]},
        "src_lint": ({"pass_rate": report["faithfulness"]["src_lint"]["pass_rate"]}
                     if report["faithfulness"].get("src_lint") else None),
    }


def aggregate(reports):
    def _mean(vals):
        vals = [v for v in vals if v is not None]
        return (sum(vals) / len(vals)) if vals else None
    return {
        "coverage": _mean(r["coverage"]["ratio"] for r in reports),
        "faithfulness": _mean(r["faithfulness"]["ratio"] for r in reports),
        "src_lint": _mean((r["faithfulness"].get("src_lint") or {}).get("pass_rate") for r in reports),
    }


def check_regression(reports, baseline):
    """No metric may decrease against the recorded baseline, per session
    (Decision 2) -- baseline.json is updated deliberately in a commit when a
    change legitimately moves the numbers, never auto-adjusted here.
    """
    problems = []
    base_sessions = (baseline or {}).get("sessions", {})
    for r in reports:
        sid = r["session_id"]
        base = base_sessions.get(sid)
        if not base:
            continue
        cur_cov = r["coverage"]["ratio"]
        prev_cov = (base.get("coverage") or {}).get("ratio")
        if prev_cov is not None and cur_cov < prev_cov:
            problems.append(f"{sid}: coverage dropped {prev_cov:.3f} -> {cur_cov:.3f}")

        cur_faith = r["faithfulness"]["ratio"]
        prev_faith = (base.get("faithfulness") or {}).get("ratio")
        if prev_faith is not None and cur_faith < prev_faith:
            problems.append(f"{sid}: faithfulness dropped {prev_faith:.3f} -> {cur_faith:.3f}")

        cur_src = (r["faithfulness"].get("src_lint") or {}).get("pass_rate")
        prev_src = (base.get("src_lint") or {}).get("pass_rate")
        if cur_src is not None and prev_src is not None and cur_src < prev_src:
            problems.append(f"{sid}: src_lint pass_rate dropped {prev_src:.3f} -> {cur_src:.3f}")
    return problems


# ------------------------------------------------------------------- cli --

def _print_report(r):
    print(f"== {r['session_id']} ({r['mode']}, {r['output_file']}) ==")
    cov = r["coverage"]
    print(f"  coverage:     {cov['ratio']:.3f}  ({len(cov['matched'])}/{cov['n_reference']} reference facts)")
    if cov["missed"]:
        print(f"    missed: {cov['missed']}")
    faith = r["faithfulness"]
    print(f"  faithfulness: {faith['ratio']:.3f}  ({faith['n_candidates']} candidates, "
          f"{len(faith['violations'])} violations, {len(faith['ungraded'])} ungraded)")
    if faith["violations"]:
        print(f"    violations: {faith['violations']}")
    if faith["ungraded"]:
        print(f"    ungraded (needs grading): {faith['ungraded']}")
    src = faith.get("src_lint")
    if src is None:
        print("  src_lint:     n/a (no transcript for this corpus item)")
    else:
        print(f"  src_lint:     {src['pass_rate']:.3f}  ({src['n']} stated candidates)")


def _all_session_ids():
    return sorted(d.name for d in CORPUS_DIR.iterdir() if d.is_dir())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Promotion evaluation harness (docs/design/promotion-eval.md)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_replay = sub.add_parser("replay", help="score stored outputs, no network")
    p_replay.add_argument("sessions", nargs="*", help="corpus session ids (default: all)")
    p_replay.add_argument("--output", help="specific output filename (single session only)")

    p_live = sub.add_parser("live", help="run the real pipeline against Ollama, score fresh output")
    p_live.add_argument("sessions", nargs="+")
    p_live.add_argument("--model")
    p_live.add_argument("--ollama-url")
    p_live.add_argument("--tag")

    p_baseline = sub.add_parser("update-baseline", help="record current replay-mode numbers as the baseline")
    p_baseline.add_argument("sessions", nargs="*")

    args = parser.parse_args(argv)

    if args.cmd == "replay":
        sessions = args.sessions or _all_session_ids()
        reports = [replay_score(sid, output_filename=args.output) for sid in sessions]
        for r in reports:
            _print_report(r)
        agg = aggregate(reports)
        print(f"\naggregate: coverage={agg['coverage']}, faithfulness={agg['faithfulness']}, "
              f"src_lint={agg['src_lint']}")
        problems = check_regression(reports, load_baseline())
        if problems:
            print("\nREGRESSIONS against eval/baseline.json:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        return 0

    if args.cmd == "live":
        for sid in args.sessions:
            r = live_run(sid, model=args.model, ollama_url=args.ollama_url, tag=args.tag)
            _print_report(r)
        return 0

    if args.cmd == "update-baseline":
        sessions = args.sessions or _all_session_ids()
        reports = [replay_score(sid) for sid in sessions]
        baseline = {"sessions": {r["session_id"]: _trim(r) for r in reports},
                    "aggregate": aggregate(reports)}
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline updated: {BASELINE_PATH}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
