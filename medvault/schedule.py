#!/usr/bin/env python3
"""The Scheduler - Madison **Content**: when to take what, and a calendar that says so.

Reads the frequency a prescription gives ("twice daily", "every 8 hours", "at bedtime")
and turns it into the doses due today, plus a calendar file a phone can import so the
reminder rings without this app running. Content is the fifth Madison role, and the one
none of the first four agents used: this agent composes something - a daily plan, a
calendar - out of what the records already say.

**Nothing here is generated.** It is a parser over a column the Reader already filled in,
and it fails loudly rather than guessing. That matters more for this agent than for any
other in the project, because the output is an instruction somebody follows at 2 a.m.

Three things it refuses to do.

**It does not schedule "as needed".** The vault's own sample data has "every 8 hours as
needed" for ibuprofen. A naive reminder turns that into three alarms a day - telling
somebody to take an NSAID on a timetable their doctor wrote as "only if you need it". So
as-needed medicines are listed separately, with the minimum gap the prescription gives,
and never rung.

**It does not invent clinical timing.** "Twice daily" says how often, not when. The times
offered for it are a convention, labelled as a suggestion, and moved by the patient's own
"my day starts at" - never presented as part of the prescription.

**It does not keep ringing after a course ends.** A seven-day antibiotic stops on day
seven; the calendar's repeat rule ends there too. A course with no stated length repeats
until the patient switches it off, and says so in the event itself.
"""
import datetime
import re

# ---- reading the frequency ---------------------------------------------------

PRN = re.compile(r"\b(as needed|as required|when needed|if needed|prn|p\.r\.n\.?)\b", re.I)

COUNT_WORDS = (
    (re.compile(r"\b(four times|4 times|qid|q\.i\.d\.?)\b", re.I), 4),
    (re.compile(r"\b(three times|3 times|thrice|tid|t\.i\.d\.?)\b", re.I), 3),
    (re.compile(r"\b(twice|two times|2 times|bid|b\.i\.d\.?)\b", re.I), 2),
    (re.compile(r"\b(once|one time|1 time|daily|every day|each day|qd|od)\b", re.I), 1),
)
EVERY_HOURS = re.compile(r"\bevery\s+(\d{1,2})\s*(?:-\s*\d{1,2}\s*)?(?:hours?|hrs?|h)\b|\bq(\d{1,2})h\b",
                         re.I)
WEEKLY = re.compile(r"\b(weekly|once a week|every week|each week)\b", re.I)
BEDTIME = re.compile(r"\b(at bed ?time|before bed|at night|nightly|qhs|h\.s\.?)\b", re.I)
MORNING = re.compile(r"\b(in the morning|every morning|each morning|on waking)\b", re.I)
WITH_FOOD = re.compile(r"\b(with (?:food|meals?)|after (?:food|meals?)|after eating)\b", re.I)
EMPTY = re.compile(r"\b(before (?:food|meals?|breakfast)|on an empty stomach)\b", re.I)

# Conventional spacing for N doses across a waking day, as offsets in minutes from the
# patient's own day start. A convention, not a prescription - see the module docstring.
SPACING = {1: (0,), 2: (0, 720), 3: (0, 360, 720), 4: (0, 240, 480, 720)}
DEFAULT_DAY_START = "08:00"
BEDTIME_AT = "22:00"


