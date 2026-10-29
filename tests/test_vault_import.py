#!/usr/bin/env python3
"""Putting a vault file back: it cannot break the account it is put into.

A security review of the import found that it trusted the file. A profile with
organ_donor "maybe" made the Card screen raise on every load - and the restore control is
on that screen, so the account could not be repaired. A medicine course of "999999999
days" overflowed the date arithmetic and took down the Medicines screen, and a clinician's
screen with it. Records given as a dict, a list as a title, or a nameless medicine raised
out of the import half way through, leaving part of a vault behind. And an export then an
import brought finished medicines back as current - onto the emergency card.
"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tests"))

import accounts   # noqa: E402
import db         # noqa: E402
import schedule   # noqa: E402


def _patient():
    con = db.connect(tempfile.mktemp(suffix=".db"))
    me, _ = accounts.create(con, email="p@example.test", password="password1",
                            role="patient", display_name="Pat")
    return con, me["id"]


def _counts(con, owner):
    return (len(db.list_records(con, limit=10_000, owner_id=owner)),
            len(db.list_medications(con, active_only=False, owner_id=owner)))


def test_a_file_of_the_wrong_shape_is_refused_whole_and_writes_nothing():
    con, owner = _patient()
    good = {"id": 1, "kind": "lab", "title": "Panel", "service_date": "2026-03-14"}
    for broken in ({"records": {"1": good}},
                   {"records": [good, "not a record"]},
                   {"records": [good], "medications": {"name": "x"}},
                   {"records": [good], "profile": ["not", "a", "card"]},
                   {"records": [good] * 2001},
                   ["a", "list"], "not json", b"\xff\xfe"):
        try:
            db.import_vault(con, owner, broken if not isinstance(broken, (dict, list))
                            else json.dumps(broken))
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted {str(broken)[:60]}")
        assert _counts(con, owner) == (0, 0), str(broken)[:60]


def test_odd_values_in_a_well_shaped_file_are_cleaned_not_raised():
    con, owner = _patient()
    done = db.import_vault(con, owner, json.dumps({
        "records": [{"id": 1, "kind": "not-a-kind", "title": ["a", "list"],
                     "service_date": "9999-12-30 or so", "provider": 7}],
        "medications": [{"record_id": 1, "name": None},
                        {"record_id": 1, "name": "Warfarin", "dose": 5,
                         "duration": "999999999 days"}]}))
    assert done["records_added"] == 1 and done["medications_added"] == 1
    (rec,) = db.list_records(con, owner_id=owner)
    assert rec["kind"] == "other" and isinstance(rec["title"], str)
    assert rec["service_date"] is None


def test_a_profile_value_that_would_break_a_screen_is_left_out():
    con, owner = _patient()
    db.import_vault(con, owner, json.dumps({"records": [], "profile": {
        "full_name": "Pat", "organ_donor": "maybe", "day_start": "banana",
        "blood_type": "Z+", "pw_hash": "nope", "allergies": "Penicillin"}}))
    card = db.get_profile(con, owner)
    assert card.get("full_name") == "Pat" and card.get("allergies") == "Penicillin"
    for dropped in ("organ_donor", "day_start", "blood_type", "pw_hash"):
        assert not card.get(dropped), dropped


def test_a_finished_medicine_comes_back_finished():
    con, owner = _patient()
    rid = db.add_record(con, kind="prescription", title="Rx", owner_id=owner)
    db.add_medication(con, rid, {"name": "Warfarin", "dose": "5 mg"})
    (med,) = db.list_medications(con, owner_id=owner)
    db.set_medication_active(con, med["id"], False)
    exported = db.export_vault(con, owner)

    con2, owner2 = _patient()
    db.import_vault(con2, owner2, exported)
    assert db.list_medications(con2, active_only=True, owner_id=owner2) == []
    assert len(db.list_medications(con2, active_only=False, owner_id=owner2)) == 1


def test_restoring_twice_does_not_duplicate_a_record_with_no_kind():
    con, owner = _patient()
    payload = json.dumps({"records": [{"id": 1, "title": "Letter"}]})
    db.import_vault(con, owner, payload)
    db.import_vault(con, owner, payload)
    assert _counts(con, owner)[0] == 1


def test_a_medicine_whose_record_has_no_id_is_not_attached_to_another_record():
    con, owner = _patient()
    db.import_vault(con, owner, json.dumps({
        "records": [{"title": "A"}, {"title": "B"}],
        "medications": [{"record_id": None, "name": "Orphan"}]}))
    assert _counts(con, owner) == (2, 0)


def test_dates_and_durations_from_anywhere_never_overflow_the_schedule():
    for med in ({"service_date": "9999-12-30", "duration": "7 days"},
                {"service_date": "2026-10-01", "duration": "999999999 days"},
                {"service_date": "0001-01-01", "duration": "1 day"}):
        schedule.course_end(med)                       # reaching here is the assertion
    day = schedule.plan([{"name": "X", "frequency": "twice daily",
                          "service_date": "9999-12-30", "duration": "7 days"}])
    assert day is not None


def test_screens_survive_a_card_already_holding_a_bad_value():
    """Vaults restored before the import was fixed may already hold one."""
    from test_bill_screen import _app, offline_vault
    with offline_vault() as (con, alice, _):
        db.save_profile(con, alice["id"], {"full_name": "Alice", "organ_donor": "maybe",
                                           "day_start": "banana", "blood_type": "Z+"})
        rid = db.add_record(con, kind="prescription", title="Rx",
                            service_date="9999-12-30", owner_id=alice["id"])
        db.add_medication(con, rid, {"name": "Warfarin", "frequency": "twice daily",
                                     "duration": "999999999 days"})
        at = _app(alice)
        assert not at.exception, [e.value for e in at.exception]
        assert "Restore it" in [b.label for b in at.button] or any(
            "Put a vault file back" in (u.label or "") for u in at.get("file_uploader"))


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
