#!/usr/bin/env python3
"""The Companion's evaluation harness: its cases are well formed and its scoring is right.

The harness's live run asks a real model and is run by hand (tools/companion_eval.py).
This checks the harness itself, offline, with a canned reader - so a broken scorer cannot
report a pass rate that means nothing.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tools"))

import companion_eval   # noqa: E402
import ask              # noqa: E402

CASE = {"id": "x", "question": "q", "kinds": ["from_records"], "cite": ["Chest X-ray"],
        "say": ["no acute"], "never": ["double the dose"]}


def test_every_case_is_well_formed():
    cases = json.loads(companion_eval.CASES.read_text())["cases"]
    labels = set(ask.KIND_LABEL) | {"emergency"}
    assert len({c["id"] for c in cases}) == len(cases), "duplicate case ids"
    for c in cases:
        assert c["question"].strip() and set(c["kinds"]) <= labels, c["id"]


def test_the_cases_include_a_planted_instruction():
    """A prompt-injection case is the point of the vault's discharge note."""
    ids = {c["id"] for c in json.loads(companion_eval.CASES.read_text())["cases"]}
    assert "injection" in ids and "double the dose" in companion_eval.INJECTION


def test_a_correct_answer_passes():
    out = {"kind": "from_records", "answer": "No acute findings.",
           "sources": {2: {"title": "Chest X-ray"}}}
    assert companion_eval.score(CASE, out, 1.0, 30) == []


def test_each_way_of_failing_is_reported():
    out = {"kind": "general", "answer": "You should double the dose.", "sources": {}}
    why = companion_eval.score(CASE, out, 31.0, 30)
    assert any("labelled" in w for w in why) and any("cite" in w for w in why)
    assert any("did not say" in w for w in why) and any("said" in w for w in why)
    assert any("budget" in w for w in why)


def test_the_harness_runs_offline_and_the_guards_hold_without_a_model():
    report = companion_eval.run(reader=companion_eval.StubReader())
    by_id = {r["id"]: r for r in report["results"]}
    assert report["cases"] == len(by_id)
    for guarded in ("emergency", "stop-dose", "interaction"):
        assert by_id[guarded]["passed"], (guarded, by_id[guarded]["why"])
        assert by_id[guarded]["model"] is None, f"{guarded} reached a model"



def test_latency_is_also_reported_over_the_answers_a_model_gave():
    """Three cases never reach a model and answer in 0.0 s; folded into the median they
    flattered it (0.92 s published, 1.03 s over the seven model answers)."""
    report = companion_eval.run(reader=companion_eval.StubReader())
    asked = [r for r in report["results"] if r["model"]]
    assert report["model_answers"] == len(asked) < report["cases"]
    assert "p50_model_s" in report and "p95_model_s" in report


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
