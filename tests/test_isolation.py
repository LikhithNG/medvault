#!/usr/bin/env python3
"""Two accounts on one server must not see each other's medical records.

This is the defect these tests exist for, found by a second person signing up on a running
instance and being shown the first person's health card: name, blood type, allergies and
emergency contact. The profile table had no account column and list_records had no owner
filter, so one vault was served to everybody.

Run with  python3 tests/test_isolation.py
"""
import pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))
import accounts, db                                                  # noqa: E402


def two_patients():
    con = db.connect(tempfile.mktemp(suffix=".db"))
    a, _ = accounts.create(con, email="a@example.com", password="12345678", role="patient")
    b, _ = accounts.create(con, email="b@example.com", password="12345678", role="patient")
    return con, a["id"], b["id"]


def test_one_patients_card_is_not_shown_to_another():
    con, a, b = two_patients()
    db.save_profile(con, a, {"full_name": "Patient A", "blood_type": "O+",
                             "allergies": "penicillin"})

    assert db.get_profile(con, a)["full_name"] == "Patient A"
    assert db.get_profile(con, b) == {}, "B was shown A's health card"


def test_two_cards_do_not_overwrite_each_other():
    con, a, b = two_patients()
    db.save_profile(con, a, {"blood_type": "O+"})
    db.save_profile(con, b, {"blood_type": "AB-"})

    assert db.get_profile(con, a)["blood_type"] == "O+"
    assert db.get_profile(con, b)["blood_type"] == "AB-"


def test_one_patients_records_are_not_listed_to_another():
    con, a, b = two_patients()
    db.add_record(con, kind="lab", title="A's blood panel", owner_id=a)
    db.add_record(con, kind="imaging", title="B's knee MRI", owner_id=b)

    assert [r["title"] for r in db.list_records(con, owner_id=a)] == ["A's blood panel"]
    assert [r["title"] for r in db.list_records(con, owner_id=b)] == ["B's knee MRI"]


def test_search_cannot_reach_across_accounts():
    con, a, b = two_patients()
    db.add_record(con, kind="visit", title="Consultation", owner_id=a,
                  raw_text="patient reports tinnitus")

    assert len(db.list_records(con, query="tinnitus", owner_id=a)) == 1
    assert db.list_records(con, query="tinnitus", owner_id=b) == [], \
        "B found A's notes by searching"


def test_counts_are_per_account():
    con, a, b = two_patients()
    for i in range(3):
        db.add_record(con, kind="lab", title=f"A lab {i}", owner_id=a)
    db.add_record(con, kind="lab", title="B lab", owner_id=b)

    assert sum(db.counts_by_kind(con, a).values()) == 3
    assert sum(db.counts_by_kind(con, b).values()) == 1


def test_medicines_follow_the_record_they_came_from():
    con, a, b = two_patients()
    ra = db.add_record(con, kind="prescription", title="A's course", owner_id=a)
    db.add_medication(con, ra, {"name": "Amoxicillin"})

    assert [m["name"] for m in db.list_medications(con, owner_id=a)] == ["Amoxicillin"]
    assert db.list_medications(con, owner_id=b) == [], "B was shown A's medicines"


def test_a_clinician_reads_across_patients_on_purpose():
    # The review queue is the one place an unscoped read is correct: confirming a record
    # means looking at records that are not yours.
    con, a, b = two_patients()
    db.add_record(con, kind="lab", title="A lab", owner_id=a)
    db.add_record(con, kind="lab", title="B lab", owner_id=b)

    assert len(db.list_records(con, owner_id=None)) == 2
    assert len(db.pending_verification(con)) == 2


def test_an_old_vault_keeps_its_card_when_accounts_arrive():
    # The profile table predates accounts. Migrating must hand the existing rows to the
    # first patient rather than dropping them.
    path = tempfile.mktemp(suffix=".db")
    con = db.connect(path)
    con.execute("DROP TABLE profile")
    con.execute("CREATE TABLE profile (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO profile VALUES ('full_name','Legacy Patient')")
    con.commit()
    con.close()

    con = db.connect(path)                      # migration runs here
    first, _ = accounts.create(con, email="only@example.com", password="12345678",
                               role="patient")
    con.close()
    con = db.connect(path)
    cols = {r["name"] for r in con.execute("PRAGMA table_info(profile)")}
    assert "account_id" in cols
    kept = con.execute("SELECT value FROM profile WHERE key='full_name'").fetchone()
    assert kept and kept["value"] == "Legacy Patient", "the existing card was dropped"





def test_an_export_holds_one_account_and_not_the_other():
    """export_vault used to take no account id at all. It called get_profile(con), which
    has not accepted that since this file was written, so it raised TypeError and had
    plainly never been called — and it called list_records with no owner filter, which
    would have written every account on the server into one file. A dead function kept a
    live defect."""
    import json as _json
    con, a, b = two_patients()
    db.save_profile(con, a, {"full_name": "Patient A"})
    db.add_record(con, kind="lab", title="A's blood panel", owner_id=a)
    db.add_record(con, kind="imaging", title="B's knee MRI", owner_id=b)

    out = db.export_vault(con, a)

    assert "A's blood panel" in out
    assert "B's knee MRI" not in out, "one patient's export held another's records"
    assert _json.loads(out)["profile"]["full_name"] == "Patient A"


def test_an_export_cannot_be_taken_without_naming_an_account():
    con, _, _ = two_patients()
    try:
        db.export_vault(con, None)
    except ValueError:
        return
    raise AssertionError("export_vault accepted no account id")


def test_a_restored_vault_lands_in_the_importing_account_only():
    con, a, b = two_patients()
    db.add_record(con, kind="lab", title="A's blood panel", service_date="2026-03-14",
                  owner_id=a)
    payload = db.export_vault(con, a)

    done = db.import_vault(con, b, payload)

    assert done["records_added"] == 1
    assert [r["title"] for r in db.list_records(con, owner_id=b)] == ["A's blood panel"]
    assert len(db.list_records(con, owner_id=a)) == 1, "the source account changed"


def test_restoring_the_same_file_twice_does_not_duplicate():
    con, a, b = two_patients()
    db.add_record(con, kind="lab", title="Blood panel", service_date="2026-03-14",
                  owner_id=a)
    payload = db.export_vault(con, a)

    db.import_vault(con, b, payload)
    second = db.import_vault(con, b, payload)

    assert second["records_added"] == 0 and second["records_skipped"] == 1
    assert len(db.list_records(con, owner_id=b)) == 1


def test_a_clinician_confirmation_does_not_travel_with_the_file():
    """The verifying account does not exist on the machine the file lands on, so the
    badge would be a claim with nothing behind it."""
    con, a, b = two_patients()
    rid = db.add_record(con, kind="lab", title="Confirmed panel", owner_id=a,
                        provenance="VERIFIED")
    payload = db.export_vault(con, a)

    db.import_vault(con, b, payload)

    assert db.list_records(con, owner_id=b)[0]["provenance"] == "SELF"


def test_a_file_that_is_not_an_export_is_refused():
    con, a, _ = two_patients()
    for junk in ('{"something": "else"}', '[]'):
        try:
            db.import_vault(con, a, junk)
        except ValueError:
            continue
        raise AssertionError(f"accepted {junk}")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
