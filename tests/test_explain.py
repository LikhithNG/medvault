#!/usr/bin/env python3
"""The explainer must never say a number the checks did not establish.

It is not a language model, and these tests are why. A generative answer to "why is this
charge wrong" is fluent whether or not it knows, and on a medical bill a fluent wrong
answer is what sends somebody into a billing office quoting a figure that collapses under
one question.

Run with  python3 tests/test_explain.py
"""
import pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))
import explain                                                       # noqa: E402

STATE = {
    "priced": {
        "billed_total": 13300.00, "posted_total": 8368.00, "questionable_amount": 4932.00,
        "lines": [
            {"code": "72148", "description": "MRI LUMBAR WITHOUT", "units": 1,
             "charged": 9400.00, "posted_price": 6009.00, "amount_over": 3391.00,
             "verdict": "ABOVE_POSTED"},
            {"code": "71046", "description": "XRAY CHEST 2-VIEWS", "units": 1,
             "charged": 299.00, "posted_price": 299.00, "amount_over": 0.0,
             "verdict": "VERIFIED"},
            {"code": "J3490", "description": "UNCLASSIFIED DRUG", "units": 1,
             "charged": 4200.00, "posted_price": None, "verdict": "NOT_POSTED"},
        ],
    },
    "rights": [{"title": "You were entitled to a written estimate before this care",
                "means": "Providers must give self-pay patients a Good Faith Estimate.",
                "todo": "Ask the billing office in writing.",
                "source": "No Surprises Act · 45 CFR 149.610"}],
    "crosschecked": [{"charged": 9400.00, "verdict": "NO_RECORD",
                      "ask": "Ask what this charge was for."}],
}

MONEY = re.compile(r"\$[\d,]+\.\d{2}")
ESTABLISHED = {"$13,300.00", "$8,368.00", "$4,932.00", "$9,400.00", "$6,009.00",
               "$3,391.00", "$299.00", "$4,200.00"}


def test_no_answer_ever_contains_an_invented_figure():
    questions = ["why is this flagged", "what is 72148", "what is the total",
                 "what are my rights", "do my records support this", "is this fraud",
                 "what do i do next", "are there duplicates", "what about 71046",
                 "explain J3490", "how much do i owe", "what is code 99999"]
    for q in questions:
        out = explain.answer(q, STATE) or ""
        for found in MONEY.findall(out):
            assert found in ESTABLISHED, f"{q!r} produced an unestablished figure {found}"


def test_a_code_on_the_bill_is_explained_from_its_own_row():
    out = explain.answer("what is 72148", STATE)
    assert "$9,400.00" in out and "$6,009.00" in out and "$3,391.00" in out
    assert "more than the price the hospital publishes" in out


def test_a_code_not_on_the_bill_is_not_invented():
    out = explain.answer("what is code 99999", STATE)
    assert "not on the bill" in out
    assert not MONEY.findall(out), "it made up figures for a code it does not have"


def test_the_unexplained_figure_is_explained_as_a_gap_not_a_refund():
    out = explain.answer("what is the unexplained difference", STATE)
    assert "not money you are owed" in out and "not a refund estimate" in out


def test_fraud_is_answered_with_a_no():
    out = explain.answer("is this fraud, should I sue them", STATE)
    assert "nothing here is evidence of fraud" in out.lower()
    assert "will not say that it is" in out.lower()
    assert "not a lawyer" in out.lower() and "not an accusation" in out.lower()


def test_records_answer_carries_the_caveat():
    out = explain.answer("do my records show this happened", STATE)
    assert "rarely everything" in out
    assert "not proof that the service never happened" in out


def test_an_empty_state_says_so_rather_than_improvising():
    for q in ("why is this flagged", "what is the total", "are there duplicates"):
        out = explain.answer(q, {})
        assert "yet" in out.lower(), f"{q!r} answered from an empty state: {out[:60]}"
        assert not MONEY.findall(out)


def test_an_unknown_question_admits_it_and_offers_what_it_can_do():
    out = explain.answer("what is the weather in Boston", STATE)
    assert "do not understand" in out
    assert "I can tell you about" in out
    assert not MONEY.findall(out)


def test_no_duplicates_is_stated_rather_than_left_silent():
    out = explain.answer("are there any duplicates", STATE)
    assert "No duplicate codes were found" in out


def test_rights_answers_cite_their_rule():
    out = explain.answer("what are my rights", STATE)
    assert "45 CFR 149.610" in out


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
