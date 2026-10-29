#!/usr/bin/env python3
"""Seed the presentation vault: one synthetic patient, one demo clinician, the paperwork the
demo walks through - and check that the agents say what the demo needs them to say.

    python3 tools/seed_demo.py --db demo_backup.db    # a local file (the fallback copy)
    python3 tools/seed_demo.py --live                 # the hosted database
    python3 tools/seed_demo.py --live --verify        # check only; writes nothing

Writes only through the app's own functions, only adds, and refuses to run at all if either
demo account already exists - so it can never overwrite or duplicate anything. Passwords are
made once into demo_accounts.txt (git-ignored, readable by you alone) and reused, so the live
site and the local copy share them. Nothing here is a real person: the emails are on the
reserved .test domain and the clinician's NPI is ten zeros with a licence of DEMO.

The story, for the demo. Maya fell at home in March and was seen in Doylestown Hospital's
emergency department: a head CT, a chest X-ray and blood tests, all filed. The bill that
followed (samples/bills/01_overcharged) also charges a lumbar MRI that nothing in her
records mentions. In October her GP saw her for an asthma flare and asked to see her again
in a week; nothing has been filed since. The sample prescription photo is left out on
purpose - it is uploaded live, and its penicillin-family antibiotic meets her allergy.
"""
import argparse
import datetime
import os
import pathlib
import secrets
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

CREDENTIALS = ROOT / "demo_accounts.txt"
PRESENTATION = datetime.date(2026, 10, 31)

PATIENT = {"email": "maya@medvault-demo.test", "role": "patient",
           "display_name": "Maya Thompson"}
CLINICIAN = {"email": "dr.nair@medvault-demo.test", "role": "clinician",
             "display_name": "Dr. Priya Nair",
             "npi_record": {"npi": "0000000000", "name": "PRIYA NAIR",
                            "specialty": "Family Medicine", "license": "DEMO",
                            "license_state": "MA"}}

GP = "Dr. Priya Nair, Back Bay Family Practice"
ED = "Doylestown Hospital"

PROFILE = {
    "full_name": "Maya Thompson", "date_of_birth": "1994-06-12", "blood_type": "O+",
    "allergies": "Penicillin (rash)", "conditions": "Asthma",
    "emergency_name": "Daniel Thompson", "emergency_relation": "brother",
    "emergency_phone": "+1 617 555 0148",
    "insurer": "Blue Cross", "member_id": "MVD 4471 902",
    "gp_name": "Dr. Priya Nair", "gp_phone": "+1 617 555 0190",
    "organ_donor": "Yes", "notes": "Carries a reliever inhaler.",
}

RECORDS = [
    {"kind": "visit", "title": "Emergency department visit", "date": "2026-03-14",
     "provider": ED,
     "summary": "Seen after a fall at home with a headache. Imaging and blood tests were "
                "normal, and she was discharged the same day."},
    {"kind": "imaging", "title": "CT head (no contrast)", "date": "2026-03-14",
     "provider": ED, "summary": "No bleeding or fracture seen."},
    {"kind": "imaging", "title": "Chest X-ray", "date": "2026-03-14", "provider": ED,
     "summary": "Two views. Lungs clear; no rib fracture."},
    {"kind": "lab", "title": "Basic metabolic panel", "date": "2026-03-14", "provider": ED,
     "summary": "All values within the normal range."},
    {"kind": "prescription", "title": "Discharge prescription", "date": "2026-03-14",
     "provider": ED, "summary": "Ibuprofen for pain after the fall.",
     "meds": [{"name": "Ibuprofen", "dose": "400 mg", "frequency": "every 8 hours as needed",
               "duration": "5 days", "reason": "Pain"}]},
    {"kind": "visit", "title": "Clinic visit: asthma flare", "date": "2026-10-12",
     "provider": GP,
     "summary": "Seen for wheeze and a night-time cough after a cold; peak flow was lower "
                "than usual. Started a short course of prednisone and a nightly "
                "montelukast, and kept the preventer inhaler. Follow up in 1 week."},
    {"kind": "prescription", "title": "Asthma prescriptions", "date": "2026-10-12",
     "provider": GP, "summary": "Inhalers, prednisone and montelukast for an asthma flare.",
     "meds": [
         {"name": "Fluticasone inhaler", "dose": "2 puffs", "frequency": "twice daily",
          "reason": "Asthma (preventer)"},
         {"name": "Albuterol inhaler", "dose": "2 puffs",
          "frequency": "every 4 to 6 hours as needed",
          "reason": "Wheeze or shortness of breath (reliever)"},
         {"name": "Prednisone", "dose": "40 mg", "frequency": "once daily",
          "duration": "5 days", "reason": "Asthma flare"},
         {"name": "Montelukast", "dose": "10 mg", "frequency": "once daily at bedtime",
          "duration": "30 days", "reason": "Asthma"}]},
]


