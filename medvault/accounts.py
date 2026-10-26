#!/usr/bin/env python3
"""Who is using the vault, and what that lets them do.

Two roles, and the distinction between them is the point of the whole feature:

  patient    owns a vault. Files records, reads them, checks bills. Everything a patient
             files is marked SELF - useful to them, evidence to nobody.
  clinician  has an NPI checked against the national registry. Can confirm that a record
             matches what they actually issued, which moves it to VERIFIED.

What was deliberately not built: a clinician-only upload gate. Locking patients out of
filing their own paperwork would empty the vault on day one and leave the product waiting
for an adoption it cannot get. Provenance is shown instead of access being withheld, so an
unverified record is visible as unverified rather than absent.

Passwords are salted and hashed with PBKDF2. This is a student project and the honest
framing is that it is enough to stop casual snooping on a shared laptop and is not a
substitute for a real identity provider.
"""
import hashlib, os, secrets, time

ROLES = ("patient", "clinician")

# Labels are written to read correctly to whoever is looking - a patient at their own
# vault and a clinician reviewing it see the same badge and both find it true. "Filed by
# you" failed that: on a clinician's review screen it claimed they had filed records they
# were being asked to check.
PROVENANCE = {
    "SELF":     ("Self-filed",
                 "Uploaded by the patient from their own paperwork. Not independently checked."),
    "VERIFIED": ("Clinician-verified",
                 "A clinician with a registry-checked NPI confirmed this record."),
    "CLINICAL": ("Filed by a clinician",
                 "Uploaded directly by a clinician with a registry-checked NPI."),
}

ITERATIONS = 120_000


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return salt, digest.hex()


def verify_password(password, salt, expected):
    _, got = hash_password(password, salt)
    return secrets.compare_digest(got, expected)


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT UNIQUE NOT NULL,
    role           TEXT NOT NULL,
    display_name   TEXT,
    pw_salt        TEXT NOT NULL,
    pw_hash        TEXT NOT NULL,
    npi            TEXT,
    npi_name       TEXT,
    npi_specialty  TEXT,
    npi_license    TEXT,
    npi_state      TEXT,
    npi_checked_at REAL,
    created_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email);
"""


def ensure(con):
    con.executescript(SCHEMA)
    con.commit()


def create(con, *, email, password, role, display_name=None, npi_record=None):
    """Make an account. Returns (account, problem)."""
    email = (email or "").strip().lower()
    if "@" not in email or len(email) < 5:
        return None, "That does not look like an email address."
    if len(password or "") < 8:
        return None, "Use at least 8 characters."
    if role not in ROLES:
        return None, "Unknown role."
    if role == "clinician" and not npi_record:
        return None, "A clinician account needs a verified NPI."
    if con.execute("SELECT 1 FROM accounts WHERE email = ?", (email,)).fetchone():
        return None, "An account already exists for that email."

    # The first version of the sign-up form asked for the password before the name, and a
    # text field directly under a password field reads as "confirm password". Someone typed
    # their password into the name box, and it was then stored in the clear and printed at
    # the top of every screen. The form order is fixed; this refuses the input anyway,
    # because a form can be re-ordered again by someone who does not know why it is so.
    if display_name and display_name.strip() == (password or ""):
        return None, ("That is your password, not your name — it would be shown on your "
                      "health card. Put your name in that box.")

    salt, digest = hash_password(password)
    n = npi_record or {}
    cur = con.execute(
        "INSERT INTO accounts (email, role, display_name, pw_salt, pw_hash, npi, npi_name,"
        " npi_specialty, npi_license, npi_state, npi_checked_at, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (email, role, display_name or n.get("name"), salt, digest, n.get("npi"),
         n.get("name"), n.get("specialty"), n.get("license"), n.get("license_state"),
         time.time() if npi_record else None, time.time()))
    con.commit()
    return get(con, cur.lastrowid), None


def get(con, account_id):
    row = con.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return dict(row) if row else None


def sign_in(con, email, password):
    """Returns (account, problem). The problem text never says which half was wrong."""
    row = con.execute("SELECT * FROM accounts WHERE email = ?",
                      ((email or "").strip().lower(),)).fetchone()
    if not row or not verify_password(password or "", row["pw_salt"], row["pw_hash"]):
        return None, "That email and password do not match an account."
    return dict(row), None


def is_verified_clinician(account):
    return bool(account and account.get("role") == "clinician" and account.get("npi_checked_at"))
