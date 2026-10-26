#!/usr/bin/env python3
"""The cross-check must never say a service did not happen.

It can only say the patient has not filed anything supporting it. Every test here exists to
hold that line, because the feature is persuasive and the failure mode is a patient walking
into a billing office accusing them of a charge that was perfectly real.

Run with  python3 tests/test_crosscheck.py
"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))
import crosscheck as cc                                              # noqa: E402

VAULT = [
    {"title": "Chest X-ray", "service_date": "2026-03-14",
     "summary": "Two views of the chest, reported clear.", "provider": "Lahey"},
    {"title": "Basic metabolic panel", "service_date": "2026-03-14",
     "summary": "Routine blood chemistry.", "provider": "Lahey"},
    {"title": "Amoxicillin course", "service_date": "2026-09-18",
     "summary": "Ten day course for sinusitis.", "provider": "Lahey"},
]


def test_a_line_backed_by_a_record_is_matched():
    r = cc.check_line({"description": "RADIOLOGIC EXAM CHEST 2 VIEWS",
                       "service_date": "2026-03-14"}, VAULT)
    assert r["verdict"] == "MATCHED"
    assert r["matches"][0]["title"] == "Chest X-ray"


def test_a_record_dated_a_day_later_still_counts():
    # imaging reports are routinely dated after the scan
    r = cc.check_line({"description": "CHEST 2 VIEWS", "service_date": "2026-03-13"}, VAULT)
    assert r["verdict"] == "MATCHED", "a 1-day gap must not read as a missing record"


def test_a_date_with_no_paperwork_at_all_is_flagged_but_not_accused():
    r = cc.check_line({"description": "MRI LUMBAR SPINE", "service_date": "2026-06-02"}, VAULT)
    assert r["verdict"] == "NO_RECORD"
    low = r["ask"].lower()
    assert "did not happen" not in low and "never happened" not in low
    assert "may simply be paperwork you never received" in low, \
        "the benign explanation has to be offered in the same breath"


def test_a_day_you_have_records_for_but_nothing_matching():
    r = cc.check_line({"description": "MRI LUMBAR SPINE WO CONTRAST",
                       "service_date": "2026-03-14"}, VAULT)
    assert r["verdict"] == "DATE_NO_MATCH"
    assert "Ask what this charge covers" in r["ask"]


def test_filler_words_do_not_manufacture_a_match():
    # "HOSPITAL SERVICE" shares only stopwords with every record in the vault
    r = cc.check_line({"description": "HCHG GENERAL HOSPITAL SERVICE",
                       "service_date": "2026-03-14"}, VAULT)
    assert r["verdict"] == "DATE_NO_MATCH", "stopwords must not count as evidence"


def test_an_undated_line_is_not_guessed_at():
    r = cc.check_line({"description": "CHEST 2 VIEWS"}, VAULT)
    assert r["verdict"] == "UNDATED"
    assert r["matches"] == []


def test_an_empty_vault_says_so_rather_than_accusing():
    r = cc.check_line({"description": "CT HEAD", "service_date": "2026-03-14"}, [])
    assert r["verdict"] == "VAULT_THIN"
    assert "cannot be checked" in r["ask"]


def test_the_summary_carries_the_caveat_and_totals_only_unsupported_lines():
    lines = [
        {"description": "RADIOLOGIC EXAM CHEST 2 VIEWS", "service_date": "2026-03-14",
         "charged": 299.00},                                   # matched
        {"description": "MRI LUMBAR SPINE", "service_date": "2026-06-02",
         "charged": 9400.00},                                  # no record
    ]
    checked, summary = cc.check_bill(lines, VAULT)
    assert summary["unsupported"] == 1
    assert summary["amount_unsupported"] == 9400.00, "a matched line must not be counted"
    assert "not proof that the service never happened" in summary["caveat"]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
