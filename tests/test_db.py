#!/usr/bin/env python3
"""The vault must not lose a record, and must not hide an undated one.

Run with  python3 tests/test_db.py
"""
import pathlib, sys, tempfile

# The modules import each other flatly (import accounts, import gemini), the convention
# carried over from Itemized, so medvault/ itself goes on the path - not the repo root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))
import db                                                            # noqa: E402


def fresh():
    return db.connect(tempfile.mktemp(suffix=".db"))


def test_a_stored_record_comes_back_whole():
    # Arrange
    con = fresh()
    blob = b"\x89PNG fake scan bytes"

    # Act
    rid = db.add_record(con, kind="imaging", title="Chest X-ray",
                        service_date="2026-03-14", provider="Doylestown Hospital",
                        summary="Two views, reported clear.", file_name="xray.png",
                        file_mime="image/png", file_bytes=blob, read_by="gemini-3.6-flash")
    got = db.get_record(con, rid)

    # Assert — including the original file, which is the evidence half of the vault
    assert got["title"] == "Chest X-ray"
    assert got["provider"] == "Doylestown Hospital"
    assert got["file_bytes"] == blob, "the uploaded original must survive storage"
    assert got["read_by"] == "gemini-3.6-flash"


def test_an_undated_record_is_not_buried():
    # Arrange — a prescription with no printed date, added most recently
    con = fresh()
    db.add_record(con, kind="lab", title="Blood panel", service_date="2024-01-01")
    db.add_record(con, kind="prescription", title="Amoxicillin")   # no service_date

    # Act
    titles = [r["title"] for r in db.list_records(con)]

    # Assert — ORDER BY service_date alone would sort NULL last and hide it
    assert titles[0] == "Amoxicillin", f"undated record sank to {titles}"


def test_search_reaches_the_text_read_off_the_page():
    # Arrange
    con = fresh()
    db.add_record(con, kind="visit", title="Follow-up", raw_text="Patient reports tinnitus")

    # Act / Assert
    assert len(db.list_records(con, query="tinnitus")) == 1
    assert len(db.list_records(con, query="fracture")) == 0


def test_deleting_a_record_takes_its_medicines_with_it():
    # Arrange
    con = fresh()
    rid = db.add_record(con, kind="prescription", title="Course of antibiotics", owner_id=1)
    db.add_medication(con, rid, {"name": "Amoxicillin", "dose": "500 mg"})
    assert len(db.list_medications(con)) == 1

    # Act
    assert db.delete_record(con, rid, owner_id=1) is True

    # Assert — an orphaned medicine with no source is a medicine nobody can verify
    assert db.list_medications(con) == []


def test_medicines_go_with_the_record_even_without_foreign_keys():
    """The hosted vault's HTTP connection never turns foreign keys on, so ON DELETE
    CASCADE does nothing there. The delete has to take the medicines itself."""
    # Arrange
    con = fresh()
    con.execute("PRAGMA foreign_keys = OFF")
    rid = db.add_record(con, kind="prescription", title="Script", owner_id=1)
    db.add_medication(con, rid, {"name": "Fluticasone"})

    # Act
    db.delete_record(con, rid, owner_id=1)

    # Assert
    assert db.list_medications(con, active_only=False) == []
    assert con.execute("SELECT COUNT(*) AS n FROM medications").fetchone()["n"] == 0


def test_only_the_owner_can_delete_a_record():
    # Arrange
    con = fresh()
    mine = db.add_record(con, kind="lab", title="Mine", owner_id=1)
    db.add_medication(con, mine, {"name": "Iron"})

    # Act — someone else's id, holding the right record number
    deleted = db.delete_record(con, mine, owner_id=2)

    # Assert — nothing gone, medicines included
    assert deleted is False
    assert db.get_record(con, mine) is not None
    assert len(db.list_medications(con, owner_id=1)) == 1


def test_a_delete_must_say_whose_record_it_is():
    con = fresh()
    rid = db.add_record(con, kind="lab", title="Anyone's", owner_id=1)
    try:
        db.delete_record(con, rid, owner_id=None)
    except ValueError:
        pass
    else:
        raise AssertionError("a delete with no owner deleted something, or tried to")
    assert db.get_record(con, rid) is not None


def test_a_record_says_how_many_medicines_came_off_it():
    con = fresh()
    rid = db.add_record(con, kind="prescription", title="Script", owner_id=1)
    for name in ("Fluticasone", "Montelukast"):
        db.add_medication(con, rid, {"name": name})
    assert db.medicines_from(con, rid) == 2
    assert db.medicines_from(con, rid + 1) == 0


def test_profile_round_trips_and_overwrites():
    # Arrange — a card belongs to an account; there is no "the" profile
    con = fresh()
    me = 1

    # Act
    db.save_profile(con, me, {"blood_type": "O+", "allergies": "penicillin"})
    db.save_profile(con, me, {"blood_type": "O-"})

    # Assert
    p = db.get_profile(con, me)
    assert p["blood_type"] == "O-", "a second save must update, not duplicate"
    assert p["allergies"] == "penicillin", "an untouched field must survive"


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); passed += 1
    print(f"{passed} passed")
