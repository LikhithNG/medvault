#!/usr/bin/env python3
"""The presentation vault says exactly what the demo needs it to say.

tools/seed_demo.py writes one synthetic patient, one demo clinician and the paperwork behind
the demo, into a local file or the hosted database. These seed a throwaway file and check
the agents' own output on the presentation day: what the Liaison raises, what the Scheduler
plans, and which bill lines the records back. The same check runs against the live
database after seeding (seed_demo.py --verify), so a mistake there is caught before an
audience sees it.
"""
import datetime
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tools"))

import db           # noqa: E402
import seed_demo    # noqa: E402

PRESENTATION = datetime.date(2026, 10, 31)


def _seeded():
    con = db.connect(tempfile.mktemp(suffix=".db"))
    seed_demo.seed(con, {"patient": "patient-pass-1", "clinician": "doctor-pass-1"})
    return con


def test_the_seeded_vault_passes_its_own_check_on_the_day():
    assert seed_demo.check(_seeded(), PRESENTATION) == []


def test_the_check_holds_on_the_days_around_it():
    """Seeded on the 29th, rehearsed on the 30th, presented on the 31st."""
    con = _seeded()
    for day in (28, 29, 30, 31):
        assert seed_demo.check(con, datetime.date(2026, 10, day)) == [], day


def test_the_check_notices_when_something_is_missing():
    con = _seeded()
    con.execute("DELETE FROM care_team")
    con.commit()
    assert any("care team" in p for p in seed_demo.check(con, PRESENTATION))


def test_a_second_run_writes_nothing():
    con = _seeded()
    before = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    try:
        seed_demo.seed(con, {"patient": "patient-pass-1", "clinician": "doctor-pass-1"})
    except seed_demo.AlreadySeeded:
        pass
    else:
        raise AssertionError("seeding twice did not refuse")
    assert con.execute("SELECT COUNT(*) FROM records").fetchone()[0] == before


def test_passwords_are_made_once_kept_private_and_reused():
    path = pathlib.Path(tempfile.mkdtemp()) / "demo_accounts.txt"
    first = seed_demo.passwords(path)
    assert set(first) == {"patient", "clinician"}
    assert all(len(p) >= 16 for p in first.values())
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert seed_demo.passwords(path) == first, "the live site and the backup must share them"


def test_the_demo_accounts_cannot_be_mistaken_for_real_people():
    for account in (seed_demo.PATIENT, seed_demo.CLINICIAN):
        assert account["email"].endswith(".test"), "a reserved domain that cannot receive mail"
    assert seed_demo.CLINICIAN["npi_record"]["npi"] == "0000000000"
    assert seed_demo.CLINICIAN["npi_record"]["license"] == "DEMO"


def test_the_demo_documents_are_kept_for_the_live_upload():
    """The sample prescription photo is uploaded during the demo - its medicines must not
    be in the vault already, or the upload would only duplicate them."""
    names = {m["name"].lower() for r in seed_demo.RECORDS for m in r.get("meds", [])}
    assert not names & {"amoxicillin-clavulanate", "fluticasone propionate nasal spray"}


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
