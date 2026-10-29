#!/usr/bin/env python3
"""Checks that need nothing but the bill. Run with python3 tests/test_billchecks.py"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))
import billchecks                                                    # noqa: E402


def test_a_line_that_multiplies_out_is_not_flagged():
    assert billchecks.arithmetic({"units": 10, "posted_price": 189.00,
                                  "charged": 1890.00}) is None


def test_a_line_that_does_not_multiply_out_says_by_how_much():
    f = billchecks.arithmetic({"units": 10, "posted_price": 189.00, "charged": 2457.00})
    assert f and "$567.00" in f["detail"] and "over" in f["detail"]


def test_being_undercharged_is_reported_too():
    f = billchecks.arithmetic({"units": 2, "posted_price": 100.00, "charged": 150.00})
    assert f and "under" in f["detail"]


def test_a_penny_of_rounding_is_not_a_finding():
    assert billchecks.arithmetic({"units": 3, "posted_price": 33.33,
                                  "charged": 99.99}) is None


def test_a_line_missing_a_unit_price_is_left_alone():
    # No price to multiply by is not the same as a wrong multiplication.
    assert billchecks.arithmetic({"units": 4, "charged": 260.00}) is None
    assert billchecks.arithmetic({"posted_price": 65.0, "charged": 260.00}) is None


def test_an_unspecified_code_is_named_and_explained():
    f = billchecks.unspecified({"code": "J3490"})
    assert f and "Unclassified drug" in f["detail"]
    assert "no published price to compare" in f["detail"]


def test_an_ordinary_code_is_not_flagged_as_unspecified():
    assert billchecks.unspecified({"code": "74177"}) is None
    assert billchecks.unspecified({"code": ""}) is None


def test_lowercase_codes_are_still_caught():
    assert billchecks.unspecified({"code": "j3490"}) is not None


def test_run_reports_which_line_each_finding_belongs_to():
    lines = [{"code": "74177", "units": 1, "posted_price": 100.0, "charged": 100.0},
             {"code": "J3490", "charged": 4200.0},
             {"code": "85027", "units": 10, "posted_price": 189.0, "charged": 2457.0}]
    found = billchecks.run(lines)
    assert {i for i, _ in found} == {1, 2}
    assert {f["rule"] for _, f in found} == {"unspecified_code", "arithmetic"}


def test_reconciliation_against_the_printed_total():
    import extract
    five = [{"charged": 3100.0}, {"charged": 260.0}, {"charged": 241.0},
            {"charged": 299.0}, {"charged": 9400.0}]
    assert extract.reconciles(five, 13300.00) is True
    assert extract.reconciles(five, 13300.01) is True      # within tolerance
    assert extract.reconciles(five[:1], 13300.00) is False  # the truncation this catches
    assert extract.reconciles(five, None) is None, \
        "no printed total means unverified, which is not the same as correct"



# ---- the same charge twice -----------------------------------------------------------
# Repeated codes used to be found only when a hospital was chosen - by the Checker, against
# that hospital's price file - so a bill from any of the thousands of hospitals not in the
# table got no duplicate check at all, though it needs nothing but the bill. And the
# Checker's rule was "the code appears again anywhere": a daily blood count on three days
# was two duplicates, and two lines with no code were duplicates of each other.

def _line(code, date="2026-03-14", charged=100.0, description="ITEM"):
    return {"code": code, "service_date": date, "charged": charged, "units": 1,
            "description": description}


def test_the_same_code_twice_on_the_same_day_is_a_duplicate():
    found = billchecks.duplicates([_line("70450", description="CT HEAD"), _line("72148"),
                                   _line("70450", charged=3076.10, description="CT HEAD")])
    assert [i for i, _ in found] == [2]
    f = found[0][1]
    assert f["rule"] == "duplicate" and "70450" in f["title"] and "2026-03-14" in f["title"]
    assert "$3,076.10" in f["detail"] and f["code"] == "70450"


def test_the_same_test_on_different_days_is_not_a_duplicate():
    daily = [_line("85025", date=f"2026-03-{d}") for d in (14, 15, 16)]
    assert billchecks.duplicates(daily) == []


def test_lines_with_no_code_are_never_duplicates_of_each_other():
    assert billchecks.duplicates([_line(""), _line(None), _line("  ")]) == []


def test_a_credit_or_a_zero_line_is_not_a_duplicate():
    assert billchecks.duplicates([_line("70450"), _line("70450", charged=-100.0),
                                  _line("70450", charged=0)]) == []


def test_codes_are_compared_as_codes():
    found = billchecks.duplicates([_line(" g0378"), _line("G0378 ")])
    assert [i for i, _ in found] == [1]


def test_two_undated_lines_with_one_code_are_duplicates():
    assert [i for i, _ in billchecks.duplicates([_line("70450", date=None),
                                                 _line("70450", date=None)])] == [1]


def test_run_reports_a_duplicate_with_the_other_checks_in_bill_order():
    lines = [_line("70450"), _line("J3490"), _line("70450")]
    assert [(i, f["rule"]) for i, f in billchecks.run(lines)] == [
        (1, "unspecified_code"), (2, "duplicate")]


def test_the_hospital_check_uses_the_same_rule():
    import checker
    table = checker.load_reference()

    def verdicts(items):
        bill = checker.check_bill({"hospital_name": "Doylestown Hospital",
                                   "line_items": items}, table)
        return [l["verdict"] for l in bill["lines"]]
    assert "DUPLICATE" not in verdicts([_line("70450", date=f"2026-03-{d}", charged=1.0)
                                        for d in (14, 15, 16)])
    assert "DUPLICATE" not in verdicts([_line(""), _line("")])
    assert verdicts([_line("70450"), _line("70450")])[1] == "DUPLICATE"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
