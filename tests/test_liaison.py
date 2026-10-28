#!/usr/bin/env python3
"""The Liaison and the care team it reports to.

Two promises are tested here, and they are the reason this agent can exist at all.

It never decides anybody needs care. Every sentence it can produce is scanned for triage
language, because "you should go to hospital" from software is either a medical device or
a liability, and this project is neither.

It reports only to doctors the patient chose. Before the care team existed, any clinician
account could read every patient's records; an agent that "updates the doctor" built on
that would have broadcast to all of them.
"""
import datetime
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import accounts   # noqa: E402
import careteam   # noqa: E402
import db         # noqa: E402
import liaison    # noqa: E402

TODAY = datetime.date(2026, 10, 28)
NPI = {"npi": "1234567890", "name": "Dr. Amara Osei", "credential": "MD",
       "specialty": "Family Medicine", "license": "X1", "license_state": "MA",
       "city": "Boston", "state": "MA", "status": "A"}

TRIAGE = ("go to the hospital", "go to hospital", "visit the hospital", "go to a hospital",
          "go to the emergency", "call 911", "you need to see", "you must see",
          "you should see a doctor", "seek medical attention", "seek immediate",
          "urgent care", "is urgent", "you need a check", "book an appointment now",
          "requires a hospital", "needs hospital")


def world():
    con = db.connect(tempfile.mktemp(suffix=".db"))
    pat, _ = accounts.create(con, email="pat@example.com", password="12345678",
                             role="patient", display_name="Asha Raman")
    other, _ = accounts.create(con, email="other@example.com", password="12345678",
                               role="patient", display_name="Someone Else")
    doc, problem = accounts.create(con, email="dr.osei@example.com", password="12345678",
                                   role="clinician", display_name="Dr. Amara Osei",
                                   npi_record=NPI)
    assert not problem, problem
    stranger, _ = accounts.create(con, email="dr.two@example.com", password="12345678",
                                  role="clinician", display_name="Dr. Two",
                                  npi_record={**NPI, "npi": "9999999999"})
    return con, pat, other, doc, stranger


# ---- the care team -------------------------------------------------------------

def test_a_patient_can_add_a_verified_clinician():
    con, pat, _, doc, _ = world()
    added, problem = careteam.add(con, pat["id"], "dr.osei@example.com")

    assert problem is None and added["id"] == doc["id"]
    assert [c["id"] for c in careteam.team(con, pat["id"])] == [doc["id"]]


def test_another_patients_email_cannot_be_added():
    """A typo'd email that matches a patient account must not hand that patient your
    records."""
    con, pat, other, _, _ = world()
    added, problem = careteam.add(con, pat["id"], "other@example.com")

    assert added is None and problem
    assert careteam.team(con, pat["id"]) == []


def test_the_refusal_does_not_reveal_whether_an_email_is_registered():
    con, pat, _, _, _ = world()
    _, for_patient = careteam.add(con, pat["id"], "other@example.com")
    _, for_nobody = careteam.add(con, pat["id"], "nobody@example.com")

    assert for_patient == for_nobody, "the message tells a stranger who uses this service"


def test_a_clinician_sees_only_the_patients_who_chose_them():
    con, pat, other, doc, stranger = world()
    careteam.add(con, pat["id"], "dr.osei@example.com")

    assert [p["id"] for p in careteam.patients(con, doc["id"])] == [pat["id"]]
    assert careteam.patients(con, stranger["id"]) == []
    assert not careteam.may_see(con, stranger["id"], pat["id"])
    assert not careteam.may_see(con, doc["id"], other["id"])


def test_removing_a_clinician_takes_effect_immediately():
    con, pat, _, doc, _ = world()
    careteam.add(con, pat["id"], "dr.osei@example.com")
    careteam.remove(con, pat["id"], doc["id"])

    assert not careteam.may_see(con, doc["id"], pat["id"])
    assert careteam.patients(con, doc["id"]) == []


