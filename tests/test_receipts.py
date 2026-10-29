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


def test_an_unmatched_hospital_is_not_reported_as_having_no_actions():
    """A zero that means "not found in the enforcement file" and a zero that means
    "nothing happened" are different claims. The table holds two of the first kind:
    a city suffix and an operator prefix each broke a join, and the miss was written
    down as a count. tools/verify_enforcement.py found them against the live CMS file."""
    line = checker.check_bill(
        {"hospital_name": "Community Hospital of Stokes",
         "line_items": [{"code": "36415", "units": 1, "charged": 90.0}]},
        checker.load_reference())["lines"][0]

    assert line["hospital_enforcement_actions"] == 0
    assert line["enforcement_match"] == "none", (
        "a zero from a failed join must be distinguishable from a real zero")


def test_a_matched_hospital_says_how_it_was_matched():
    line = checker.check_bill(
        {"hospital_name": HOSPITAL,
         "line_items": [{"code": "70450", "units": 1, "charged": 3076.10}]},
        checker.load_reference())["lines"][0]

    assert line["enforcement_match"] == "name+state"
    assert line["hospital_enforcement_actions"] == 2
    assert line["hospital_latest_cms_action"] == "Closure Notice"
    assert line["hospital_latest_action_date"] == "2025-09-18"


def test_cms_entries_are_not_called_actions_against_the_hospital():
    """The count is every row CMS's price-transparency file holds for the hospital -
    closure notices and "Met Requirements" included - and the screen called all of them
    "enforcement actions against this hospital". Across the whole file, 7,573 of 13,355
    rows are closures or findings that a hospital met the rule. Found checking the deck."""
    import bill_render
    line = {"enforcement_match": "name+state", "hospital_enforcement_actions": 2,
            "hospital_latest_cms_action": "Closure Notice",
            "hospital_latest_action_date": "2025-09-18"}
    kind, head, why = bill_render.enforcement_note([line])
    assert kind == "hint"
    assert "2 entries" in head and "Closure Notice" in head and "18 September 2025" in head
    assert "against this hospital" not in head + why
    kind, head, _ = bill_render.enforcement_note([{**line, "hospital_enforcement_actions": 1,
                                                   "hospital_latest_cms_action": "Met Requirements"}])
    assert "1 entry" in head and "Met Requirements" in head
    kind, head, _ = bill_render.enforcement_note([{**line, "hospital_enforcement_actions": 0}])
    assert kind == "caption" and "no entries" in head
    kind, head, _ = bill_render.enforcement_note([{**line, "enforcement_match": "none",
                                                   "hospital_enforcement_actions": 0}])
    assert kind == "hint" and "not a clean record" in head



# ---- from the test pass: a letter whose arithmetic did not add up ------------------

def _reviewed(lines, questionable):
    return {"hospital_name": "A Hospital", "billed_total": 600.0, "posted_total": 462.0,
            "questionable_amount": questionable, "lines": lines}


RECEIPT = {"source_url": "https://example.org/prices.csv", "basis": "hospital gross charge",
           "collected_date": "2026-10-02"}


def test_a_multi_unit_line_in_the_letter_adds_up():
    """ "Billed $600.00. Your published price is $154.00. Difference: $138.00." - the $462
    for three units, the figure that makes it add up, was never printed."""
    text = dispute.letter(_reviewed([{"code": "85025", "description": "CBC", "units": 3,
                                      "charged": 600.0, "posted_price": 154.0,
                                      "expected_for_units": 462.0, "amount_over": 138.0,
                                      "verdict": "ABOVE_POSTED", **RECEIPT}], 138.0))
    assert "$462.00 for 3 units" in text and "Difference: $138.00" in text


def test_a_letter_with_nothing_to_quantify_does_not_ask_about_zero_dollars():
    text = dispute.letter(_reviewed([{"code": "J3490", "description": "DRUG", "units": 1,
                                      "charged": 420.0, "verdict": "NOT_POSTED"}], 0.0))
    assert "$0.00" not in text and "J3490" in text


def test_the_letter_to_the_hospital_carries_no_advice_meant_for_the_patient():
    found = [{"title": "This bill is $900.00 above your estimate",
              "todo": "Start dispute resolution within 120 days of the bill.",
              "source": "No Surprises Act · 45 CFR 149.620"}]
    text = dispute.letter(_reviewed([{"code": "J3490", "description": "DRUG", "units": 1,
                                      "charged": 420.0, "verdict": "NOT_POSTED"}], 0.0),
                          rights_findings=found)
    assert "Start dispute resolution" not in text
    assert "This bill is $900.00 above your estimate" in text and "149.620" in text


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
