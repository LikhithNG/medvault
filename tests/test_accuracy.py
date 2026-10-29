#!/usr/bin/env python3
"""The Assignment 2 success metrics, as tests rather than as a target.

The PRD promised >=90% precision on overcharge flags and >=85% extraction accuracy on
code and amount. Neither was ever measured. tools/accuracy_test.py measures them; this
keeps them measured, and keeps the measurement itself honest.

The last test is the one that matters most. A benchmark reporting 100% is worth nothing
unless it could have reported something else, so it re-introduces real defects — two of
which this project actually shipped — and fails if the benchmark does not notice.
"""
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tools"))

import accuracy_test as bench   # noqa: E402
import checker                  # noqa: E402

BILLS = 27          # three per hospital
SEED = 20261026


def corpus_and_table():
    table = checker.load_reference()
    catalogue = bench.by_hospital(table)
    hospitals = sorted(catalogue)
    every_code = {c for (_, c) in table}
    rng = random.Random(SEED)
    bills = []
    for i in range(BILLS):
        hospital = hospitals[i % len(hospitals)]
        prices = catalogue[hospital]
        bills.append(bench.build_bill(rng, hospital, prices,
                                      sorted(every_code - set(prices)), i))
    return bench.label_corpus(bills, catalogue), table


def test_the_corpus_spans_every_hospital_in_the_table():
    """One hospital is not enough: two of the nine have identical gross and cash prices,
    and a corpus built on one of those cannot detect a wrong-basis comparison."""
    corpus, table = corpus_and_table()
    assert len({b["hospital_name"] for b in corpus}) == len(bench.by_hospital(table))


def test_the_corpus_contains_every_kind_of_line():
    corpus, _ = corpus_and_table()
    labels = {l["expect"] for b in corpus for l in b["line_items"]}
    assert {"ABOVE_POSTED", "VERIFIED", "NOT_POSTED", "DUPLICATE",
            "QUANTITY_SUSPECT"} <= labels


def test_overcharge_precision_meets_the_prd_target():
    """>=90%. Precision governs: telling somebody to dispute a legitimate charge sends
    them into a fight they lose."""
    corpus, table = corpus_and_table()
    _, right, total, _, _ = bench.measure_flagging(corpus, table)

    assert total > 50, "too few flags to say anything"
    assert right / total >= 0.90


def test_the_checker_agrees_with_its_own_documented_rules():
    corpus, table = corpus_and_table()
    confusion, *_ = bench.measure_flagging(corpus, table)
    disagreements = {k: v for k, v in confusion.items() if k[0] != k[1]}

    assert not disagreements, f"verdicts that contradict the spec: {disagreements}"


def test_extraction_accuracy_meets_the_prd_target():
    """>=85% on code AND amount together, which is how the PRD specified it."""
    corpus, _ = corpus_and_table()
    n, both, _, _ = bench.measure_extraction(corpus)

    assert n > 100
    assert both / n >= 0.85


def test_a_wilson_interval_never_runs_past_one():
    """The reason for Wilson rather than the normal approximation: at 50 bills near 1.0
    the normal interval returns an upper bound above 100%."""
    lo, hi = bench.wilson(123, 123)
    assert 0.0 <= lo < hi <= 1.0
    assert lo > 0.95, "123 of 123 should not have a lower bound this loose"
    # The normal approximation gives (1.0, 1.0) here - a zero-width interval claiming
    # certainty from a finite sample. Wilson keeps a real lower bound and stays inside 1.
    assert bench.wilson(0, 0) == (0.0, 0.0)
    assert bench.wilson(0, 10)[0] == 0.0


def test_the_benchmark_notices_when_the_checker_is_broken():
    """A benchmark that cannot fail is not a measurement. Each of these is a real defect
    — 'units' is the one that put a correct line in a patient's letter."""
    corpus, table = corpus_and_table()
    rows = {name: (prec, rec, wrong)
            for name, prec, rec, wrong in bench.run_mutations(corpus, table)}

    assert rows["none (as shipped)"][2] == 0, "the unmutated run should be clean"
    for defect in ("units", "basis", "hospital"):
        prec, _, wrong = rows[defect]
        assert wrong > 0, f"the benchmark did not notice '{defect}'"
        assert prec < 0.90, f"'{defect}' left precision at {prec:.1%}"
    assert rows["tolerance widened to 2.0x"][1] < 0.90, "widening tolerance should cost recall"



def test_every_line_is_what_it_was_built_to_be():
    """ "Labelled by construction" is only true if the label a line was built with is the
    verdict the documented rules give it. Three lines built as "duplicate" were the first
    line on their bill - there was nothing yet to repeat - so they were built as a fresh
    code and expected VERIFIED under a label that said otherwise."""
    built = {"at_published": "VERIFIED", "above_published": "ABOVE_POSTED",
             "duplicate": "DUPLICATE", "quantity": "QUANTITY_SUSPECT",
             "not_posted": "NOT_POSTED", "just_inside_tolerance": "VERIFIED"}
    table = checker.load_reference()
    catalogue = bench.by_hospital(table)
    hospitals, every_code = sorted(catalogue), {c for (_, c) in table}
    rng = random.Random(SEED)
    published = bench.label_corpus(
        [bench.build_bill(rng, hospitals[i % len(hospitals)],
                          catalogue[hospitals[i % len(hospitals)]],
                          sorted(every_code - set(catalogue[hospitals[i % len(hospitals)]])), i)
         for i in range(50)], catalogue)                      # the 50 bills the README cites
    off = [(l["label"], l["expect"]) for b in published for l in b["line_items"]
           if built[l["label"]] != l["expect"]]
    assert not off, off


def test_the_corpus_does_not_depend_on_the_hash_seed():
    """It chose from a set, so it changed with PYTHONHASHSEED: 296 lines on one run, 299
    on another, and the README's figures reproduced only by luck."""
    import os
    import subprocess
    counts = set()
    for seed in ("0", "3", "11"):
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "accuracy_test.py")],
                             capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": seed,
                                  "TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": ""}).stdout
        counts.add(next(l for l in out.splitlines() if "lines across" in l))
    assert len(counts) == 1, counts


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
