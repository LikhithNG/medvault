#!/usr/bin/env python3
"""The safety filters, measured - and the measurement, held in place.

tools/safety_eval.py scores safety.is_emergency, is_decision and directs against phrasings
a separate writer labelled without seeing them (bench/safety_cases.json). These check that
the bench is well formed, that the harness counts what it says it counts, and that no change
to the patterns makes the held-out numbers worse than the ones published in the README.
"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tools"))

import safety_eval   # noqa: E402

BENCH = json.loads(safety_eval.CASES.read_text())


# ---- the bench ------------------------------------------------------------------------

def test_every_item_has_a_known_label_and_a_split():
    for section, labels in (("questions", safety_eval.QUESTION_LABELS),
                            ("answers", safety_eval.ANSWER_LABELS)):
        assert BENCH[section], section
        for c in BENCH[section]:
            assert c["label"] in labels, c
            assert c["split"] in safety_eval.SPLITS, c
            assert c["text"].strip(), c


def test_no_item_is_in_the_bench_twice():
    for section in ("questions", "answers"):
        ids = [c["id"] for c in BENCH[section]]
        texts = [" ".join(c["text"].lower().split()) for c in BENCH[section]]
        assert len(ids) == len(set(ids)), section
        assert len(texts) == len(set(texts)), section


def _round(case):
    """Which labeller's file an item came from: the second one's ids start "r2"."""
    return case["id"][:2] if case["id"].startswith("r2") else "r1"


def test_both_halves_hold_the_same_mix():
    """Each labeller's file is halved on its own, label by label."""
    for section, labels in (("questions", safety_eval.QUESTION_LABELS),
                            ("answers", safety_eval.ANSWER_LABELS)):
        for rnd in {_round(c) for c in BENCH[section]}:
            for label in labels:
                halves = [sum(1 for c in BENCH[section] if c["label"] == label
                              and c["split"] == s and _round(c) == rnd)
                          for s in safety_eval.SPLITS]
                assert abs(halves[0] - halves[1]) <= 1, (section, rnd, label, halves)


# ---- the harness ----------------------------------------------------------------------

RAW = {"questions": [{"id": f"q{i:03d}", "text": t, "label": l, "ambiguous": False}
                     for i, (t, l) in enumerate([
                         ("I have chest pain right now", "emergency"),
                         ("my throat is closing up", "emergency"),
                         ("should I stop taking the amoxicillin?", "decision"),
                         ("how do I feel about my dose", "decision"),
                         ("what did my x-ray show?", "other"),
                         ("who prescribed my inhaler?", "other")])],
       "answers": [{"id": "a001", "text": "You can stop it now.", "label": "directive",
                    "ambiguous": False},
                   {"id": "a002", "text": "Ask your pharmacist first.", "label": "fine",
                    "ambiguous": False}]}


def _built():
    raw = pathlib.Path(tempfile.mkdtemp()) / "raw.json"
    raw.write_text(json.dumps(RAW))
    return safety_eval.build(raw)


def test_the_same_file_always_splits_the_same_way():
    assert _built() == _built()


def test_the_split_is_stratified_by_label():
    built = _built()
    for label in ("emergency", "decision", "other"):
        splits = sorted(c["split"] for c in built["questions"] if c["label"] == label)
        assert splits == ["held_out", "tuning"], label


def test_recall_and_false_alarms_count_what_they_say():
    cases = {"questions": [{**c, "split": "tuning"} for c in RAW["questions"]],
             "answers": [{**c, "split": "tuning"} for c in RAW["answers"]]}
    decision = safety_eval.score(cases, "tuning", "decision")
    assert (decision["recall"]["hits"], decision["recall"]["total"]) == (1, 2)
    assert decision["missed"] == ["how do I feel about my dose"]
    assert decision["false_alarms"]["total"] == 2          # "other" only, not emergencies
    directive = safety_eval.score(cases, "tuning", "directive")
    assert directive["recall"]["hits"] == 1 and directive["false_alarms"]["hits"] == 0


def test_the_held_out_misses_stay_hidden_unless_asked_for():
    hidden = safety_eval.run()
    for by_split in hidden["filters"].values():
        assert isinstance(by_split["held_out"]["missed"], str)
        assert isinstance(by_split["tuning"]["missed"], list)
    shown = safety_eval.run(reveal=True)
    for by_split in shown["filters"].values():
        assert isinstance(by_split["held_out"]["missed"], list)


# ---- the published numbers --------------------------------------------------------------

# What the README publishes, unambiguous items only: (filter, half) -> (least it catches,
# most false alarms). A change to safety.py may move these up; it may not move them down.
PUBLISHED = {
    ("emergency", "tuning"): (104, 0), ("emergency", "held_out"): (56, 10),
    ("decision", "tuning"): (125, 0), ("decision", "held_out"): (80, 1),
    ("directive", "tuning"): (74, 0), ("directive", "held_out"): (41, 3),
}


def test_no_change_makes_the_published_numbers_worse():
    report = safety_eval.run()
    for (name, split), (caught, alarms) in PUBLISHED.items():
        r = report["filters"][name][split]
        assert r["recall"]["hits"] >= caught, (name, split, r["recall"])
        assert r["false_alarms"]["hits"] <= alarms, (name, split, r["false_alarms"])


def test_the_readme_quotes_the_numbers_the_harness_produces():
    readme = (ROOT / "README.md").read_text()
    report = safety_eval.run()
    for name in ("emergency", "decision", "directive"):
        r = report["filters"][name]["held_out"]["recall"]
        assert f"{r['hits']}/{r['total']}" in readme, name


def test_the_measurement_calls_no_model():
    import urllib.request

    def offline(*args, **kwargs):
        raise AssertionError("the measurement tried to reach the network")
    saved = urllib.request.urlopen
    urllib.request.urlopen = offline
    try:
        safety_eval.run()
    finally:
        urllib.request.urlopen = saved


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
