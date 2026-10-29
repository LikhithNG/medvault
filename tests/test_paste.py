#!/usr/bin/env python3
"""Reading the rows of a bill somebody pasted in.

The bug these exist for: pasting the whole statement is the obvious thing to do, and the
statement's own "TOTAL DUE 3,532.00" was being read as an eleventh charge with no
published price. On the sample bill where every line is exactly at the published price,
that produced six flagged lines and $3,532 "unexplained". Inventing a finding on a
correct bill is the worst thing this tool can do.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import paste   # noqa: E402

CLEAN = (ROOT / "samples" / "bills" / "07_clean.txt").read_text()
SUMMARY = (ROOT / "samples" / "bills" / "06_summary_not_itemised.txt").read_text()


def test_a_whole_pasted_statement_yields_only_its_charges():
    items = paste.lines(CLEAN)

    assert [i["code"] for i in items] == ["70450", "71046", "80048", "76700"]


def test_the_statements_own_total_is_not_a_charge():
    assert paste.is_charge({"description": "TOTAL DUE", "code": None,
                            "charged": 3532.0}) is False


def test_a_header_row_with_no_amount_is_not_a_charge():
    for row in ("DOYLESTOWN HOSPITAL", "DATE CODE DESCRIPTION QTY AMOUNT",
                "Patient Financial Services Account 88211904"):
        assert not paste.is_charge(paste.line(row))


def test_a_coded_row_is_a_charge_however_it_is_worded():
    """"Total knee arthroplasty" is a procedure, not a summary line."""
    item = paste.line("2026-03-14  27447  TOTAL KNEE ARTHROPLASTY   1   28,400.00")

    assert item["code"] == "27447"
    assert paste.is_charge(item)


def test_an_uncoded_charge_survives_so_it_can_be_rejected_as_unitemised():
    """A summary bill's "HOSPITAL SERVICES 8,420.00" has to reach the screen for the
    not-itemised check to catch it. Filtering it out here would hide the problem."""
    items = paste.lines(SUMMARY)

    assert [i["description"] for i in items] == ["HOSPITAL SERVICES", "PHARMACY"]
    assert all(i["code"] is None for i in items)


def test_the_quantity_column_is_read_not_assumed():
    """Two units at a published $50 is $100 and correct. Read as one unit it looked like
    $50 over, and the letter said so in writing."""
    item = paste.line("2026-03-14  36415  BLOOD DRAW   2   100.00")

    assert item["units"] == 2 and item["charged"] == 100.0


def test_the_description_loses_the_date_code_and_money():
    item = paste.line("2026-03-14  70450  CT HEAD/BRAIN W/O CONTRAST   1   3,076.10")

    assert item["description"] == "CT HEAD/BRAIN W/O CONTRAST"
    assert item["service_date"] == "2026-03-14"


def test_everything_can_still_be_asked_for():
    """charges_only=False is how a caller sees the rows that were set aside."""
    assert len(paste.lines(CLEAN, charges_only=False)) > len(paste.lines(CLEAN))



# ---- from the test pass ------------------------------------------------------------

def test_a_credit_keeps_its_minus_sign_however_it_is_written():
    """The money pattern ignored "-", "(...)" and "CR": a reversal of $154 became a second
    $154 charge, reported as a duplicate, with a letter asking about it."""
    for row in ("2026-03-14  85025  CBC REVERSAL  1  -154.00",
                "2026-03-14  85025  CBC REVERSAL  1  (154.00)",
                "2026-03-14  85025  CBC REVERSAL  1  154.00 CR",
                "2026-03-14  85025  CBC REVERSAL  1  -$154.00"):
        assert paste.line(row)["charged"] == -154.0, row


def test_a_level_in_a_description_is_not_a_quantity():
    """ "ED VISIT LEVEL 5 8,025.00" was read as five visits, so 5x the posted price came
    out matching it exactly."""
    item = paste.line("2026-03-14  99285  ED VISIT LEVEL 5  8,025.00")
    assert item["units"] == 1 and item["charged"] == 8025.0
    assert paste.line("OFFICE VISIT LEVEL 3 150.00")["units"] == 1
    assert paste.line("2026-03-14  99284  ED VISIT LEVEL 4  2  3,210.00")["units"] == 2


def test_the_quantity_is_found_beside_a_unit_price_or_a_dollar_sign():
    """With a unit-price column, or "$" before the amount, the quantity was missed and the
    line read as one unit - a false "$308 over" that went into the letter."""
    item = paste.line("2026-03-14  85025  CBC  3  154.00  462.00")
    assert (item["units"], item["charged"]) == (3, 462.0)
    item = paste.line("2026-03-14  85025  CBC  3  $462.00")
    assert (item["units"], item["charged"]) == (3, 462.0)


def test_payments_adjustments_and_discounts_are_not_charges():
    for row in ("INSURANCE ADJUSTMENT -1,200.00", "PAYMENT RECEIVED -500.00",
                "CONTRACTUAL ADJUSTMENT 500.00", "DISCOUNT 50.00", "COPAY 20.00",
                "PATIENT PAYMENT 75.00", "WRITE OFF 10.00"):
        assert not paste.is_charge(paste.line(row)), row
    assert paste.is_charge(paste.line("ROOM AND BOARD 2,400.00"))
    # An uncoded credit is an adjustment however it is labelled.
    assert not paste.is_charge(paste.line("ADJ 03/14 -50.00"))


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
