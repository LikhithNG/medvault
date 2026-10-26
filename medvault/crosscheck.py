#!/usr/bin/env python3
"""Check a hospital bill against what the patient's own records say happened.

This is the question a price comparison cannot answer. A published-price check asks *was
this the right amount for a CT scan*. This asks *did I have a CT scan at all*.

The danger in it is obvious and has to be designed against rather than disclaimed. A vault
contains what its owner remembered to upload, which is never everything. "No record found"
therefore means *you have not filed anything that supports this line* - it does not mean the
service did not happen, and this module must never produce a sentence that says it did.
Every verdict below is phrased as a question to ask, not a finding to assert.
"""
import re
from datetime import date, timedelta

# How far from a bill's service date a record can sit and still plausibly cover it. An
# imaging report is often dated the day after the scan; a discharge summary, days later.
WINDOW_DAYS = 3

# Words that appear in nearly every line of a hospital bill and carry no meaning for
# matching. Without this, "HOSPITAL SERVICE" matches every record ever filed.
STOPWORDS = {
    "hchg", "hospital", "service", "services", "charge", "charges", "general", "supply",
    "supplies", "room", "misc", "miscellaneous", "level", "unit", "units", "each", "per",
    "with", "without", "and", "the", "for", "initial", "subsequent", "department",
}

VERDICTS = {
    "MATCHED":       ("Matches a record you filed", "ok"),
    "DATE_NO_MATCH": ("You have records that day, but none mention this", "warn"),
    "NO_RECORD":     ("Nothing in your vault from this date", "bad"),
    "UNDATED":       ("This line has no date to check against", "warn"),
    "VAULT_THIN":    ("Your vault has nothing from around this time", "warn"),
}


def _parse(value):
    if not value:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _words(text):
    """The meaningful words of a description, lowercased, stopwords dropped."""
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in STOPWORDS}


def _record_text(rec):
    return " ".join(str(rec.get(k) or "") for k in ("title", "summary", "provider", "raw_text"))


def check_line(line, records):
    """One bill line against the whole vault. Returns a verdict dict.

    `line` needs a description and, ideally, a service date. `records` are vault rows.
    """
    when = _parse(line.get("service_date") or line.get("date"))
    desc = line.get("description") or line.get("desc") or ""
    wanted = _words(desc)

    dated = [(r, _parse(r.get("service_date"))) for r in records]
    dated = [(r, d) for r, d in dated if d]

    if not when:
        return {"verdict": "UNDATED", "matches": [],
                "ask": "Ask the billing office what date this line was for — it is not "
                       "printed, so it cannot be checked against your records."}

    if not dated:
        return {"verdict": "VAULT_THIN", "matches": [],
                "ask": "You have not filed any dated records yet, so this line cannot be "
                       "checked. Add the paperwork from this visit first."}

    near = [r for r, d in dated if abs((d - when).days) <= WINDOW_DAYS]

    if not near:
        nearest = min(dated, key=lambda rd: abs((rd[1] - when).days))
        gap = abs((nearest[1] - when).days)
        return {"verdict": "NO_RECORD", "matches": [], "nearest_days": gap,
                "ask": f"Ask what this charge was for. You have filed nothing from "
                       f"{when:%d %b %Y} — your closest record is {gap} days away. "
                       f"That may simply be paperwork you never received."}

    scored = []
    for r in near:
        overlap = wanted & _words(_record_text(r))
        if overlap:
            scored.append((len(overlap), r, sorted(overlap)))
    scored.sort(key=lambda t: -t[0])

    if scored:
        _, best, overlap = scored[0]
        return {"verdict": "MATCHED", "matches": [best], "overlap": overlap,
                "ask": f"Supported by your own record: “{best['title']}”"
                       + (f" ({best['service_date']})" if best.get("service_date") else "")}

    titles = ", ".join(f"“{r['title']}”" for r in near[:3])
    return {"verdict": "DATE_NO_MATCH", "matches": near,
            "ask": f"Ask what this charge covers. You have records from {when:%d %b %Y} "
                   f"({titles}) and none of them mentions it."}


def check_bill(lines, records):
    """A whole bill. Returns (checked_lines, summary)."""
    out = []
    for line in lines:
        result = check_line(line, records)
        out.append(line | result)

    counts = {}
    for r in out:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    unsupported = [r for r in out if r["verdict"] in ("NO_RECORD", "DATE_NO_MATCH")]
    at_stake = round(sum(float(r.get("charged") or 0) for r in unsupported), 2)

    return out, {
        "lines": len(out),
        "counts": counts,
        "unsupported": len(unsupported),
        "amount_unsupported": at_stake,
        # Said once, here, so every surface that renders this carries the same caveat.
        "caveat": ("Your vault holds what you have uploaded, which is rarely everything. "
                   "A line with no matching record is a question to ask, not proof that "
                   "the service never happened."),
    }