def test_only_a_patient_can_build_a_team():
    con, _, _, doc, _ = world()
    _, problem = careteam.add(con, doc["id"], "dr.two@example.com")
    assert problem


def test_adding_twice_does_not_duplicate():
    con, pat, _, _, _ = world()
    careteam.add(con, pat["id"], "dr.osei@example.com")
    careteam.add(con, pat["id"], "DR.OSEI@example.com ")
    assert len(careteam.team(con, pat["id"])) == 1


# ---- follow-ups ---------------------------------------------------------------

def test_an_overdue_follow_up_is_found():
    con, pat, _, _, _ = world()
    db.add_record(con, kind="visit", title="Discharge summary", service_date="2026-08-01",
                  summary="Sinusitis. Follow up in 2 weeks if not improved.",
                  owner_id=pat["id"])

    found = liaison.follow_ups(con, pat["id"], TODAY)

    assert len(found) == 1
    assert found[0]["due"] == datetime.date(2026, 8, 15)


def test_a_follow_up_not_yet_due_is_not_raised():
    con, pat, _, _, _ = world()
    db.add_record(con, kind="visit", title="Clinic note", service_date="2026-10-20",
                  summary="Review in 6 weeks.", owner_id=pat["id"])
    assert liaison.follow_ups(con, pat["id"], TODAY) == []


def test_a_follow_up_is_not_raised_when_something_was_filed_since():
    con, pat, _, _, _ = world()
    db.add_record(con, kind="visit", title="Discharge summary", service_date="2026-08-01",
                  summary="Follow up in 2 weeks.", owner_id=pat["id"])
    db.add_record(con, kind="visit", title="Follow-up visit", service_date="2026-08-16",
                  owner_id=pat["id"])
    assert liaison.follow_ups(con, pat["id"], TODAY) == []


def test_one_patients_follow_up_is_not_reported_for_another():
    con, pat, other, _, _ = world()
    db.add_record(con, kind="visit", title="Discharge", service_date="2026-08-01",
                  summary="Follow up in 2 weeks.", owner_id=other["id"])
    assert liaison.follow_ups(con, pat["id"], TODAY) == []


def test_an_as_needed_medicine_is_not_raised_as_undosable():
    """It has an instruction - 'as needed' - just not a clock. Flagging it would tell the
    patient to ask about something that is fine."""
    con, pat, _, _, _ = world()
    rid = db.add_record(con, kind="prescription", title="Script", owner_id=pat["id"])
    db.add_medication(con, rid, {"name": "Ibuprofen", "frequency": "every 8 hours as needed",
                                 "reason": "pain"})
    assert not [i for i in liaison.update(con, pat["id"], TODAY) if i["kind"] == "dosing"]


def test_an_unreadable_dose_is_raised():
    con, pat, _, _, _ = world()
    rid = db.add_record(con, kind="prescription", title="Script", owner_id=pat["id"])
    db.add_medication(con, rid, {"name": "Mystery", "frequency": "take as directed",
                                 "reason": "unknown"})
    assert [i for i in liaison.update(con, pat["id"], TODAY) if i["kind"] == "dosing"]


# ---- the line it never crosses ---------------------------------------------------

def _everything_it_can_say():
    con, pat, _, _, _ = world()
    db.save_profile(con, pat["id"], {"allergies": "Penicillin (rash)"})
    db.add_record(con, kind="visit", title="Discharge", service_date="2026-08-01",
                  summary="Follow up in 2 weeks. Repeat bloods in 1 month.",
                  owner_id=pat["id"])
    rid = db.add_record(con, kind="prescription", title="Script", service_date="2026-03-14",
                        owner_id=pat["id"])
    for m in ({"name": "Amoxicillin", "frequency": "twice daily", "duration": "7 days"},
              {"name": "Amoxicillin", "frequency": "twice daily"},
              {"name": "Mystery", "frequency": "take as directed"}):
        db.add_medication(con, rid, m)
    items = liaison.update(con, pat["id"], TODAY)
    return items, liaison.message(pat, items, TODAY)


