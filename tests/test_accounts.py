#!/usr/bin/env python3
"""Roles, verification, and the line the product must not cross.

The feature exists so a patient cannot pass off something they typed as something a doctor
issued. These tests hold that line from both directions: a clinician account cannot be
created without a registry-checked NPI, and a self-filed record cannot acquire a verified
badge without a clinician id attached to it.

Run with  python3 tests/test_accounts.py
"""
import pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
import accounts, db                                                  # noqa: E402

REGISTRY = {"npi": "1255850020", "name": "A Real Provider", "specialty": "Internal Medicine",
            "license": "242854", "license_state": "MA"}


def fresh():
    return db.connect(tempfile.mktemp(suffix=".db"))


def test_a_password_is_never_stored_in_the_clear():
    con = fresh()
    acct, err = accounts.create(con, email="p@example.com", password="correct-horse",
                                role="patient")
    assert err is None
    row = con.execute("SELECT * FROM accounts WHERE id=?", (acct["id"],)).fetchone()
    assert "correct-horse" not in str(dict(row)), "the password appeared in the row"
    assert len(row["pw_hash"]) == 64 and row["pw_salt"]


def test_sign_in_works_and_a_wrong_password_does_not():
    con = fresh()
    accounts.create(con, email="p@example.com", password="correct-horse", role="patient")
    ok, err = accounts.sign_in(con, "P@Example.com ", "correct-horse")   # case and space
    assert ok and err is None, "email should be normalised"
    bad, err = accounts.sign_in(con, "p@example.com", "wrong")
    assert bad is None and "do not match" in err
    assert "password" not in err.lower().replace("password do not", ""), \
        "the error must not say which half was wrong"


def test_a_clinician_cannot_exist_without_a_checked_npi():
    con = fresh()
    acct, err = accounts.create(con, email="dr@example.com", password="12345678",
                                role="clinician")
    assert acct is None and "verified NPI" in err


def test_a_clinician_with_a_checked_npi_is_verified():
    con = fresh()
    acct, err = accounts.create(con, email="dr@example.com", password="12345678",
                                role="clinician", npi_record=REGISTRY)
    assert err is None
    assert accounts.is_verified_clinician(acct)
    assert acct["npi_license"] == "242854"


def test_a_patient_is_never_a_verified_clinician():
    con = fresh()
    acct, _ = accounts.create(con, email="p@example.com", password="12345678", role="patient")
    assert not accounts.is_verified_clinician(acct)


def test_what_a_patient_files_is_marked_self():
    con = fresh()
    rid = db.add_record(con, kind="lab", title="Blood panel")
    assert db.get_record(con, rid)["provenance"] == "SELF"


def test_verification_is_attributed_and_reversible():
    con = fresh()
    dr, _ = accounts.create(con, email="dr@example.com", password="12345678",
                            role="clinician", npi_record=REGISTRY)
    rid = db.add_record(con, kind="lab", title="Blood panel")

    db.verify_record(con, rid, dr["id"], note="matches what I issued")
    rec = db.get_record(con, rid)
    assert rec["provenance"] == "VERIFIED"
    assert rec["verified_by"] == dr["id"], "a badge must trace to an account"
    assert rec["verified_at"]

    db.unverify_record(con, rid, note="wrong patient")
    rec = db.get_record(con, rid)
    assert rec["provenance"] == "SELF", "withdrawing must demote, not delete"
    assert rec["verified_by"] is None


def test_a_verified_record_leaves_the_pending_queue():
    con = fresh()
    dr, _ = accounts.create(con, email="dr@example.com", password="12345678",
                            role="clinician", npi_record=REGISTRY)
    rid = db.add_record(con, kind="lab", title="Blood panel")
    assert len(db.pending_verification(con)) == 1
    db.verify_record(con, rid, dr["id"])
    assert db.pending_verification(con) == []


def test_two_accounts_cannot_share_an_email():
    con = fresh()
    accounts.create(con, email="p@example.com", password="12345678", role="patient")
    dupe, err = accounts.create(con, email="P@EXAMPLE.COM", password="12345678", role="patient")
    assert dupe is None and "already exists" in err


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
