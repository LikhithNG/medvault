#!/usr/bin/env python3
"""How many AI reads each account may start in a day, and how many the whole site may.

The reader runs on the free Gemini tier, which allows about 20 requests a day per model
(gemini.py). Six models make roughly 120 a day for the entire site, shared by every account,
and nothing stopped one account from spending all of them. On the day of a presentation, a
room of people opening the link could switch the AI off for everybody - the presenter too.

So each account gets a daily allowance, and the site a ceiling below the provider's, which
leaves room for the accounts listed in MEDVAULT_UNCAPPED (the presenter's) once the public
has used theirs. An "AI read" is one thing a person starts that asks a model: reading a
document, reading a bill, or a question the Companion sends to one. An emergency or a dose
question never reaches a model, so it is never counted and never refused.

A read is taken - checked and counted in one statement - before the model is asked, so a
request that fails or raises is still counted, and two tabs cannot both take the last one.

This shares the quota out; it does not stop abuse. An account costs an email-shaped string
and a password, so somebody who wants more reads can make more accounts, and the site
ceiling is the limit that actually holds. A listed address is matched on the account's
email, which is not verified, so list only addresses already registered on the site.

What is kept is an account, a date and a count - see db.ai_use.
"""
import datetime
import logging
import os
from dataclasses import dataclass

import db

log = logging.getLogger(__name__)

# One AI read is usually one request, and two when a model has to be retried. Fifty
# public reads a day stay well inside 120 requests and leave room for the listed accounts.
PER_ACCOUNT = 10
SITE = 50
# Below this many left, the screen says how many. Above it, a count is noise.
LOW = 3

# Google's daily quotas restart at midnight Pacific, so this one does too.
try:
    from zoneinfo import ZoneInfo
    RESETS = ZoneInfo("America/Los_Angeles")
except Exception:            # noqa: BLE001 - no tz database here: Pacific standard time
    RESETS = datetime.timezone(datetime.timedelta(hours=-8))


@dataclass(frozen=True)
class Allowance:
    used: int               # this account's AI reads today
    limit: int | None       # None: a listed account, never refused
    site_used: int
    site_limit: int

    @property
    def left(self):
        return None if self.limit is None else max(self.limit - self.used, 0)

    @property
    def refused(self):
        """Why no more may be started today - "account" or "site" - or None if more may."""
        if self.limit is None:
            return None
        if self.used >= self.limit:
            return "account"
        if self.site_used >= self.site_limit:
            return "site"
        return None


def today():
    return datetime.datetime.now(RESETS).date().isoformat()


def _whole(raw, default, name):
    """A limit from the environment. A typo in a secret must not take every screen down."""
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
        if value >= 0:
            return value
    except ValueError:
        pass
    log.warning("%s=%r is not a whole number; using %s", name, raw, default)
    return default


def _uncapped():
    raw = os.environ.get("MEDVAULT_UNCAPPED", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _limits(account):
    """(this account's daily limit, or None when it is listed; the site's)."""
    listed = (account.get("email") or "").strip().lower() in _uncapped()
    per_account = _whole(os.environ.get("MEDVAULT_DAILY_PER_ACCOUNT"), PER_ACCOUNT,
                         "MEDVAULT_DAILY_PER_ACCOUNT")
    site = _whole(os.environ.get("MEDVAULT_DAILY_SITE"), SITE, "MEDVAULT_DAILY_SITE")
    return None if listed else per_account, site


def allowance(con, account):
    """Where `account` stands today."""
    mine, site_used = db.ai_use(con, account.get("id"), today())
    limit, site = _limits(account)
    return Allowance(used=mine, limit=limit, site_used=site_used, site_limit=site)


def spend(con, account):
    """Count one AI read for `account`, whatever the allowance says."""
    db.count_ai_use(con, account.get("id"), today())


def take(con, account):
    """Take one of today's AI reads for `account`, just before the model is asked. True
    means go ahead (and it is counted); False means there was no room.

    A counter that cannot be written lets the read go ahead and logs why: bookkeeping that
    fails must not cost the patient the answer - the same rule as runtime.record.
    """
    try:
        limit, site = _limits(account)
        if limit is None:
            spend(con, account)
            return True
        return db.take_ai_use(con, account.get("id"), today(), limit, site)
    except Exception:            # noqa: BLE001 - see the docstring
        log.exception("could not take an AI read for account %s", account.get("id"))
        return True


RESET_NOTE = ("Everything that does not need AI still works, and the count starts again at "
              "midnight Pacific time.")


def note(a):
    """What the screen should say about the allowance, or None when nothing needs saying."""
    if a.refused == "account" and a.limit == 0:
        # Set on purpose, to keep every read for the listed accounts. Nothing was used up,
        # and nothing restarts at midnight.
        return ("AI reads are switched off on this demo for now. Everything that does not "
                "need AI still works.")
    if a.refused == "account":
        return (f"You have used today's {a.limit} AI read{'' if a.limit == 1 else 's'} on "
                f"this account. {RESET_NOTE}")
    if a.refused == "site":
        return f"This demo has used all of today's AI reads, across everyone. {RESET_NOTE}"
    if a.left is not None and a.left <= LOW:
        return f"{a.left} AI read{'' if a.left == 1 else 's'} left on this account today."
    return None