class AlreadySeeded(Exception):
    """A demo account exists already. Nothing has been written."""


def passwords(path=CREDENTIALS):
    """The two demo passwords: read from `path`, or made and written there once (0600)."""
    path = pathlib.Path(path)
    if path.exists():
        found = {}
        for line in path.read_text().splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] in ("patient", "clinician"):
                found[parts[0]] = parts[2]
        if set(found) == {"patient", "clinician"}:
            return found
        raise SystemExit(f"{path} exists but does not hold both demo passwords - "
                         "move it aside rather than have it overwritten.")
    made = {"patient": secrets.token_urlsafe(16), "clinician": secrets.token_urlsafe(16)}
    text = ("MedVault presentation accounts - private, git-ignored, not for chat.\n"
            f"patient    {PATIENT['email']}    {made['patient']}\n"
            f"clinician  {CLINICIAN['email']}  {made['clinician']}\n")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return made


def _account_id(con, email):
    row = con.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
    return row["id"] if row else None


def seed(con, pw):
    """Write the demo vault. Raises AlreadySeeded, before writing anything, if either demo
    account exists. Returns the two account ids."""
    import accounts
    import careteam
    import db
    taken = [a["email"] for a in (PATIENT, CLINICIAN) if _account_id(con, a["email"])]
    if taken:
        raise AlreadySeeded(", ".join(taken))

    doctor, problem = accounts.create(con, email=CLINICIAN["email"], password=pw["clinician"],
                                      role="clinician", display_name=CLINICIAN["display_name"],
                                      npi_record=CLINICIAN["npi_record"])
    if problem:
        raise RuntimeError(f"clinician: {problem}")
    patient, problem = accounts.create(con, email=PATIENT["email"], password=pw["patient"],
                                       role="patient", display_name=PATIENT["display_name"])
    if problem:
        raise RuntimeError(f"patient: {problem}")
    db.save_profile(con, patient["id"], PROFILE)
    for r in RECORDS:
        rid = db.add_record(con, kind=r["kind"], title=r["title"], service_date=r["date"],
                            provider=r["provider"], summary=r["summary"],
                            owner_id=patient["id"])
        for m in r.get("meds", []):
            db.add_medication(con, rid, m)
    _, problem = careteam.add(con, patient["id"], CLINICIAN["email"])
    if problem:
        raise RuntimeError(f"care team: {problem}")
    con.commit()
    return {"patient": patient["id"], "clinician": doctor["id"]}


def _bill(name):
    import paste
    return paste.lines((ROOT / "samples" / "bills" / f"{name}.txt").read_text())


