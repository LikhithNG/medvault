#!/usr/bin/env python3
"""A portal's record file on screen: checked before filing like any read, and labelled as
what it is - copied from the hospital's own file, not read by an AI.

The real app against a throwaway vault, as in test_bill_screen.py. The Add screen's upload
half cannot be driven by the test runner, so the filing half is run on its own with the
draft ccda.read() makes, as test_ux.py does for the Reader's drafts.

Run with  python3 tests/test_portal_screen.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tests"))

from test_bill_screen import _app, _shown, offline_vault   # noqa: E402

SAMPLE = (ROOT / "tests" / "fixtures" / "portal_summary.xml").read_bytes()


def _click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _filing(medvault):
    import sys
    sys.path.insert(0, medvault)
    import screen_records
    import session
    import ui
    ui.show_flash()
    screen_records.check_and_file(session.vault())


def _review(account):
    import ccda
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_resource.clear()
    at = AppTest.from_function(_filing, default_timeout=60, args=(str(ROOT / "medvault"),))
    at.session_state["account"] = account
    at.session_state["draft"] = ccda.read(SAMPLE)
    at.session_state["draft_file"] = ("summary.xml", "text/xml", SAMPLE)
    at.session_state["draft_model"] = ccda.READER
    return at.run()


def test_the_review_says_the_file_was_copied_not_read_by_ai():
    with offline_vault() as (_, alice, _):
        at = _review(alice)
        assert not at.exception, [e.value for e in at.exception]
        assert _shown(at, "Results found · 5")
        assert any("not read by an AI" in c.value for c in at.caption)
        assert not any("Read by an AI" in c.value for c in at.caption)


def test_filing_keeps_every_medicine_result_and_the_allergy():
    import db
    with offline_vault() as (con, alice, _):
        _click(_review(alice), "File this record")
        [record] = [r for r in db.list_records(con, owner_id=alice["id"])
                    if r["read_by"] == "patient portal file (C-CDA), no AI"]
        meds = {m["name"].split()[0]: m for m in db.list_medications(con, active_only=False, owner_id=alice["id"])
                if m["record_id"] == record["id"]}
        assert set(meds) == {"Fluticasone", "Montelukast", "Albuterol", "Prednisone"}
        assert not meds["Prednisone"]["active"], "a finished course was filed as current"
        results = db.lab_results_by_record(con, [alice["id"]])[record["id"]]
        assert {(r["code"], r["taken_on"]) for r in results} >= {("4548-4", "2026-04-12"), ("4548-4", "2026-10-12")}
        card = db.get_profile(con, alice["id"])
        assert card["allergies"] == "Penicillin G (hives)"
        assert card["conditions"] == "Asthma"


def test_a_medicine_already_on_the_list_is_not_filed_twice():
    """A portal summary lists every current medicine, including the ones a photographed
    prescription already filed. A second copy rang a second reminder for the same tablet."""
    import db
    with offline_vault() as (con, alice, _):
        rx = db.add_record(con, kind="prescription", title="Rx", service_date="2026-10-12", owner_id=alice["id"])
        db.add_medication(con, rx, {"name": "Montelukast", "dose": "10 mg", "frequency": "at bedtime"})
        at = _review(alice)
        assert _shown(at, "Already on your list")
        _click(at, "File this record")
        names = [m["name"] for m in db.list_medications(con, active_only=True, owner_id=alice["id"])]
        assert sum(n.lower().startswith("montelukast") for n in names) == 1, names
        assert any(n.startswith("Fluticasone") for n in names), "a new medicine was held back too"


def test_a_repeat_can_still_be_filed_when_the_patient_says_it_is_different():
    import db
    with offline_vault() as (con, alice, _):
        rx = db.add_record(con, kind="prescription", title="Rx", service_date="2026-10-12", owner_id=alice["id"])
        db.add_medication(con, rx, {"name": "Montelukast", "dose": "10 mg", "frequency": "at bedtime"})
        at = _review(alice)
        at.checkbox(key="repeat_0").check().run()
        _click(at, "File this record")
        names = [m["name"] for m in db.list_medications(con, active_only=True, owner_id=alice["id"])]
        assert sum(n.lower().startswith("montelukast") for n in names) == 2


def test_a_different_medicine_sharing_a_first_word_is_not_held_back():
    """Vitamin D on the list is not Vitamin B12 in the file; insulin glargine is not lispro."""
    import screen_records
    assert screen_records._drug("Vitamin B12 1000 MCG") != screen_records._drug("Vitamin D3 2000 UNT")
    assert screen_records._drug("Insulin lispro 100 UNT/ML") != screen_records._drug("Insulin glargine")
    assert screen_records._drug("Fluticasone propionate 110 MCG") == screen_records._drug("Fluticasone inhaler")
    assert screen_records._drug("1234") == "", "a name with no letters must match nothing"


def test_ticking_one_of_two_identical_entries_files_only_that_one():
    import db
    import ccda
    with offline_vault() as (con, alice, _):
        rx = db.add_record(con, kind="prescription", title="Rx", service_date="2026-10-12", owner_id=alice["id"])
        db.add_medication(con, rx, {"name": "Montelukast", "dose": "10 mg", "frequency": "at bedtime"})
        at = _review(alice)
        draft = ccda.read(SAMPLE)
        montelukast = next(m for m in draft["medications"] if m["name"].startswith("Montelukast"))
        draft["medications"].append(dict(montelukast))        # the same entry, twice in one file
        at.session_state["draft"] = draft
        at.run()
        at.checkbox(key="repeat_0").check().run()
        _click(at, "File this record")
        names = [m["name"] for m in db.list_medications(con, active_only=True, owner_id=alice["id"])]
        assert sum(n.lower().startswith("montelukast") for n in names) == 2, names


def test_the_card_is_left_alone_when_the_patient_says_so():
    import db
    with offline_vault() as (con, alice, _):
        at = _review(alice)
        at.checkbox(key="portal_allergies").uncheck().run()
        at.checkbox(key="portal_problems").uncheck().run()
        _click(at, "File this record")
        assert not db.get_profile(con, alice["id"]).get("allergies")


def test_the_records_screen_shows_a_test_over_time_and_says_where_it_came_from():
    with offline_vault() as (_, alice, _):
        _click(_review(alice), "File this record")
        at = _app(alice)
        assert not at.exception, [e.value for e in at.exception]
        assert _shown(at, "Results over time")
        assert any("Hemoglobin A1c" in e.label and "2 results" in e.label for e in at.expander)
        html = " ".join(m.value for m in at.markdown)
        assert "Copied from your patient portal's record file" in html
        assert "Read off the report by an AI reader" not in html


def test_a_plain_word_search_says_what_else_it_searched_for():
    import db
    with offline_vault() as (con, alice, _):
        db.add_record(con, kind="visit", title="Diabetes review", owner_id=alice["id"])
        at = _app(alice)
        next(t for t in at.text_input if t.label == "Search").set_value("high blood sugar").run()
        assert any("Also searched for" in c.value and "diabetes" in c.value for c in at.caption)
        assert _shown(at, "Diabetes review")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
