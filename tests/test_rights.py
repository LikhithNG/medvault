#!/usr/bin/env python3
"""Rights checks must never invent a protection, and never deny one it did not check.

The second half is the one that needs tests. A tool that answers "no" when it means "we
did not ask" will eventually tell somebody they have no right that they in fact have, and
it will sound just as confident doing it.

Run with  python3 tests/test_rights.py
"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))
import rights                                                        # noqa: E402

BILL = [{"description": "CT HEAD/BRAIN WO CONTRAST", "charged": 3100.00}]


def ids(found):
    return {f["rule"] for f in found}


def test_an_empty_context_asserts_nothing():
    found = rights.evaluate(BILL, 3100.0, rights.context())
    assert found == [], "a tool that was told nothing must claim nothing"


def test_the_open_questions_are_reported_rather_than_assumed():
    open_qs = rights.unanswered(rights.context())
    assert len(open_qs) == 4
    assert any("insured or self-pay" in q for q in open_qs)


def test_a_self_pay_patient_is_owed_an_estimate():
    found = rights.evaluate(BILL, 3100.0, rights.context(coverage="self_pay"))
    assert "gfe_missing" in ids(found)


def test_an_insured_patient_is_not_told_about_estimates():
    # The GFE right belongs to uninsured and self-pay patients only.
    found = rights.evaluate(BILL, 3100.0, rights.context(coverage="insured"))
    assert "gfe_missing" not in ids(found)


def test_four_hundred_over_the_estimate_opens_federal_dispute():
    at = rights.evaluate(BILL, 1400.0, rights.context(coverage="self_pay", gfe_amount=1000.0))
    assert "gfe_exceeded" in ids(at), "exactly $400 over must qualify"

    under = rights.evaluate(BILL, 1399.0,
                            rights.context(coverage="self_pay", gfe_amount=1000.0))
    assert "gfe_exceeded" not in ids(under)
    assert "gfe_over_small" in ids(under), "still worth mentioning, just not disputable"


def test_a_bill_under_its_estimate_produces_nothing():
    found = rights.evaluate(BILL, 800.0, rights.context(coverage="self_pay", gfe_amount=1000.0))
    assert ids(found) == set()


def test_charity_care_needs_a_yes_not_an_absence():
    assert "charity_care" in ids(rights.evaluate(BILL, 3100.0,
                                                 rights.context(nonprofit_hospital=True)))
    assert "charity_care" not in ids(rights.evaluate(BILL, 3100.0,
                                                     rights.context(nonprofit_hospital=None)))
    assert "charity_care" not in ids(rights.evaluate(BILL, 3100.0,
                                                     rights.context(nonprofit_hospital=False)))


def test_emergency_care_is_flagged_as_protected():
    found = rights.evaluate(BILL, 3100.0, rights.context(emergency=True))
    assert "nsa_emergency" in ids(found)


def test_the_in_network_facility_rule_needs_insurance_to_mean_anything():
    insured = rights.context(coverage="insured", in_network_facility=True)
    assert "nsa_in_network_facility" in ids(rights.evaluate(BILL, 3100.0, insured))

    selfpay = rights.context(coverage="self_pay", in_network_facility=True)
    assert "nsa_in_network_facility" not in ids(rights.evaluate(BILL, 3100.0, selfpay)), \
        "there is no network to be out of without a plan"


def test_an_ambulance_line_is_named_as_an_uncovered_gap():
    bill = BILL + [{"description": "A0427 ALS AMBULANCE EMERGENCY TRANSPORT",
                    "charged": 1890.00}]
    found = rights.evaluate(bill, 4990.0, rights.context())
    assert "ambulance_carveout" in ids(found)
    text = next(f for f in found if f["rule"] == "ambulance_carveout")
    assert "not going to guess" in text["means"], \
        "the state-law gap must be admitted, not filled in"


def test_every_finding_cites_the_rule_it_came_from():
    ctx = rights.context(coverage="self_pay", emergency=True, nonprofit_hospital=True)
    for f in rights.evaluate(BILL, 3100.0, ctx):
        assert f["source"], f"{f['rule']} has no citation"
        assert f["todo"], f"{f['rule']} tells the reader nothing to do"


def test_the_highest_value_findings_come_first():
    ctx = rights.context(coverage="self_pay", emergency=True, nonprofit_hospital=True)
    found = rights.evaluate(BILL + [{"description": "A0427 AMBULANCE"}], 3100.0, ctx)
    assert found[0]["severity"] == "high"
    assert found[-1]["severity"] == "info"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
