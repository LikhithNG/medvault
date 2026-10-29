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


def test_an_er_visit_line_finds_the_emergency_visit_record():
    """"E/R VISIT LEVEL IV" left only "visit" - one weak word, never evidence - so the
    charge read as having nothing behind it beside an emergency department record."""
    vault = VAULT + [{"title": "Emergency department visit", "service_date": "2026-03-14",
                      "summary": "Seen after a fall; discharged the same day.",
                      "provider": "Lahey"}]
    for printed in ("E/R VISIT LEVEL IV", "ER VISIT LEVEL 4", "ED VISIT", "E.R. VISIT"):
        r = cc.check_line({"description": printed, "service_date": "2026-03-14"}, vault)
        assert r["verdict"] == "MATCHED", (printed, r["verdict"])
        assert r["matches"][0]["title"] == "Emergency department visit", printed
    # "ER" also means extended release; only an ER *visit* is an emergency.
    r = cc.check_line({"description": "METFORMIN ER 500MG", "service_date": "2026-03-14"},
                      vault)
    assert r["verdict"] == "DATE_NO_MATCH", r.get("overlap")
    # And with no emergency record, an ER visit is still a question, not a match.
    r = cc.check_line({"description": "E/R VISIT LEVEL IV", "service_date": "2026-03-14"},
                      VAULT)
    assert r["verdict"] == "DATE_NO_MATCH", r.get("overlap")


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


def test_a_decoding_artifact_is_stripped_from_an_english_field():
    # A reason field came back from the model as "For the sinus infection整度". Accents and
    # genuinely non-Latin text must survive; stray CJK in an English field must not.
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))
    from extract import _clean
    assert _clean("For the sinus infection\u6574\u5ea6") == "For the sinus infection"
    assert _clean("Caf\u00e9 S\u00e3o Paulo clinic") == "Caf\u00e9 S\u00e3o Paulo clinic"
    assert _clean("\u6771\u4eac\u7dcf\u5408\u75c5\u9662") == "\u6771\u4eac\u7dcf\u5408\u75c5\u9662"


def test_one_generic_word_is_not_a_match():
    # "BLOOD DRAW" was reported as supported by a basic metabolic panel, on the single
    # shared word "blood". A false match is the worst direction of error here: a line the
    # patient believes is accounted for is a line they never ask about.
    r = cc.check_line({"description": "BLOOD DRAW", "service_date": "2026-03-14"}, VAULT)
    assert r["verdict"] == "DATE_NO_MATCH", f"matched on {r.get('overlap')}"


def test_one_distinctive_word_still_matches():
    # Requiring two words outright is too strict: this overlaps "Chest X-ray" on an
    # anatomical word that actually means something.
    r = cc.check_line({"description": "XRAY CHEST 2-VIEWS", "service_date": "2026-03-14"},
                      VAULT)
    assert r["verdict"] == "MATCHED"
    assert "chest" in r["overlap"]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
