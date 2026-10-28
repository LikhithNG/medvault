#!/usr/bin/env python3
"""The Companion - Madison **Experience**: the bot that answers questions about
your own records.

The fourth agent, and the one Assignment 2 did not plan for. Experience is the one
Madison role of the five the original three-agent design never used.

Separate from explain.py, which answers questions about a bill and is deliberately not a
language model. This one is, because the questions are different: "what is this medicine
for", "what did they find on the scan", "why am I on two of these". Those cannot be
answered from a lookup table, and a patient holding a discharge summary they do not
understand is exactly the person a careful reader helps most.

Three things keep it from becoming the bad version of itself.

**The checks run before the model does.** Everything in brief() is arithmetic over the
vault — a duplicate medicine, a course whose end date has passed, a name that matches a
recorded allergy. Those are the findings that must never depend on a model's mood, so they
do not.

**It is told what it may not do, and the two worst questions never reach it.** Anything
that reads like an emergency, and anything that asks for a decision about a dose, is
answered deterministically and the model is never called. A fluent paragraph is the wrong
output for "should I stop taking this".

**Every answer says where it came from.** An answer drawn from the records names them. An
answer that is general knowledge about a drug says so, and says it is not about this
person. An answer the records do not support says that instead of filling the gap.

It does not check drug interactions. There is no interaction database here, and a check
that quietly does not run is worse than one that is absent.
"""
import datetime
import re

import db

# ---- what the model may never do -------------------------------------------

# Asked in the middle of something happening, the right output is six words and a phone
# number, not a paragraph. These never reach a model.
#
# Patterns rather than substrings, because people do not type the canonical phrasing:
# "my throat is closing" does not contain "throat closing", which a first version of this
# list missed. And the ambiguous ones — stroke, seizure — need a present-tense marker, or
# "what was I given after my stroke in 2019?" is answered by telling somebody to call 911.
EMERGENCY = tuple(re.compile(p) for p in (
    r"chest\s+(pain|tight)",
    r"can'?t\s+breath|cannot\s+breath|not\s+able\s+to\s+breath",
    r"(trouble|difficulty|struggling|hard)\s+\w*\s*breath",
    r"short(ness)?\s+of\s+breath",
    r"anaphyla",
    r"(severe|heavy|heavily|badly|won'?t\s+stop|can'?t\s+stop)\s+\w*\s*bleed",
    r"bleeding\s+(heavily|badly|a\s+lot)",
    r"unconscious|passed\s+out|blacked\s+out|collapsed",
    r"overdose|took\s+too\s+many|swallowed\s+the\s+whole",
    r"suicid|kill\s+myself|end\s+my\s+life|harm\s+myself",
    r"slurr\w*\s+speech",
    r"face\s+\w*\s*droop",
    r"(having|signs\s+of|think\s+\w+\s+having)\s+a?\s*(stroke|seizure|heart\s+attack)",
    r"stroke\s+symptoms|heart\s+attack\s+symptoms",
    r"lips\s+\w*\s*blue|blue\s+lips",
    r"throat\s+\w*\s*clos|tongue\s+\w*\s*swell|swollen\s+tongue",
))

# A decision about a dose belongs to the person who prescribed it. The app's job is to put
# what the record actually says in front of them, not to answer instead of the prescriber.
DECISION = (
    "should i stop", "should i take", "can i stop", "can i skip", "should i skip",
    "can i double", "should i double", "can i take more", "how much should i take",
    "is it safe for me", "is it safe to take", "can i take both", "should i increase",
    "should i reduce", "can i drink", "is it ok to take", "do i still need",
)

# HTML, not markdown: this is rendered inside a raw HTML bubble, and markdown does not
# run inside a block of HTML — the first version printed its own asterisks.
EMERGENCY_ANSWER = (
    "<b>If this is happening right now, stop reading and call 911</b> — or your local "
    "emergency number, or get to an emergency department.\n\n"
    "This app files paperwork. It cannot assess a symptom, and nothing in your records "
    "changes that answer."
)


# A short, hand-written table of the drug families a name check alone would miss. It is
# short on purpose and it is not a formulary: it exists so that "allergic to penicillin"
# plus "amoxicillin" is not silently treated as unrelated, which is the single most likely
# way a name-matching check gets somebody hurt. Everything it does not know, it says it
# does not know.
FAMILIES = {
    "penicillin": ("amoxicillin", "ampicillin", "augmentin", "amoxicillin-clavulanate",
                   "flucloxacillin", "dicloxacillin", "piperacillin", "nafcillin"),
    "sulfa": ("sulfamethoxazole", "bactrim", "co-trimoxazole", "trimethoprim-sulfa",
              "sulfasalazine"),
    "nsaid": ("ibuprofen", "naproxen", "diclofenac", "ketorolac", "celecoxib",
              "indomethacin", "aspirin"),
    "cephalosporin": ("cephalexin", "cefazolin", "ceftriaxone", "cefuroxime", "cefdinir"),
    "statin": ("atorvastatin", "simvastatin", "rosuvastatin", "pravastatin"),
}

