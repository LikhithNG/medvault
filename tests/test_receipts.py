#!/usr/bin/env python3
"""No receipt, no flag — the Assignment 2 PRD's guarantee, enforced.

The PRD promised that every flag carries the published figure, the basis it was compared
on, the file URL and the collection date, and that this is "enforced in schema, not in a
code review". Two of those four fields were not on the object at all and nothing enforced
any of them. These tests are the enforcement.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import checker    # noqa: E402
import dispute    # noqa: E402
import receipts   # noqa: E402

HOSPITAL = "Doylestown Hospital"


def reviewed(items):
    return checker.check_bill({"hospital_name": HOSPITAL, "line_items": items},
                              checker.load_reference())


def test_a_priced_flag_carries_all_four_receipt_fields():
    line = reviewed([{"code": "70450", "description": "CT", "units": 1,
                      "charged": 3076.10}])["lines"][0]

    assert line["verdict"] == "ABOVE_POSTED"
    assert receipts.missing_fields(line) == ()
    assert line["basis"] == "hospital gross charge"
    assert line["collected_date"] == "2026-10-02"
    assert line["source_url"].startswith("http")


def test_the_basis_says_which_of_three_published_numbers_was_used():
    """Gross charge, cash price and negotiated rate are different figures for one code.
    Comparing against the wrong one manufactures a fake overcharge, so the receipt has to
    name the one that was used rather than leave a reader to infer it."""
    line = reviewed([{"code": "70450", "units": 1, "charged": 3076.10}])["lines"][0]
    assert "gross charge" in line["basis"]


def test_a_line_asserting_no_comparison_owes_no_receipt():
    """NOT_POSTED has no published figure behind it by definition. Treating that as a
    missing receipt would collapse it into an overcharge, which is the single easiest way
    to make this tool harmful."""
    line = reviewed([{"code": "J3490", "description": "UNSPECIFIED DRUG", "units": 1,
                      "charged": 900.0}])["lines"][0]

    assert line["verdict"] == "NOT_POSTED"
    assert not receipts.owes_a_receipt(line)
    assert receipts.has_receipt(line)
    assert receipts.receipt(line) is None


def test_a_whole_checked_bill_passes_the_audit():
    out = reviewed([{"code": "70450", "units": 1, "charged": 3076.10},
                    {"code": "71046", "units": 1, "charged": 299.0},
                    {"code": "J3490", "units": 1, "charged": 900.0}])

    assert receipts.audit(out) == []


def test_a_flag_stripped_of_its_source_is_refused():
    good = reviewed([{"code": "70450", "units": 1, "charged": 3076.10}])["lines"][0]
    stripped = {**good, "source_url": None}

    assert receipts.missing_fields(stripped) == ("source_url",)
    assert not receipts.has_receipt(stripped)

    quotable, withheld = receipts.quotable([good, stripped])
    assert quotable == [good] and withheld == [stripped]


def test_the_letter_leads_with_the_largest_amount_at_stake():
    """A billing office reads the first entry and skims the rest."""
    # Both over their published price, the smaller one listed first on the bill:
    # 36415 blood draw is $50 published, 72148 MRI is $6,009.
    out = reviewed([{"code": "36415", "description": "BLOOD DRAW", "units": 1,
                     "charged": 120.0},
                    {"code": "72148", "description": "MRI LUMBAR", "units": 1,
                     "charged": 9374.04}])
    text = dispute.letter(out, patient_name="A Patient")

    assert "72148" in text and "36415" in text
    assert text.index("72148") < text.index("36415"), "the letter kept the bill's order"


def test_the_letter_cites_the_file_and_the_date_for_every_line_it_quotes():
    out = reviewed([{"code": "70450", "description": "CT", "units": 1, "charged": 3076.10}])
    text = dispute.letter(out, patient_name="A Patient")

    assert "hospital gross charge" in text
    assert "2026-10-02" in text
    assert "standardcharges" in text


def test_a_line_without_a_receipt_is_withheld_out_loud_not_dropped():
    """An earlier version of this letter silently lost a flagged line. A letter that
    quietly shrinks is worse than one that explains."""
    out = reviewed([{"code": "70450", "description": "CT", "units": 1, "charged": 3076.10}])
    out = {**out, "lines": [{**l, "source_url": None} for l in out["lines"]]}

    text = dispute.letter(out, patient_name="A Patient")

    assert "70450 — CT\n" not in text
    assert "could not trace a published figure" in text


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