def parse(frequency):
    """What a frequency string actually says. understood=False means do not schedule it."""
    text = (frequency or "").strip()
    out = {"text": text, "per_day": None, "every_hours": None, "weekly": False,
           "prn": bool(PRN.search(text)), "bedtime": bool(BEDTIME.search(text)),
           "morning": bool(MORNING.search(text)), "with_food": bool(WITH_FOOD.search(text)),
           "empty_stomach": bool(EMPTY.search(text)), "understood": False}
    if not text:
        return out

    hours = EVERY_HOURS.search(text)
    if hours:
        n = int(hours.group(1) or hours.group(2))
        if 1 <= n <= 24 and 24 % n == 0:
            out.update(every_hours=n, per_day=24 // n, understood=True)
            return out
        out["every_hours"] = n          # odd spacing: read, but not turned into clock times
        out["understood"] = out["prn"]  # an as-needed minimum gap is still usable
        return out

    if WEEKLY.search(text):
        out.update(weekly=True, per_day=None, understood=True)
        return out

    for pattern, count in COUNT_WORDS:
        if pattern.search(text):
            out.update(per_day=count, understood=True)
            return out

    if out["bedtime"] or out["morning"]:
        out.update(per_day=1, understood=True)
    return out


# ---- turning it into clock times ---------------------------------------------

def _minutes(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


def _clock(minutes):
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def times_for(parsed, day_start=DEFAULT_DAY_START):
    """Suggested clock times for one day. Empty for as-needed, weekly, or unreadable."""
    if parsed["prn"] or not parsed["understood"] or not parsed["per_day"]:
        return []
    if parsed["bedtime"] and parsed["per_day"] == 1:
        return [BEDTIME_AT]
    start = _minutes(day_start or DEFAULT_DAY_START)
    if parsed["every_hours"]:
        step = parsed["every_hours"] * 60
        return [_clock(start + i * step) for i in range(parsed["per_day"])]
    offsets = SPACING.get(parsed["per_day"])
    if not offsets:
        return []
    return [_clock(start + o) for o in offsets]


# ---- a course's own end date --------------------------------------------------

_DURATION = re.compile(r"(\d+)\s*(day|week|month)", re.I)
_PER_UNIT = {"day": 1, "week": 7, "month": 30}


def course_end(med):
    """The last day of a course, when the prescription gives both a start and a length."""
    started, duration = med.get("service_date"), med.get("duration")
    match = _DURATION.search(duration or "")
    if not started or not match:
        return None
    try:
        begin = datetime.date.fromisoformat(str(started)[:10])
    except ValueError:
        return None
    return begin + datetime.timedelta(
        days=int(match.group(1)) * _PER_UNIT[match.group(2).lower()] - 1)


# ---- the day's plan -----------------------------------------------------------

def plan(meds, today=None, day_start=DEFAULT_DAY_START):
    """Everything due today, in order, and everything that could not be put on a clock.

    Returns doses (rung), as_needed (listed, never rung), weekly, finished and
    unreadable - so the screen can show each group for what it is rather than
    quietly dropping the ones that did not fit.
    """
    today = today or datetime.date.today()
    doses, as_needed, weekly, finished, unreadable = [], [], [], [], []

    for med in meds:
        parsed = parse(med.get("frequency"))
        end = course_end(med)
        entry = {"med": med, "parsed": parsed, "ends": end}

        if end and end < today:
            finished.append(entry)
            continue
        if parsed["prn"]:
            as_needed.append(entry)
            continue
        if parsed["weekly"]:
            weekly.append(entry)
            continue
        clock = times_for(parsed, day_start)
        if not clock:
            unreadable.append(entry)
            continue
        for at in clock:
            doses.append({"at": at, **entry})

    doses.sort(key=lambda d: d["at"])
    return {"doses": doses, "as_needed": as_needed, "weekly": weekly,
            "finished": finished, "unreadable": unreadable, "day_start": day_start,
            "date": today}


def next_due(day, now=None):
    """The next dose still to come today, or None."""
    now = now or datetime.datetime.now()
    current = now.hour * 60 + now.minute
    return next((d for d in day["doses"] if _minutes(d["at"]) >= current), None)


def note(parsed):
    """The plain-language instruction that belongs beside a dose."""
    bits = []
    if parsed["with_food"]:
        bits.append("with food")
    if parsed["empty_stomach"]:
        bits.append("on an empty stomach")
    return ", ".join(bits)


# ---- the calendar a phone can hold ----------------------------------------------

def _escape(text):
    return (str(text or "").replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _fold(line):
    """RFC 5545 caps a line at 75 octets; longer ones continue on a line that starts
    with a space. A phone calendar that meets an unfolded 200-character line may drop
    the whole event, which is the failure nobody would notice until a dose was missed."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, chunk = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > (75 if not parts else 74):
            parts.append(chunk.decode("utf-8"))
            chunk = b""
        chunk += b
    parts.append(chunk.decode("utf-8"))
    return "\r\n ".join(parts)


def calendar(day, account_label="MedVault", stamp=None):
    """A .ics file: one repeating event per dose time, with an alarm at the dose.

    Floating local times (no time zone) on purpose: "08:00" should mean eight in the
    morning wherever the phone is, which is what a dose time means.
    """
    stamp = stamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    start_day = day["date"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//MedVault//Medication schedule//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_escape(account_label)} medicines"]

    for i, dose in enumerate(day["doses"]):
        med, parsed, end = dose["med"], dose["parsed"], dose["ends"]
        h, m = dose["at"].split(":")
        begins = f"{start_day:%Y%m%d}T{h}{m}00"
        rule = "RRULE:FREQ=DAILY"
        if end:
            rule += f";UNTIL={end:%Y%m%d}T235959"
        what = f"{med.get('name')} - {med.get('dose') or 'as prescribed'}"
        extra = note(parsed)
        description = (
            f"{med.get('dose') or ''} · {parsed['text']}"
            + (f" · {extra}" if extra else "")
            + (f"\\nPrescribed for: {med['reason']}" if med.get("reason") else "")
            + ("" if end else
               "\\nThis course has no stated end. Delete this reminder when you stop.")
            + "\\nThe time is a suggestion from MedVault, not part of the prescription."
        )
        lines += ["BEGIN:VEVENT",
                  f"UID:medvault-{med.get('id', i)}-{h}{m}-{start_day:%Y%m%d}@medvault",
                  f"DTSTAMP:{stamp}", f"DTSTART:{begins}", "DURATION:PT5M", rule,
                  f"SUMMARY:{_escape(what)}", f"DESCRIPTION:{_escape(description)}",
                  "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:PT0M",
                  f"DESCRIPTION:{_escape('Time for ' + str(med.get('name')))}",
                  "END:VALARM", "END:VEVENT"]

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