FAMILY_CAVEAT = ("This is a name and drug-family check against what you typed in the "
                 "allergies box. The family list here is short and hand-written — it is "
                 "not a formulary, and it will miss things. Tell the hospital your "
                 "allergies yourself; do not let an app do it for you.")


def _words(text):
    return {w for w in re.findall(r"[a-z][a-z-]{2,}", (text or "").lower())}


def _family_of(name):
    low = (name or "").lower()
    return {fam for fam, members in FAMILIES.items()
            if fam in low or any(m in low for m in members)}


def allergy_conflicts(meds, profile):
    """Medicines whose name, or whose drug family, matches a recorded allergy."""
    allergy_text = (profile.get("allergies") or "").lower()
    if not allergy_text or "none" in allergy_text:
        return []
    allergy_words = {w for w in _words(allergy_text) if len(w) > 3}
    allergy_families = _family_of(allergy_text)

    hits = []
    for m in meds:
        name = (m.get("name") or "").lower()
        if not name:
            continue
        by_name = sorted(w for w in allergy_words if w in name)
        shared = sorted(_family_of(name) & allergy_families)
        if by_name or shared:
            hits.append({"med": m, "matched": by_name, "family": shared})
    return hits


# ---- the deterministic read of the vault -----------------------------------

_DURATION = re.compile(r"(\d+)\s*(day|week|month)", re.I)
_PER_UNIT = {"day": 1, "week": 7, "month": 30}


def course_ended(med, today=None):
    """The last day of a course whose own record says it is already over, else None.

    Delegates to schedule.course_end so the Companion and the Scheduler cannot disagree
    about when a course stops. They did: this function computed start + length, which is
    the day AFTER the last dose, so a 7-day course from 14 March "finished on 21 March"
    and was only flagged from the 22nd - while the Scheduler, correctly, stopped ringing
    after the 20th. Two agents giving a patient two different end dates for one
    prescription is worse than either being slightly wrong alone.

    A course with no stated duration is not overdue; it is unknown, and the two are not
    the same.
    """
    import schedule
    last = schedule.course_end(med)
    return last if last and last < (today or datetime.date.today()) else None


def _norm(name):
    return re.sub(r"[^a-z]", "", (name or "").lower())


def brief(con, owner_id, today=None):
    """What can be said about this vault without asking anything to generate a sentence."""
    meds = db.list_medications(con, active_only=True, owner_id=owner_id)
    profile = db.get_profile(con, owner_id)
    out = []

    for hit in allergy_conflicts(meds, profile):
        why = []
        if hit["matched"]:
            why.append("the name matches " + ", ".join(hit["matched"]))
        if hit["family"]:
            why.append("it is in the " + "/".join(hit["family"]) + " family")
        out.append({
            "tone": "bad",
            "title": f"{hit['med']['name']} against your recorded allergies",
            "body": (f"You listed <b>{profile.get('allergies')}</b> on your card, and "
                     f"{' and '.join(why)}. Worth raising with whoever prescribed it "
                     f"before the next dose. {FAMILY_CAVEAT}"),
        })

    seen = {}
    for m in meds:
        seen.setdefault(_norm(m.get("name")), []).append(m)
    for name, group in seen.items():
        if len(group) > 1:
            dates = ", ".join(sorted({g.get("service_date") or "undated" for g in group}))
            out.append({
                "tone": "warn",
                "title": f"{group[0]['name']} is listed {len(group)} times, all current",
                "body": (f"From prescriptions dated {dates}. That can be right — a repeat "
                         f"prescription looks the same as a second one — but two active "
                         f"entries for one medicine is worth a check."),
            })

    for m in meds:
        end = course_ended(m, today)
        if end:
            out.append({
                "tone": "warn",
                "title": f"{m['name']} is still marked as current",
                "body": (f"The prescription says {m['duration']} from "
                         f"{m.get('service_date')}, which finished on {end:%-d %B %Y}. "
                         f"If you have stopped taking it, switch it off in Medicines so "
                         f"your card is right."),
            })

    nameless = [m for m in meds if not (m.get("reason") or "").strip()]
    if nameless:
        out.append({
            "tone": "ok",
            "title": f"{len(nameless)} medicine(s) with no reason recorded",
            "body": ("Your record does not say what "
                     + ", ".join(m["name"] for m in nameless[:4])
                     + (" and others" if len(nameless) > 4 else "")
                     + " is for. That is a good thing to ask at the next appointment, and "
                       "a good thing to know if someone else ever reads this card."),
        })
    return out


# ---- the context the model is allowed to see -------------------------------

RECORDS_WITH_TEXT = 8      # how many documents get their transcribed text included
CHARS_PER_RECORD = 900
MAX_CONTEXT = 14000


