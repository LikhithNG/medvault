#!/usr/bin/env python3
"""Who a patient has chosen to share their records with.

This is the grant mechanism CAVEATS.md section 7 said was missing: "a clinician account
can currently read every patient's records, and there is no mechanism yet for a patient to
grant or revoke that access." The Liaison agent reports a patient's outstanding items to
their doctors - and an agent that reports to *every* clinician on the server would turn
that gap into a broadcast. So the Liaison is built on this, and reports only to a care
team the patient assembled and can take apart.

The rules are the ones a patient would assume without being told:

  * Only a patient can add someone, and only to their own team.
  * Only an account whose NPI was checked against the national registry can be added.
    A typo'd email that happens to match a patient account must not hand that patient
    another patient's records.
  * Removing someone takes effect immediately - the next screen they load no longer has
    you on it.
"""
import time

import accounts


def add(con, patient_id, clinician_email):
    """Put a clinician on a patient's team. Returns (clinician, problem)."""
    patient = accounts.get(con, patient_id)
    if not patient or patient.get("role") != "patient":
        return None, "Only a patient can build a care team."
    email = (clinician_email or "").strip().lower()
    if "@" not in email:
        return None, "That does not look like an email address."

    row = con.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
    clinician = accounts.get(con, row["id"]) if row else None
    # Deliberately one message for "no account" and "not a verified clinician": telling a
    # stranger which emails belong to patients would leak who uses this service.
    if not clinician or not accounts.is_verified_clinician(clinician):
        return None, ("No verified clinician has that email. They need a MedVault "
                      "clinician account with a registry-checked NPI first.")
    if clinician["id"] == patient_id:
        return None, "You cannot add yourself."

    con.execute("INSERT OR IGNORE INTO care_team (patient_id, clinician_id, added_at) "
                "VALUES (?,?,?)", (patient_id, clinician["id"], time.time()))
    con.commit()
    return clinician, None


def remove(con, patient_id, clinician_id):
    """Take a clinician off the team, and forget when they signed in: that history was
    about access the patient has now withdrawn."""
    con.execute("DELETE FROM care_team WHERE patient_id = ? AND clinician_id = ?",
                (patient_id, clinician_id))
    con.execute("DELETE FROM care_views WHERE patient_id = ? AND clinician_id = ?",
                (patient_id, clinician_id))
    con.commit()


def team(con, patient_id):
    """The clinicians this patient has chosen, oldest first."""
    rows = con.execute("SELECT clinician_id FROM care_team WHERE patient_id = ? "
                       "ORDER BY added_at", (patient_id,)).fetchall()
    return [a for a in (accounts.get(con, r["clinician_id"]) for r in rows) if a]


def patients(con, clinician_id):
    """The patients who have chosen this clinician. Nobody else."""
    rows = con.execute("SELECT patient_id FROM care_team WHERE clinician_id = ? "
                       "ORDER BY added_at", (clinician_id,)).fetchall()
    return [a for a in (accounts.get(con, r["patient_id"]) for r in rows) if a]


def may_see(con, clinician_id, patient_id):
    """Whether this clinician is on this patient's team, right now."""
    return con.execute("SELECT 1 FROM care_team WHERE clinician_id = ? AND patient_id = ?",
                       (clinician_id, patient_id)).fetchone() is not None


# Screens redraw on every click, so a clinician reading for ten minutes would otherwise
# count as hundreds of visits. Anything within this long of the last one is the same visit.
VISIT_GAP_S = 30 * 60


def note_view(con, clinician_id, patient_id, now=None):
    """Record that a clinician signed in with access to this patient's records. Returns
    whether it counted as a new sign-in.

    What it records is exactly that: the clinician's screens load their care team's
    records on sign-in, so this is when they had them, not proof of which they read. The
    patient can see it - the other half of choosing who may. Only a clinician on the team
    right now is recorded: a row for anyone else would read as if they had been given
    access. One statement, so two of their tabs opening at once cannot collide.
    """
    if not may_see(con, clinician_id, patient_id):
        return False
    now = time.time() if now is None else now
    cur = con.execute(
        "INSERT INTO care_views (patient_id, clinician_id, last_seen_at, visits) "
        "VALUES (?,?,?,1) ON CONFLICT(patient_id, clinician_id) DO UPDATE SET "
        "last_seen_at = excluded.last_seen_at, visits = care_views.visits + 1 "
        "WHERE excluded.last_seen_at - care_views.last_seen_at >= ?",
        (patient_id, clinician_id, now, VISIT_GAP_S))
    con.commit()
    return (cur.rowcount or 0) > 0


def last_seen(con, patient_id):
    """When each clinician last saw this patient's records, and how many visits in all."""
    rows = con.execute("SELECT clinician_id, last_seen_at, visits FROM care_views "
                       "WHERE patient_id = ?", (patient_id,)).fetchall()
    return {r["clinician_id"]: {"last_seen_at": r["last_seen_at"], "visits": r["visits"]}
            for r in rows}
