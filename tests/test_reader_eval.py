#!/usr/bin/env python3
"""The Reader's photo benchmark scores what it says it scores.

tools/reader_eval.py sends real photographs to a real model and is run by hand. What can
be tested without one is the scoring: a line read right must match code, quantity and
amount; a printed line not read is a miss; a line read that was never printed is an
invention; and the prescription's facts are checked one by one.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tools"))

import paste         # noqa: E402
import reader_eval   # noqa: E402

TRUTH = [{"code": "70450", "units": 1, "charged": 1619.0},
         {"code": "36415", "units": 2, "charged": 100.0}]


def test_a_perfect_read_scores_every_line_and_invents_none():
    right, missed, invented = reader_eval.score_bill(TRUTH, list(reversed(TRUTH)))
    assert (right, missed, invented) == (2, [], [])


def test_a_wrong_quantity_or_amount_is_a_miss_and_an_invention():
    read = [{"code": "70450", "units": 1, "charged": 1691.0},     # digits swapped
            {"code": "36415", "units": 1, "charged": 100.0}]      # quantity dropped
    right, missed, invented = reader_eval.score_bill(TRUTH, read)
    assert right == 0 and len(missed) == 2 and len(invented) == 2


def test_a_line_that_was_never_printed_is_counted_as_invented():
    read = TRUTH + [{"code": "99999", "units": 1, "charged": 5.0}]
    right, missed, invented = reader_eval.score_bill(TRUTH, read)
    assert right == 2 and not missed and [g["code"] for g in invented] == ["99999"]


def test_every_sample_photo_has_its_printed_lines_beside_it():
    for photo in sorted((ROOT / "samples" / "bills").glob("*.jpg")):
        text = photo.with_suffix(".txt")
        assert text.exists(), photo.name
        assert paste.lines(text.read_text()), photo.name


PERFECT = {"kind": "prescription", "service_date": "2026-09-18",
           "provider": "Riverbend Community Hospital",
           "medications": [
               {"name": "Amoxicillin-Clavulanate", "dose": "875 mg / 125 mg",
                "frequency": "1 tablet by mouth twice daily", "duration": "10 days"},
               {"name": "Fluticasone propionate nasal spray", "dose": "50 mcg",
                "frequency": "2 sprays each nostril once daily", "duration": "21 days"},
               {"name": "Ibuprofen", "dose": "400 mg",
                "frequency": "1 tablet every 8 hours as needed", "duration": "5 days"}]}


def test_a_faithful_prescription_passes_every_check():
    checks = reader_eval.score_prescription(PERFECT)
    assert all(passed for _, passed in checks), [c for c, p in checks if not p]


def test_an_as_needed_medicine_read_as_scheduled_fails_its_check():
    wrong = {**PERFECT, "medications": PERFECT["medications"][:2] + [
        {**PERFECT["medications"][2], "frequency": "1 tablet every 8 hours"}]}
    failed = [c for c, p in reader_eval.score_prescription(wrong) if not p]
    assert failed == ["ibuprofen: as needed"], failed


def test_a_misspelled_prescriber_fails_the_provider_check():
    """The check passed on the surname alone, so a staging read of "Dr. Amora Osei" for the
    printed "Dr. Amara Osei" scored as right. A name is a fact; spelt wrong it is wrong."""
    failed = [c for c, p in reader_eval.score_prescription(
        {**PERFECT, "provider": "Dr. Amora Osei, MD"}) if not p]
    assert failed == ["provider"], failed
    for right in ("Dr. Amara Osei, MD", "Riverbend Community Hospital"):
        assert all(p for _, p in reader_eval.score_prescription({**PERFECT, "provider": right}))


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
