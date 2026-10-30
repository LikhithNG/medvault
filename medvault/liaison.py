#!/usr/bin/env python3
"""The Liaison - Madison **Performance**: what a patient's records say is outstanding,
carried to the doctors they chose.

The brief asked for an agent that tells the patient and the doctor when a hospital visit
or a check-up is needed. Half of that is buildable honestly and half is not, and the line
between them is the whole design.

**What it does not do: decide that anybody needs care.** Whether a symptom warrants a
hospital is a clinical judgement, and software that makes it is either a medical device
or a liability - this project is neither. So nothing here reads a symptom, scores a risk,
or tells anyone to go anywhere. tests/test_liaison.py scans every sentence this module can
produce for triage language and fails if it finds any.

**What it does: notice what the records themselves say.** A discharge summary that says
"follow up in two weeks", dated two months ago, with nothing in the vault since - that is
not a judgement, it is the record's own instruction, overdue. Same for a medicine that
collides with a recorded allergy, a course that ended but is still marked current, a dose
nobody can time. Each item names the record it came from, so the doctor reading it can
check it rather than trust it.

**Who sees it: only the care team the patient built** (careteam.py). Not every clinician
on the server.

**How it reaches them: through the patient.** There is no email or push here. The patient
sees the same list their doctor sees, and can download it as a message to send themselves.
An app that messages a doctor on a patient's behalf is speaking for them; one that hands
them the words is not.
"""
import datetime
import re

import ask
import db
import schedule

# A follow-up a record asks for, and how long after the record it falls due. Read with
# care, because a test pass found this raising "Return to work after 2 days", "Please
# return this form within 30 days" and "Follow up is not required in 2 weeks" as overdue
# follow-ups - and missing "follow up in two weeks", "in 2-3 weeks" and "in 1 year".
_NUMBER = (r"(\d{1,3}(?:\s*(?:-|–|to)\s*\d{1,3})?|one|two|three|four|five|six|seven|eight"
           r"|nine|ten|eleven|twelve|a|an)")
FOLLOW_UP = re.compile(
    r"\b(follow[\s-]?up|review(?!\s+of\b)|re-?check|recheck|come back"
    r"|return(?!\s+(?:to\s+(?:work|school|normal|usual|activit\w*|sport\w*|driving|duty)"
    r"|this|the\s+form|policy|of)\b)"
    r"|repeat (?:the )?(?:test|scan|bloods?|labs?)|see (?:your|the) (?:gp|doctor|physician"
    r"|clinician))\b"
    rf"[^.\n]{{0,40}}?\b(?:in|after|within)\s+{_NUMBER}\s*(day|week|month|year)s?\b",
    re.I)
_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
# "Follow up is not required in 2 weeks", "No need to follow up in 2 weeks".
NOT_NEEDED = re.compile(r"\b(not|no need|unnecessary|isn'?t|aren'?t|never)\b", re.I)


def _count(number):
    """How many of the unit: the later end of a range ("2-3 weeks" is three)."""
    digits = re.findall(r"\d{1,3}", number)
    return int(digits[-1]) if digits else _WORDS[number.lower()]


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


# Titles and initials say nothing about which doctor a card names, so they never count
# towards a match: "Dr. P. Nair" is matched on "Nair" alone.
_TITLE = {"dr", "doctor", "prof", "professor", "mr", "mrs", "ms", "mx", "md", "do"}


def _name_words(name):
    return [w for w in re.findall(r"[a-z]+", (name or "").lower())
            if len(w) > 1 and w not in _TITLE]


def contact(profile, provider):
    """Who to ask about a record, when the record is from the doctor on the patient's card.

    The number is the one the patient wrote on their own card - nothing is looked up or
    guessed. It is offered only when every word of that doctor's name appears in the
    record's provider, because the card's doctor is not every record's doctor, and the
    wrong number is worse than none.
    """
    name, phone = (profile.get("gp_name") or "").strip(), (profile.get("gp_phone") or "").strip()
    words = _name_words(name)
    if not (words and phone and provider):
        return None
    if not set(words) <= set(re.findall(r"[a-z]+", provider.lower())):
        return None
    dial = re.sub(r"[^\d+]", "", phone)
    if len(re.sub(r"\D", "", dial)) < 7:
        return None
    return {"name": name, "phone": phone, "dial": dial}


