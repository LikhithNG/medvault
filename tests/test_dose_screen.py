#!/usr/bin/env python3
"""The dose log on the Medicines screen: one tap for taken, one for skipped, one to undo.

The real app against a throwaway vault, as in test_bill_screen.py. What these hold in
place: a tap changes the log and the box together, the screen says what it did, and a
count that is running out is said before it runs out.

Run with  python3 tests/test_dose_screen.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tests"))

from test_bill_screen import _app, _shown, offline_vault   # noqa: E402


def _toasts(at):
    return [t.value for t in at.toast]


def _click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _medicine(con, owner, **stock):
    import db
    import doselog
    rx = db.add_record(con, kind="prescription", title="Rx", service_date="2026-10-01",
                       owner_id=owner["id"])
    med = db.add_medication(con, rx, {"name": "Amoxicillin", "dose": "1 tablet",
                                      "frequency": "twice daily"})
    if stock:
        doselog.set_stock(con, med, owner["id"], **stock)
    return med


def _stock(con, owner):
    import db
    return db.list_medications(con, owner_id=owner["id"])[0]["stock"]


def test_taken_logs_the_dose_and_takes_one_out_of_the_box():
    import doselog
    with offline_vault() as (con, alice, _):
        _medicine(con, alice, stock=10)
        at = _click(_app(alice), "Taken")
        log = doselog.dose_log(con, alice["id"])
        assert [(r["at"], r["status"]) for r in log] == [("08:00", "taken")]
        assert _stock(con, alice) == 9
        assert any("9 tablets left" in t for t in _toasts(at))


def test_skip_is_logged_and_uses_nothing():
    import doselog
    with offline_vault() as (con, alice, _):
        _medicine(con, alice, stock=10)
        _click(_app(alice), "Skip")
        assert [r["status"] for r in doselog.dose_log(con, alice["id"])] == ["skipped"]
        assert _stock(con, alice) == 10


def test_undo_puts_the_dose_back_in_the_box():
    import doselog
    with offline_vault() as (con, alice, _):
        _medicine(con, alice, stock=10)
        _click(_app(alice), "Taken")
        # A fresh session, as in test_ux.py: the test runner does not carry widget state
        # across a run in which the screen's buttons changed.
        _click(_app(alice), "Undo")
        assert doselog.dose_log(con, alice["id"]) == []
        assert _stock(con, alice) == 10


def test_a_box_running_low_says_so_before_it_is_empty():
    with offline_vault() as (con, alice, _):
        _medicine(con, alice, stock=3)
        assert _shown(_app(alice), "Running low")


def test_a_refill_adds_what_a_refill_holds():
    with offline_vault() as (con, alice, _):
        _medicine(con, alice, stock=2, refill_size=30)
        at = _click(_app(alice), "Refilled: add 30")
        assert _stock(con, alice) == 32
        assert any("32 tablets" in t for t in _toasts(at))


def test_the_stock_form_saves_what_was_typed():
    """A number in the box is a count. There used to be a "Count what's left" tick as well,
    and a patient who typed 30 without ticking it saved nothing, and was told it saved."""
    with offline_vault() as (con, alice, _):
        med = _medicine(con, alice)
        at = _app(alice)
        at.number_input(key=f"left{med}").set_value(28.0).run()
        _click(at, "Save stock")
        assert _stock(con, alice) == 28


def test_a_large_liquid_dose_does_not_take_the_screen_down():
    """"500 ml" is read as 500 per dose, and the dose field stopped at 100: Streamlit
    raises when a field's value is past its own maximum."""
    import db
    with offline_vault() as (con, alice, _):
        rx = db.add_record(con, kind="prescription", title="Rx", service_date="2026-10-01",
                           owner_id=alice["id"])
        db.add_medication(con, rx, {"name": "Oral rehydration", "dose": "500 ml",
                                    "frequency": "twice daily"})
        at = _app(alice)
        assert not at.exception, [e.value for e in at.exception]


def test_hiding_medicine_names_in_notifications_is_remembered():
    import db
    with offline_vault() as (con, alice, _):
        _medicine(con, alice)
        at = _app(alice)
        assert not at.exception, [e.value for e in at.exception]
        at.toggle(key="notify_private").set_value(True).run()
        assert not at.exception, [e.value for e in at.exception]
        assert db.get_profile(con, alice["id"]).get("notify_private") == "1"
        assert _app(alice).toggle(key="notify_private").value is True


def test_another_patients_doses_are_not_on_my_screen():
    with offline_vault() as (con, alice, bob):
        _medicine(con, alice, stock=10)
        at = _app(bob)
        assert not any(b.label == "Taken" for b in at.button), "Bob was offered Alice's dose"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
