#!/usr/bin/env python3
"""Measure the Companion's three safety filters against phrasings labelled in advance.

    python3 tools/safety_eval.py                  # counts for both halves; the tuning half's misses
    python3 tools/safety_eval.py --out FILE.json  # and write the report
    python3 tools/safety_eval.py --reveal         # the held-out half's misses too - see below
    python3 tools/safety_eval.py --build A.json B.json  # labellers' files -> bench/safety_cases.json

Three checks in safety.py decide what a model never gets to say:

  emergency  safety.is_emergency  a question describing an emergency gets the 911 answer
  decision   safety.is_decision   a question asking for a dose decision gets the fixed answer
  directive  safety.directs       a model answer that tells somebody to change a dose is replaced

They are keyword patterns, and until this they had only a handful of hand-picked unit
tests each - so nobody knew how many real ways of asking they missed.

WHERE THE PHRASINGS COME FROM, because that decides what the numbers mean. They were
written by a separate model instance from written definitions of the three labels, with
instructions not to open this repository: whoever writes the cases while looking at the
patterns writes cases the patterns catch. They are synthetic, English, and labelled by
that writer without clinical review; items it marked ambiguous are scored apart from the
headline. So this measures the filters against one careful writer's idea of how people
ask, which is a regression check and a map of the gaps, not a clinical validation.

THE SPLIT. Each label is shuffled with a fixed seed and halved: a tuning half, which the
patterns may be changed to fit, and a held-out half, which they may not. Only the held-out
half's counts are printed unless --reveal is given, so its misses cannot leak into the
patterns. A pattern tuned until the tuning half passes says little; the held-out number is
the one to quote.

Each filter is scored on its recall (the share of real cases it catches) and its false
alarms (the share of the rest it flags), with Wilson 95% intervals. No model is called.
"""
import argparse
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tools"))

import safety                    # noqa: E402
from accuracy_test import wilson  # noqa: E402

CASES = ROOT / "bench" / "safety_cases.json"
SEED = 7375
SPLITS = ("tuning", "held_out")

QUESTION_LABELS = ("emergency", "decision", "other")
ANSWER_LABELS = ("directive", "fine")


# filter -> (section of the bench, the label it should catch, the labels it should leave
# alone, the check). An emergency question flagged as a dose decision is not counted as a
# false alarm for that filter: triage runs first, so the flag never decides anything.
FILTERS = {
    "emergency": ("questions", "emergency", ("decision", "other"), safety.is_emergency),
    "decision": ("questions", "decision", ("other",), safety.is_decision),
    "directive": ("answers", "directive", ("fine",), safety.directs),
}


def _split(raw, rng):
    out = {}
    for section, labels in (("questions", QUESTION_LABELS), ("answers", ANSWER_LABELS)):
        items = []
        for label in labels:
            group = sorted((c for c in raw[section] if c["label"] == label),
                           key=lambda c: c["id"])
            rng.shuffle(group)
            half = (len(group) + 1) // 2
            items += [{**c, "split": SPLITS[0] if i < half else SPLITS[1]}
                      for i, c in enumerate(group)]
        out[section] = items
    return out


def build(*raw_paths, seed=SEED):
    """The labellers' files, with each item given a split. Each file is halved on its own,
    stratified by label, so both halves hold the same mix and a file added later leaves the
    earlier files' halves exactly as they were. Ordered by id first, so the same files
    always split the same way."""
    out = {"questions": [], "answers": []}
    seen = set()
    for n, path in enumerate(raw_paths):
        raw = json.loads(pathlib.Path(path).read_text())
        # A sentence an earlier labeller already wrote is not counted twice.
        raw = {section: [c for c in raw[section]
                         if (section, " ".join(c["text"].lower().split())) not in seen]
               for section in out}
        part = _split(raw, random.Random(seed + n))
        for section in out:
            out[section] += part[section]
            seen |= {(section, " ".join(c["text"].lower().split())) for c in part[section]}
    return {section: sorted(items, key=lambda c: c["id"]) for section, items in out.items()}


def _rate(hits, total):
    lo, hi = wilson(hits, total)
    return {"hits": hits, "total": total, "rate": round(hits / total, 4) if total else None,
            "ci": [round(lo, 4), round(hi, 4)]}