def context_pack(con, owner_id):
    """Their records, flattened into the text the model answers from.

    Returns (text, sources) where sources maps a record id to the record, so an answer that
    cites one can be shown next to the card it came from.
    """
    profile = db.get_profile(con, owner_id)
    records = db.list_records(con, owner_id=owner_id, limit=60)
    meds_now = db.list_medications(con, active_only=True, owner_id=owner_id)
    meds_past = [m for m in db.list_medications(con, active_only=False, owner_id=owner_id)
                 if not m.get("active")]

    parts = ["ABOUT THEM"]
    for key, label in (("date_of_birth", "Born"), ("blood_type", "Blood type"),
                       ("allergies", "Allergies"), ("conditions", "Ongoing conditions")):
        if profile.get(key):
            parts.append(f"- {label}: {profile[key]}")

    def med_line(m):
        bits = [m.get("name") or "?"]
        for field in ("dose", "frequency", "duration", "reason"):
            if m.get(field):
                bits.append(f"{field}: {m[field]}")
        if m.get("service_date"):
            bits.append(f"prescribed {m['service_date']}")
        if m.get("provider"):
            bits.append(f"by {m['provider']}")
        return "- " + " · ".join(bits)

    parts.append("\nMEDICINES THEY ARE TAKING NOW")
    parts += [med_line(m) for m in meds_now] or ["- none recorded"]
    if meds_past:
        parts.append("\nMEDICINES THEY HAVE STOPPED")
        parts += [med_line(m) for m in meds_past[:12]]

    parts.append("\nTHEIR RECORDS")
    sources = {}
    for i, r in enumerate(records):
        sources[r["id"]] = r
        head = (f"[record {r['id']}] {r.get('service_date') or 'undated'} · "
                f"{r.get('kind')} · {r.get('title')}"
                + (f" · {r['provider']}" if r.get("provider") else ""))
        parts.append(head)
        if r.get("summary"):
            parts.append(f"    summary: {r['summary']}")
        if i < RECORDS_WITH_TEXT:
            full = db.get_record(con, r["id"]) or {}
            text = (full.get("raw_text") or "").strip()
            if text:
                parts.append("    document text: "
                             + " ".join(text.split())[:CHARS_PER_RECORD])
    return "\n".join(parts)[:MAX_CONTEXT], sources


PROMPT = """You are answering a patient's question about their own medical records, inside
an app that files their prescriptions, reports and discharge summaries. You are not their
clinician and you must not act like one.

RULES, in order of importance:
1. Never tell them to start, stop, change, skip, split or combine a dose. Never judge
   whether something is safe for them. Never diagnose. If the question asks for any of
   those, set kind to "for_prescriber", say plainly that it is a decision for whoever
   prescribed it, and then tell them exactly what their own record says about it.
2. Answer from THEIR RECORDS below wherever the records contain the answer, and put every
   record number you used in records_used. That is kind "from_records".
3. You may explain what a medicine, test or procedure generally is and what it is generally
   for. That is kind "general" — it is textbook knowledge, not a statement about this
   person, and you must not dress it up as one.
4. If their records do not say, set kind to "cannot_say" and tell them what is missing and
   who would have it. Never fill the gap with a plausible guess.
5. Do not claim anything about drug interactions. You have not been given an interaction
   database and you cannot check one.
6. Plain English, the way you would explain it to someone across a table. No headings, no
   bullet lists, no markdown. Two short paragraphs at most. Do not open by restating the
   question.

THEIR RECORDS
{context}

THEIR QUESTION
{question}
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string",
                 "enum": ["from_records", "general", "cannot_say", "for_prescriber"]},
        "answer": {"type": "string"},
        "records_used": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["kind", "answer", "records_used"],
}

KIND_LABEL = {
    "from_records": ("From your records", "ok"),
    "general": ("General information — not about you", "warn"),
    "cannot_say": ("Your records do not say", "warn"),
    "for_prescriber": ("A question for your prescriber", "bad"),
}


def triage(question):
    """The two questions a model never gets to answer."""
    q = " ".join((question or "").lower().split())
    if any(p.search(q) for p in EMERGENCY):
        return {"kind": "emergency", "answer": EMERGENCY_ANSWER, "records_used": []}
    return None


def answer(con, owner_id, question, reader=None):
    """Returns {kind, answer, records_used, sources, model, error}."""
    question = (question or "").strip()
    if not question:
        return None

    urgent = triage(question)
    if urgent:
        return {**urgent, "sources": {}, "model": None}

    context, sources = context_pack(con, owner_id)
    if reader is None:
        import gemini as reader

    result = reader.generate(PROMPT.format(context=context, question=question),
                             schema=SCHEMA, temperature=0.2)
    if not result.get("ok"):
        return {"kind": "error", "answer": None, "records_used": [], "sources": {},
                "model": result.get("model"), "error": result.get("error")}

    out = result.get("json") or {}
    kind = out.get("kind") if out.get("kind") in KIND_LABEL else "general"
    used = [i for i in (out.get("records_used") or []) if i in sources]

    # A "from your records" answer that cites nothing is not from the records. Relabel it
    # rather than let the badge make a promise the answer cannot keep.
    if kind == "from_records" and not used:
        kind = "general"

    # Asking for a decision is the one case where the badge must not depend on the model
    # having classified itself honestly.
    q = " ".join(question.lower().split())
    if any(p in q for p in DECISION):
        kind = "for_prescriber"

    return {"kind": kind, "answer": (out.get("answer") or "").strip(),
            "records_used": used, "sources": {i: sources[i] for i in used},
            "model": result.get("model"), "error": None}
