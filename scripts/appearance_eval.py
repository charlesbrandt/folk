#!/usr/bin/env python3
"""Appearance evaluation harness -- docs/design/appearance.md (Decision 10).

Scores what is deterministically checkable about a figure's appearance brief,
and refuses to score what isn't.

**No image is ever opened, and no model is ever called.** The tempting
shortcut -- hand the render and the brief to a vision model, ask "does this
match" -- is exactly the move promotion-eval.md Decision 1 rules out, for the
same reason: a model grading a model reintroduces the unmeasurability the
harness exists to remove. Whether a render *looks like* the figure is a human
grade in a corpus label file, attributed to the fingerprint of the brief that
produced it, and this runner only reports those grades alongside its own
numbers -- it never derives a metric from them.

The four checks:

  determinism  Compiling a fixture twice yields byte-identical output. The
               same bar every other folk output holds.
  stability    The compiled brief matches its golden snapshot, so a change to
               the flattening (a separator, an ordering) is a diff in a commit
               rather than a mystery in a render three weeks later.
  propagation  Every compiled prompt still contains the figure's *current*
               brief. This is the check most likely to catch a real bug: a
               brief edited in folk, a prompt never recompiled, a render that
               drifts for a boring reason.
  coverage     Are the labels a consumer reads actually present? Reported per
               figure, and a *finding, never a failure* -- most people in most
               collections have no reason to carry a physical description at
               all, so a missing label is information, not a broken build.

Dev tool, not a `folk` subcommand -- user-facing surface area is deliberately
zero (promotion-eval.md Decision 4, same shape). Stdlib only (invariant 8).
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from folk import person

EVAL_DIR = REPO_ROOT / "eval" / "appearance"
CORPUS_DIR = EVAL_DIR / "corpus"
CONSUMERS_PATH = EVAL_DIR / "consumers.json"

# Checks that gate; coverage deliberately does not (see module docstring).
GATING_CHECKS = ("determinism", "stability", "propagation")


def load_consumers():
    """The frozen consumer config -- which labels each consumer reads.

    Committed config, not a lookup into a live consumer's own configuration,
    so a coverage number is reproducible across machines and time (the same
    reasoning eval/vocab.json is frozen for). This file is also the only
    place in the repo where label names are written down: folk's source
    contains none (appearance.md Decision 2).
    """
    data = json.loads(CONSUMERS_PATH.read_text(encoding="utf-8"))
    return data.get("consumers", {})


def corpus_figures(name=None):
    """(slug, dir) for each corpus figure, sorted. `name` selects one."""
    if not CORPUS_DIR.is_dir():
        return []
    found = []
    for entry in sorted(CORPUS_DIR.iterdir()):
        if not entry.is_dir() or not (entry / "person.md").is_file():
            continue
        if name and entry.name != name:
            continue
        found.append((entry.name, entry))
    return found


def compile_brief(person_path):
    """The figure's brief, as folk hands it to a consumer.

    Deliberately routed through folk's own person.appearance_text rather than
    reimplemented here: a harness that flattens the brief its own way would
    pass while the thing it is supposed to be testing was broken.
    """
    info = person.show_person(person_path)
    appearance = info["appearance"]
    return {
        "labels": appearance["labels"],
        "note": appearance["note"],
        "appearance_text": person.appearance_text(appearance),
        "appearance_fingerprint": person.appearance_fingerprint(appearance),
    }


def _load_labels(figure_dir):
    path = figure_dir / "labels.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def check_determinism(person_path):
    """Compile twice; the two results must be identical."""
    first = compile_brief(person_path)
    second = compile_brief(person_path)
    ok = json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    return {"ok": ok, "detail": "" if ok else "two compiles of unchanged input differed"}


def check_stability(figure_dir, compiled):
    """The compiled brief must match its golden snapshot."""
    golden_path = figure_dir / "expected.json"
    if not golden_path.is_file():
        return {
            "ok": False,
            "detail": f"no golden snapshot ({golden_path.name}); run `update-golden` to record one",
        }
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    diffs = []
    for key in ("appearance_text", "appearance_fingerprint"):
        if golden.get(key) != compiled[key]:
            diffs.append(f"{key}: golden {golden.get(key)!r} != current {compiled[key]!r}")
    if golden.get("labels") != compiled["labels"]:
        diffs.append("labels differ from golden")
    return {"ok": not diffs, "detail": "; ".join(diffs)}


def check_propagation(figure_dir, compiled, labels):
    """Every compiled prompt must contain the figure's current brief.

    A prompt listed in labels.json's `expected_stale_prompts` inverts the
    assertion: it is a planted failure, and the check fails if it *passes* --
    otherwise a propagation check that silently stopped working would look
    exactly like a clean run.
    """
    prompts_dir = figure_dir / "prompts"
    if not prompts_dir.is_dir():
        return {"ok": True, "detail": "no prompts to check", "stale": [], "unexpectedly_current": []}

    brief = compiled["appearance_text"]
    expected_stale = set(labels.get("expected_stale_prompts") or [])
    stale, unexpectedly_current = [], []
    for prompt_path in sorted(prompts_dir.iterdir()):
        if not prompt_path.is_file():
            continue
        contains = brief and brief in prompt_path.read_text(encoding="utf-8")
        if prompt_path.name in expected_stale:
            if contains:
                unexpectedly_current.append(prompt_path.name)
        elif not contains:
            stale.append(prompt_path.name)

    detail = []
    if stale:
        detail.append("stale (brief edited, prompt never recompiled): " + ", ".join(stale))
    if unexpectedly_current:
        detail.append(
            "planted-stale prompt now contains the current brief -- the check "
            "itself may be broken: " + ", ".join(unexpectedly_current))
    return {
        "ok": not stale and not unexpectedly_current,
        "detail": "; ".join(detail),
        "stale": stale,
        "unexpectedly_current": unexpectedly_current,
    }


def check_coverage(compiled, consumers):
    """Which consumer-read labels this figure carries. A finding, not a gate."""
    present = {item["label"] for item in compiled["labels"]}
    per_consumer = {}
    for name, cfg in sorted(consumers.items()):
        required = list(cfg.get("required_labels") or [])
        missing = [label for label in required if label not in present]
        per_consumer[name] = {
            "required": len(required),
            "present": len(required) - len(missing),
            "missing": missing,
        }
    return per_consumer


def score_figure(slug, figure_dir, consumers):
    person_path = figure_dir / "person.md"
    compiled = compile_brief(person_path)
    labels = _load_labels(figure_dir)
    return {
        "figure": slug,
        "fingerprint": compiled["appearance_fingerprint"],
        "determinism": check_determinism(person_path),
        "stability": check_stability(figure_dir, compiled),
        "propagation": check_propagation(figure_dir, compiled, labels),
        "coverage": check_coverage(compiled, consumers),
        "likeness_grades": labels.get("likeness_grades") or [],
    }


def score(name=None):
    """Score the whole corpus (or one figure). Pure: no writes, no network."""
    consumers = load_consumers()
    return [score_figure(slug, d, consumers) for slug, d in corpus_figures(name)]


def _print_report(reports):
    failures = 0
    for r in reports:
        print(f"{r['figure']}  (brief {r['fingerprint'] or '-'})")
        for check in GATING_CHECKS:
            result = r[check]
            mark = "ok  " if result["ok"] else "FAIL"
            line = f"  {mark} {check}"
            if result["detail"]:
                line += f" -- {result['detail']}"
            print(line)
            if not result["ok"]:
                failures += 1

        for consumer, cov in r["coverage"].items():
            note = f"  --  coverage[{consumer}]: {cov['present']}/{cov['required']} labels"
            if cov["missing"]:
                note += f" (missing: {', '.join(cov['missing'])})"
            print(note)

        grades = r["likeness_grades"]
        if grades:
            counts = {}
            stale_attribution = 0
            for g in grades:
                counts[g.get("grade", "?")] = counts.get(g.get("grade", "?"), 0) + 1
                if g.get("brief_fingerprint") != r["fingerprint"]:
                    stale_attribution += 1
            summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
            print(f"  --  likeness grades (human, unscored): {summary}")
            if stale_attribution:
                print(f"  --  {stale_attribution} grade(s) attributed to an older brief "
                      "-- they describe a render the current brief would not produce")
        print()

    print(f"{len(reports)} figure(s), {failures} gating failure(s)")
    print("coverage and likeness grades are findings, never gates")
    return failures


def cmd_run(args):
    reports = score(args.figure)
    if not reports:
        print(f"no corpus figures found under {CORPUS_DIR}", file=sys.stderr)
        return 1
    return 1 if _print_report(reports) else 0


def cmd_update_golden(args):
    """Record the current compiled brief as each figure's golden snapshot.

    Deliberate and explicit, like promotion-eval's update-baseline: a golden
    that moves on its own is not a golden. Run it, then read the diff in the
    commit -- that diff is the point.
    """
    for slug, figure_dir in corpus_figures(args.figure):
        compiled = compile_brief(figure_dir / "person.md")
        (figure_dir / "expected.json").write_text(
            json.dumps(compiled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"updated golden: {slug} ({compiled['appearance_fingerprint'] or '-'})")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="score the corpus (exit 1 on a gating failure)")
    p_run.add_argument("figure", nargs="?", help="score one figure instead of all")
    p_run.set_defaults(func=cmd_run)

    p_gold = sub.add_parser("update-golden", help="record current briefs as golden snapshots")
    p_gold.add_argument("figure", nargs="?", help="update one figure instead of all")
    p_gold.set_defaults(func=cmd_update_golden)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