def score(cases, split, filter_name, ambiguous=False):
    """One filter on one half. Returns recall, false alarms, and the items it got wrong."""
    section, positive, negatives, check = FILTERS[filter_name]
    pool = [c for c in cases[section]
            if c["split"] == split and bool(c.get("ambiguous")) == ambiguous]
    pos = [c for c in pool if c["label"] == positive]
    neg = [c for c in pool if c["label"] in negatives]
    missed = [c for c in pos if not check(c["text"])]
    alarms = [c for c in neg if check(c["text"])]
    return {"recall": _rate(len(pos) - len(missed), len(pos)),
            "false_alarms": _rate(len(alarms), len(neg)),
            "missed": [c["text"] for c in missed],
            "false_alarm_items": [c["text"] for c in alarms]}


def routes(cases, split):
    """Where each kind of question ends up: the 911 answer, the prescriber answer, or a
    model. The column that matters is the last one for an emergency or a dose question."""
    table = {}
    for label in QUESTION_LABELS:
        pool = [c for c in cases["questions"]
                if c["split"] == split and c["label"] == label and not c.get("ambiguous")]
        went = {"emergency": 0, "decision": 0, "model": 0}
        for c in pool:
            went["emergency" if safety.is_emergency(c["text"])
                 else "decision" if safety.is_decision(c["text"]) else "model"] += 1
        table[label] = {**went, "total": len(pool)}
    return table


def run(cases_path=CASES, reveal=False):
    cases = json.loads(pathlib.Path(cases_path).read_text())
    report = {"cases": str(pathlib.Path(cases_path).relative_to(ROOT))
              if pathlib.Path(cases_path).is_relative_to(ROOT) else str(cases_path),
              "seed": SEED, "filters": {}, "routes": {}}
    for name in FILTERS:
        report["filters"][name] = {}
        for split in SPLITS:
            result = score(cases, split, name)
            result["ambiguous"] = {k: v for k, v in score(cases, split, name, True).items()
                                   if k in ("recall", "false_alarms")}
            if split == "held_out" and not reveal:
                result["missed"] = f"{len(result['missed'])} hidden - rerun with --reveal"
                result["false_alarm_items"] = (f"{len(result['false_alarm_items'])} hidden "
                                               "- rerun with --reveal")
            report["filters"][name][split] = result
    for split in SPLITS:
        report["routes"][split] = routes(cases, split)
    return report


def _pct(r):
    if not r["total"]:
        return "     —"
    return (f"{r['hits']:>3}/{r['total']:<3} {100 * r['rate']:5.1f}% "
            f"[{100 * r['ci'][0]:.0f}–{100 * r['ci'][1]:.0f}]")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--build", metavar="RAW", nargs="+",
                        help="write bench/safety_cases.json from the labellers' files, in order")
    parser.add_argument("--out", metavar="FILE", help="write the report here")
    parser.add_argument("--reveal", action="store_true",
                        help="print the held-out half's misses (do not tune on them)")
    args = parser.parse_args()
    if args.build:
        CASES.write_text(json.dumps(build(*args.build), indent=1, ensure_ascii=False) + "\n")
        print(f"written {CASES.relative_to(ROOT)}")
        return

    report = run(reveal=args.reveal)
    for name, by_split in report["filters"].items():
        for split, r in by_split.items():
            print(f"  {name:<10} {split:<9} caught {_pct(r['recall'])}   "
                  f"false alarms {_pct(r['false_alarms'])}")
    print("\n  where questions go (unambiguous)      911   prescriber   model")
    for split, table in report["routes"].items():
        for label, t in table.items():
            print(f"  {split:<9} {label:<10} ({t['total']:>3})      {t['emergency']:>5}"
                  f"   {t['decision']:>10}   {t['model']:>5}")
    for name, by_split in report["filters"].items():
        for split in SPLITS:
            r = by_split[split]
            if isinstance(r["missed"], list) and (r["missed"] or r["false_alarm_items"]):
                print(f"\n  {name} · {split} · missed:")
                for text in r["missed"]:
                    print(f"    - {text}")
                print(f"  {name} · {split} · false alarms:")
                for text in r["false_alarm_items"]:
                    print(f"    + {text}")
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(report, indent=1, ensure_ascii=False))
        print(f"\nwritten {args.out}")


if __name__ == "__main__":
    main()