def follow_ups(con, owner_id, today=None):
    """Follow-ups a record asked for, whose date has passed with nothing filed since.

    "Nothing filed since" is said as exactly that. A vault holds what was uploaded, which
    is rarely everything - so an overdue follow-up here is a question to ask, never a
    finding that the patient missed an appointment.
    """
    today = today or datetime.date.today()
    records = db.list_records(con, owner_id=owner_id, limit=1000)
    profile = db.get_profile(con, owner_id)
    dated = sorted(d for d in (_date(r.get("service_date")) for r in records) if d)
    out = []
    for r in records:
        start = _date(r.get("service_date"))
        if not start:
            continue
        full = db.get_record(con, r["id"]) or {}
        text = " ".join(filter(None, [r.get("summary"), full.get("raw_text")]))
        for match in FOLLOW_UP.finditer(text):
            if NOT_NEEDED.search(text[max(0, match.start() - 20):match.end()]):
                continue
            due = start + datetime.timedelta(
                days=_count(match.group(2)) * _DAYS[match.group(3).lower()])
            if due >= today:
                continue
            if any(d >= due for d in dated):
                continue              # something has been filed since it was due
            out.append({
                "tone": "warn",
                "kind": "follow_up",
                "title": f"A follow-up from {start:%-d %B %Y} may be overdue",
                "body": (f"Your {r.get('kind') or 'record'} “{r.get('title')}”"
                         + (f" from {r['provider']}" if r.get("provider") else "")
                         + f" says “{match.group(0).strip()}” — around {due:%-d %B %Y}. "
                         "There is nothing in your vault dated after that, which may "
                         "only mean the paperwork is not here. Worth checking whether "
                         "it happened."),
                "source": r.get("title"),
                "due": due,
                "contact": contact(profile, r.get("provider")),
            })
            break                     # one item per record is enough to ask about
    return out


def update(con, owner_id, today=None):
    """Everything the records say is outstanding, most pressing first.

    Built from the same checks the Companion already runs, so a doctor and a patient
    are never shown two different lists about the same records.
    """
    items = [dict(f, kind=f.get("kind", "record")) for f in ask.brief(con, owner_id, today)]
    items += follow_ups(con, owner_id, today)
    meds = db.list_medications(con, active_only=True, owner_id=owner_id)
    for e in schedule.plan(meds, today)["unreadable"]:
        items.append({
            "tone": "warn", "kind": "dosing",
            "title": f"{e['med']['name']}: no usable instruction for when to take it",
            "body": (f"The prescription says “{e['parsed']['text'] or 'nothing'}”, which "
                     "does not say how often. Worth confirming with the pharmacist."),
        })
    order = {"bad": 0, "warn": 1, "ok": 2}
    return sorted(items, key=lambda i: order.get(i.get("tone"), 3))


def message(patient, items, today=None):
    """The update as words a patient can send their doctor themselves."""
    today = today or datetime.date.today()
    name = patient.get("display_name") or "your patient"
    lines = [f"MedVault update for {name} · {today:%-d %B %Y}", "",
             "These are things my own records say are outstanding. They come from the "
             "documents I have filed, not from a symptom check, and the vault holds only "
             "what I have uploaded.", ""]
    if not items:
        lines.append("Nothing outstanding in my records.")
    for n, item in enumerate(items, 1):
        lines += [f"{n}. {item['title']}", "   " + re.sub(r"<[^>]+>", "", item["body"]), ""]
    lines.append("I would be grateful for a word on any of these when you next have "
                 "a moment.")
    return "\n".join(lines) + "\n"
