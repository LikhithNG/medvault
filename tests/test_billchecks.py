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


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