def check(con, today=PRESENTATION):
    """Everything the demo relies on, from the agents' own output. Returns the problems
    found - an empty list means the vault says what the demo will say."""
    import ask
    import careteam
    import crosscheck
    import db
    import liaison
    import schedule
    import schema
    problems = []
    pid, cid = _account_id(con, PATIENT["email"]), _account_id(con, CLINICIAN["email"])
    if not pid or not cid:
        return ["a demo account is missing"]

    if schema.missing_essentials(db.get_profile(con, pid)):
        problems.append("the emergency card is missing essentials")
    records = db.list_records(con, owner_id=pid, limit=100)
    if sorted(r["title"] for r in records) != sorted(r["title"] for r in RECORDS):
        problems.append(f"records differ: {sorted(r['title'] for r in records)}")
    meds = db.list_medications(con, active_only=True, owner_id=pid)
    if len(meds) != sum(len(r.get("meds", [])) for r in RECORDS):
        problems.append(f"{len(meds)} active medicines")
    if [p["id"] for p in careteam.patients(con, cid)] != [pid]:
        problems.append("the care team does not link the doctor to the patient")
    if len(db.pending_verification(con, owner_ids=[pid])) != len(RECORDS):
        problems.append("the doctor's confirmation queue is not every record")

    # The Liaison: exactly the three things the demo talks about, and nothing else.
    titles = [i["title"] for i in liaison.update(con, pid, today)]
    wanted = ["A follow-up from 12 October 2026 may be overdue",
              "Ibuprofen is still marked as current", "Prednisone is still marked as current"]
    if sorted(titles) != sorted(wanted):
        problems.append(f"the Liaison raises {titles}")

    # The Scheduler: the preventer twice a day, montelukast at bedtime, the reliever only
    # when needed, and the two finished courses kept off today's plan.
    day = schedule.plan(meds, today)
    doses = sorted((d["at"], d["med"]["name"]) for d in day["doses"])
    if doses != [("08:00", "Fluticasone inhaler"), ("20:00", "Fluticasone inhaler"),
                 ("22:00", "Montelukast")]:
        problems.append(f"today's plan is {doses}")
    if [e["med"]["name"] for e in day["as_needed"]] != ["Albuterol inhaler"]:
        problems.append(f"as needed: {[e['med']['name'] for e in day['as_needed']]}")
    if sorted(e["med"]["name"] for e in day["finished"]) != ["Ibuprofen", "Prednisone"]:
        problems.append(f"finished: {[e['med']['name'] for e in day['finished']]}")

    # The bills: which lines the records back, by the Checker's records check.
    for bill, expected in (
            ("01_overcharged", {"70450": "CT head (no contrast)", "71046": "Chest X-ray",
                                "80048": "Basic metabolic panel", "72148": None}),
            ("02_duplicate", {"99284": "Emergency department visit",
                              "70450": "CT head (no contrast)", "36415": None})):
        checked, _ = crosscheck.check_bill(_bill(bill), records)
        for line in checked:
            backed = line["matches"][0]["title"] if line["verdict"] == "MATCHED" else None
            if backed != expected[line["code"]]:
                problems.append(f"{bill} {line['code']}: backed by {backed!r}")

    # The Companion: a dose question names the GP and reads the record back.
    said = ask.decision(con, pid, "I missed last night's montelukast, should I take two?")
    if GP not in said["answer"] or "Montelukast · 10 mg" not in said["answer"]:
        problems.append("the prescriber answer does not name the GP and the dose")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--db", help="a local SQLite file")
    where.add_argument("--live", action="store_true", help="the hosted database")
    parser.add_argument("--verify", action="store_true", help="check only; write nothing")
    args = parser.parse_args()

    import db
    import store
    if args.live and not store.configured():
        raise SystemExit("--live, but no hosted database is configured in the environment.")
    con = db.connect() if args.live else db.connect(args.db)
    target = "the hosted database" if args.live else args.db
    if not args.verify:
        try:
            ids = seed(con, passwords())
        except AlreadySeeded as e:
            raise SystemExit(f"Not seeded - already in {target}: {e}. Nothing was written.")
        print(f"seeded {target}: patient {ids['patient']}, clinician {ids['clinician']} "
              f"(passwords in {CREDENTIALS.name})")
    failed = False
    for day in sorted({datetime.date.today(), PRESENTATION}):
        problems = check(con, day)
        print(f"check for {day}: " + ("everything the demo needs is there" if not problems
                                      else "; ".join(problems)))
        failed = failed or bool(problems)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
