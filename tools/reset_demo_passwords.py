#!/usr/bin/env python3
"""Give both demo accounts one new password, everywhere the demo runs.

    .venv/bin/python tools/reset_demo_passwords.py            # the hosted database, and demo_backup.db
    .venv/bin/python tools/reset_demo_passwords.py --db FILE  # one local file only, for a dry run

For when the password in demo_accounts.txt and the one in the hosted database have come
apart, and for rotating them after the presentation. It changes the two password columns
of the two demo accounts and nothing else, through the app's own hashing, then signs in
with the new password to prove it took. The new password is printed once, in your own
terminal, and written to demo_accounts.txt (git-ignored, readable by you alone) in the
layout tools/seed_demo.py reads, so the seed check and the screenshot script keep working.
"""
import argparse
import os
import pathlib
import secrets
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

CREDENTIALS = ROOT / "demo_accounts.txt"
BACKUP = ROOT / "demo_backup.db"
ACCOUNTS = (("patient", "maya@medvault-demo.test"), ("clinician", "dr.nair@medvault-demo.test"))
# Easy to type in front of an audience; strong enough for two synthetic accounts on the
# reserved .test domain, and meant to be rotated after the presentation.
WORDS = ("maple", "river", "cedar", "harbor", "willow", "summit", "meadow", "lantern",
         "falcon", "orchard", "comet", "garnet", "ember", "pebble", "canyon", "violet")


def new_password():
    return f"{secrets.choice(WORDS)}-{secrets.choice(WORDS)}-{secrets.randbelow(9000) + 1000}"


def reset(con, password):
    """Set the password on both demo accounts in `con`; returns the emails that now sign in."""
    import accounts
    for _, email in ACCOUNTS:
        salt, digest = accounts.hash_password(password)
        con.execute("UPDATE accounts SET pw_salt = ?, pw_hash = ? WHERE email = ?", (salt, digest, email))
    con.commit()
    return [email for _, email in ACCOUNTS if accounts.sign_in(con, email, password)[0]]


def save(password, path=CREDENTIALS):
    text = ("MedVault presentation accounts - private, git-ignored, not for chat.\n"
            + "".join(f"{role:<10} {email}    {password}\n" for role, email in ACCOUNTS))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", help="change only this local SQLite file (nothing hosted, no file written)")
    args = parser.parse_args()

    import db
    import store
    password = new_password()
    if args.db:
        targets = [(args.db, db.connect(args.db))]
    else:
        if not store.configured():
            raise SystemExit("No hosted database is configured in .env, so there is nothing live to change.")
        answer = input("This changes the demo passwords on the LIVE site. Type yes to go on: ")
        if answer.strip().lower() != "yes":
            raise SystemExit("Nothing changed.")
        targets = [("the live site", db.connect())]
        if BACKUP.exists():
            targets.append((BACKUP.name, db.connect(BACKUP)))

    for name, con in targets:
        working = reset(con, password)
        missing = [email for _, email in ACCOUNTS if email not in working]
        if missing:
            raise SystemExit(f"{name}: {', '.join(missing)} still cannot sign in. If the account is "
                             "not there at all, run tools/seed_demo.py for it.")
        print(f"{name}: both demo accounts sign in with the new password")

    if args.db:
        print("Dry run on a local file: demo_accounts.txt was left as it was.")
        return
    save(password)
    print(f"\nNew password for both accounts (also saved in {CREDENTIALS.name}):\n\n    {password}\n")


if __name__ == "__main__":
    main()
