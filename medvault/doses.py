#!/usr/bin/env python3
"""The Scheduler's log: what was taken, what was skipped, what was missed, and what is left.

The Scheduler says when a dose is due; this says what happened to it. Each scheduled dose
can be marked taken or skipped. A dose nobody marked, long after its time, is missed -
which is the one fact a family member far away actually needs, and the ground the
Guardian will stand on.

The model is MedTimer's (github.com/Futsch1/medTimer, MIT): a dose is an event with a
status, a skipped dose uses no stock, and stock is counted in the dose's own unit with no
conversion. Only the first number in the dose counts, and only when it counts something:
"1 capsule (25 mg)" is one capsule; "500 mg" is a strength, and says nothing about how
many leave the box, so it is not read as 500 of anything.

**Nothing here guesses.** No count per dose, no forecast. Not on a daily clock, no
forecast. A course that ends first, no refill warning. Each is said out loud on screen
rather than replaced by a plausible number.
"""
import csv
import datetime
import io
import math
import re

import schedule

GRACE_MINUTES = 120        # unmarked this long after its time, a dose is missed
LOW_DAYS = 7               # warn when the box runs out within a week
EXPIRY_WARN_DAYS = 30      # and when the medicine expires within a month
FORECAST_DAYS = 36_500     # a century: past this a run-out date is not a date, it is a typo
STATUSES = ("taken", "skipped")

# Things a dose counts. A unit outside this list ("mg", "mcg", "ml/kg") is a strength or
# a rate, not a number of things taken out of a box.
COUNTED = ("tablet", "tab", "capsule", "cap", "pill", "puff", "drop", "patch", "sachet",
           "spray", "lozenge", "suppository", "injection", "ml", "teaspoon", "tsp", "unit")
_NUMBER_WORDS = {"half": 0.5, "½": 0.5, "one": 1, "two": 2, "three": 3, "four": 4}
_FIRST_AMOUNT = re.compile(r"^\s*(\d+(?:\.\d+)?|½|half|one|two|three|four)\s*(?:an?\s+)?([a-z]+)", re.I)
# "10 ml/kg", "5 ml per kg": a rate by body weight, not a count of anything.
_RATE = re.compile(r"\s*(?:/|per\b)", re.I)
# Cells a spreadsheet would run as a formula if they started a field.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


# ---- how much one dose uses ------------------------------------------------------

def _amount(dose):
    """(count, unit) from the start of a dose, or None when it does not count anything."""
    text = str(dose or "")
    match = _FIRST_AMOUNT.match(text)
    if not match or _RATE.match(text, match.end()):
        return None
    number, word = match.group(1).lower(), match.group(2).lower()
    unit = word[:-2] if word.endswith("es") and word[:-2] in COUNTED else word.rstrip("s")
    if unit not in COUNTED:
        return None
    count = _NUMBER_WORDS[number] if number in _NUMBER_WORDS else float(number)
    return (count, unit) if count > 0 else None


def per_dose(med):
    """How much one dose takes out of the box: what the patient typed, else the label's count."""
    typed = med.get("per_dose")
    if isinstance(typed, (int, float)) and not isinstance(typed, bool) and math.isfinite(typed) and typed > 0:
        return float(typed)
    found = _amount(med.get("dose"))
    return found[0] if found else None


def unit(med):
    """The unit the stock is counted in, when the dose names one."""
    found = _amount(med.get("dose"))
    return found[1] if found else None


def count_text(n, unit_name):
    """"9 tablets", "1 tablet", "0.5 tablet", "30 ml", or just "30" when the unit is not known."""
    number = f"{n:g}"
    if not unit_name:
        return number
    if 0 < n <= 1 or unit_name in ("ml", "tsp"):
        return f"{number} {unit_name}"
    if unit_name.endswith(("ch", "sh", "s", "x")):
        return f"{number} {unit_name}es"
    if unit_name.endswith("y"):
        return f"{number} {unit_name[:-1]}ies"
    return f"{number} {unit_name}s"


def after_taking(stock, amount):
    """Stock after one dose. Never below zero: a box cannot hold minus one tablet."""
    return max(0.0, float(stock) - float(amount))


# ---- today's doses ---------------------------------------------------------------

def _status(dose, entry, day, now):
    if entry:
        return entry["status"]
    hour, minute = map(int, dose["at"].split(":"))
    due = datetime.datetime.combine(day, datetime.time(hour, minute))
    if now < due:
        return "upcoming"
    if now < due + datetime.timedelta(minutes=GRACE_MINUTES):
        return "due"
    return "missed"


def board(day, logged, now=None):
    """Each of the day's doses with what happened to it: taken, skipped, due, upcoming or missed.

    `day` is a schedule.plan(); `logged` is that account's log rows. Only entries for the
    plan's own date count, so yesterday's 08:00 is not today's.
    """
    now = now or datetime.datetime.now()
    date = day["date"].isoformat()
    entries = {(e["med_id"], e["at"]): e for e in logged if e["day"] == date}
    return [{**dose, "status": _status(dose, entries.get((dose["med"]["id"], dose["at"])), day["date"], now)}
            for dose in day["doses"]]


def missed(rows):
    """The doses on a board that nobody marked in time. A skipped dose is a choice, not a miss."""
    return [row for row in rows if row["status"] == "missed"]


# ---- stock and expiry ------------------------------------------------------------

def _doses_per_day(med):
    return len(schedule.times_for(schedule.parse(med.get("frequency"))))


def stock_state(med, today=None):
    """What the box holds and when it runs out.

    level is "untracked" (nobody entered a stock), "out", "low" (runs out within
    LOW_DAYS), "ok", or "unknown" (a stock, but no count per dose or no daily schedule, so
    no forecast can honestly be made). enough is True when the course ends first.
    """
    today = today or datetime.date.today()
    left = med.get("stock")
    state = {"left": left, "unit": unit(med), "runs_out": None, "enough": False}
    if left is None:
        return {**state, "level": "untracked"}
    if left <= 0:
        return {**state, "level": "out"}
    each, daily = per_dose(med), _doses_per_day(med)
    if not each or not daily:
        return {**state, "level": "unknown"}
    days = left / (each * daily)
    if not math.isfinite(days) or days > FORECAST_DAYS:
        return {**state, "level": "ok"}
    runs_out = today + datetime.timedelta(days=int(days))
    end = schedule.course_end(med)
    if end and runs_out > end:
        return {**state, "level": "ok", "enough": True}
    low = (runs_out - today).days <= LOW_DAYS
    return {**state, "runs_out": runs_out, "level": "low" if low else "ok"}


def expiry_state(med, today=None):
    """"expired", "soon" (within EXPIRY_WARN_DAYS), or None - including when there is no date."""
    today = today or datetime.date.today()
    try:
        expires = datetime.date.fromisoformat(str(med.get("expires") or ""))
    except ValueError:
        return None
    if expires < today:
        return "expired"
    return "soon" if (expires - today).days <= EXPIRY_WARN_DAYS else None


# ---- the history, for a doctor ---------------------------------------------------

def _cell(value):
    """Text, never a formula: names and doses were read off photographs."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def history_csv(rows):
    """The dose log as CSV, one row per recorded dose, oldest first."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["date", "scheduled", "medicine", "dose", "status", "recorded_at"])
    for row in rows:
        recorded = datetime.datetime.fromtimestamp(row["recorded_at"]).isoformat(timespec="minutes")
        writer.writerow([_cell(row["day"]), _cell(row["at"]), _cell(row["name"]), _cell(row.get("dose")),
                         _cell(row["status"]), recorded])
    return out.getvalue()