def test_it_produced_something_to_scan():
    items, _ = _everything_it_can_say()
    kinds = {i["kind"] for i in items}
    assert {"follow_up", "dosing"} <= kinds, kinds


def test_nothing_it_says_is_triage():
    """The agent reports what records say. It never tells anyone they need care."""
    items, text = _everything_it_can_say()
    corpus = (text + " ".join(i["title"] + " " + i["body"] for i in items)).lower()
    for phrase in TRIAGE:
        assert phrase not in corpus, f"the Liaison said {phrase!r}"


def test_the_message_says_where_it_came_from():
    _, text = _everything_it_can_say()
    assert "not from a symptom check" in text
    assert "only what I have uploaded" in text


def test_the_message_carries_no_html():
    _, text = _everything_it_can_say()
    assert "<b>" not in text and "</" not in text




# ---- what a clinician can see at all ---------------------------------------------
# The care team would mean nothing if the clinician's other screens ignored it. They did:
# the review queue and the Records tab listed every patient's records to every verified
# clinician, while the Card screen told patients "nobody else can".

def _filed(con, owner, title):
    return db.add_record(con, kind="lab", title=title, owner_id=owner)


def test_a_clinician_nobody_chose_sees_an_empty_queue_not_everyone():
    """The failure that matters: an empty team must mean nothing, never all."""
    con, pat, other, doc, _ = world()
    _filed(con, pat["id"], "Asha's panel")
    _filed(con, other["id"], "Someone's panel")

    team = [p["id"] for p in careteam.patients(con, doc["id"])]
    assert team == []
    assert db.pending_verification(con, owner_ids=team) == []
    assert db.list_records(con, owner_ids=team) == []
    assert db.counts_by_kind(con, owner_ids=team) == {}


def test_a_clinician_sees_only_their_care_teams_records():
    con, pat, other, doc, _ = world()
    _filed(con, pat["id"], "Asha's panel")
    _filed(con, other["id"], "Someone's panel")
    careteam.add(con, pat["id"], "dr.osei@example.com")

    team = [p["id"] for p in careteam.patients(con, doc["id"])]
    titles = {r["title"] for r in db.pending_verification(con, owner_ids=team)}
    assert titles == {"Asha's panel"}
    assert {r["title"] for r in db.list_records(con, owner_ids=team)} == {"Asha's panel"}


def test_removal_empties_the_queue_on_the_next_screen():
    con, pat, _, doc, _ = world()
    _filed(con, pat["id"], "Asha's panel")
    careteam.add(con, pat["id"], "dr.osei@example.com")
    careteam.remove(con, pat["id"], doc["id"])

    team = [p["id"] for p in careteam.patients(con, doc["id"])]
    assert db.pending_verification(con, owner_ids=team) == []


def test_the_queue_carries_the_owner_so_the_screen_can_check_it():
    """The second lock in the review screen reads owner_id off each row."""
    con, pat, _, doc, _ = world()
    _filed(con, pat["id"], "Asha's panel")
    careteam.add(con, pat["id"], "dr.osei@example.com")
    row = db.pending_verification(con, owner_ids=[pat["id"]])[0]
    assert row["owner_id"] == pat["id"]


def test_no_clinician_screen_in_the_app_reaches_for_every_record():
    """Read the source: the unscoped call is how the leak worked.

    The first version of this test looked for one spelling - "None if clinician_view()" -
    and missed the header, which spelled the same check "None if
    accounts.is_verified_clinician(account)" and showed a clinician the record count for
    the whole server. So this looks for the shape, not the spelling: any of the three
    record queries called with a bare None for its owner."""
    import re
    source = (pathlib.Path(__file__).resolve().parent.parent / "app.py").read_text()
    unscoped = re.findall(
        r"(?:counts_by_kind|list_records|pending_verification)\(\s*con\s*(?:,\s*None\b|\))"
        r"|owner_id\s*=\s*None|None if (?:clinician_view|accounts\.is_verified_clinician)",
        source)
    assert not unscoped, f"unscoped record queries in app.py: {unscoped}"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
