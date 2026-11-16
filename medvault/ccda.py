#!/usr/bin/env python3
"""A patient portal's record file, read with no AI at all.

Most portals (MyChart and the rest) will hand a patient their record as a C-CDA file: XML
in the HL7 standard, with each section - allergies, medicines, problems, results,
vaccinations, vital signs - marked by a template id. The approach is Mere Medical's
(github.com/cfu288/mere-medical, MIT): find each section by its template id and copy out
what the hospital itself stored. Nothing is read off a photograph, so nothing has to be
guessed, and the result comes back as the same draft the Reader produces, to be checked
on the same screen before anything is filed.

**What it refuses.** A file that is not a C-CDA. Any file with a DTD or entities - the
two classic ways to attack an XML parser through an upload - which a real C-CDA never
needs. An as-needed medicine is never handed to the Scheduler without "as needed" on it,
and a finished course arrives finished.
"""
import datetime
import math
import re
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as SafeXML

import doses
from schema import PORTAL_READER

READER = PORTAL_READER
MAX_BYTES = 10 * 1024 * 1024       # a summary of one person's care, not a hospital's archive
MAX_ROWS = 2000                    # per section
H = "urn:hl7-org:v3"
NS = {"h": H}
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
LOINC = "2.16.840.1.113883.6.1"
_SECTION_IDS = {
    "allergies": "2.16.840.1.113883.10.20.22.2.6", "medications": "2.16.840.1.113883.10.20.22.2.1",
    "problems": "2.16.840.1.113883.10.20.22.2.5", "results": "2.16.840.1.113883.10.20.22.2.3",
    "immunizations": "2.16.840.1.113883.10.20.22.2.2", "vitals": "2.16.840.1.113883.10.20.22.2.4",
}
FINISHED = ("completed", "aborted", "cancelled", "nullified")
# A dose with no unit takes its form from the product: "Montelukast 10 MG Oral Tablet".
_FORMS = (("inhal", "puff"), ("actuat", "puff"), ("tablet", "tablet"), ("capsule", "capsule"),
          ("patch", "patch"), ("drop", "drop"), ("spray", "spray"), ("suppositor", "suppository"),
          ("lozenge", "lozenge"), ("sachet", "sachet"))
_PER_HOURS = {24: "once daily", 12: "twice daily", 8: "three times daily", 6: "four times daily"}
LONGEST_PERIOD = 366          # in whatever unit the file uses; past this it is not a schedule


def _positive(text, ceiling=None):
    """A finite number above zero (and at most `ceiling`), or None: "1e999", "nan", "0"
    and "-4" are not amounts, and "1e999" used to raise OverflowError on the Add screen."""
    try:
        n = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or n <= 0 or (ceiling is not None and n > ceiling):
        return None
    return n


# ---- small readers -------------------------------------------------------------------

def _date(value):
    """"20261014103000-0500" -> "2026-10-14"; None for anything that is not a real date."""
    digits = re.match(r"(\d{4})(\d{2})(\d{2})", str(value or ""))
    if not digits:
        return None
    try:
        return datetime.date(*map(int, digits.groups())).isoformat()
    except ValueError:
        return None


def _narrative(section):
    """The section's human-readable text, by element ID, for originalText references."""
    return {el.get("ID"): " ".join("".join(el.itertext()).split())
            for el in section.iter() if el.get("ID")}


def _label(code, ids):
    """What a coded element is called: its display name, else its original text."""
    if code is None:
        return None
    if code.get("displayName"):
        return code.get("displayName").strip()
    original = code.find("h:originalText", NS)
    if original is None:
        return None
    ref = original.find("h:reference", NS)
    if ref is not None and (ref.get("value") or "").startswith("#"):
        return ids.get(ref.get("value")[1:])
    return " ".join("".join(original.itertext()).split()) or None


def _when(el):
    """An element's effectiveTime, as a date: its value, else its low end."""
    time = el.find("h:effectiveTime", NS)
    if time is None:
        return None
    low = time.find("h:low", NS)
    return _date(time.get("value") or (low.get("value") if low is not None else None))


# ---- medicines -------------------------------------------------------------------------

def _frequency(sa):
    for time in sa.findall("h:effectiveTime", NS):
        period = time.find("h:period", NS)
        if time.get(XSI_TYPE) != "PIVL_TS" or period is None:
            continue
        n = _positive(period.get("value"), LONGEST_PERIOD)
        if n is None:
            return None
        n, unit = int(n) if n == int(n) else n, period.get("unit")
        if unit == "h":
            return _PER_HOURS.get(n, f"every {n} hours")
        if unit == "d":
            return {1: "once daily", 7: "once a week"}.get(n, f"every {n} days")
        if unit == "wk":
            return "once a week" if n == 1 else f"every {n} weeks"
        if unit == "mo":
            return "once a month" if n == 1 else f"every {n} months"
    return None


def _course(sa):
    """(duration text, end date) from the medicine's start and end, when both are given."""
    for time in sa.findall("h:effectiveTime", NS):
        low, high = time.find("h:low", NS), time.find("h:high", NS)
        start = _date(low.get("value")) if low is not None else None
        end = _date(high.get("value")) if high is not None else None
        if start and end and end >= start:
            days = (datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)).days + 1
            return f"{days} days, until {end}", end
        if end:
            return f"until {end}", end
    return None, None


def _dose(sa, name):
    qty = sa.find("h:doseQuantity", NS)
    amount = _positive(qty.get("value")) if qty is not None else None
    if amount is None:
        return None
    unit = (qty.get("unit") or "").strip("{}").lower()
    if unit in ("", "1"):
        unit = next((form for key, form in _FORMS if key in (name or "").lower()), "")
    if unit.rstrip("s") in doses.COUNTED or unit in dict(_FORMS).values():
        return doses.count_text(amount, unit.rstrip("s"))
    return f"{amount:g} {unit}".strip()


def _medication(sa, ids, as_of):
    material = sa.find("h:consumable/h:manufacturedProduct/h:manufacturedMaterial", NS)
    if material is None:
        return None
    name = _label(material.find("h:code", NS), ids) or (material.findtext("h:name", namespaces=NS) or "").strip()
    if not name:
        return None
    frequency = _frequency(sa)
    if sa.find("h:precondition", NS) is not None:          # "only when wheezing": as needed
        frequency = f"{frequency} as needed" if frequency else "as needed"
    duration, end = _course(sa)
    status = (sa.find("h:statusCode", NS).get("code") if sa.find("h:statusCode", NS) is not None else "")
    reason = sa.find("h:entryRelationship[@typeCode='RSON']/h:observation/h:value", NS)
    return {"name": name, "dose": _dose(sa, name), "frequency": frequency, "duration": duration,
            "reason": _label(reason, ids),
            "active": status not in FINISHED and not (end and as_of and end < as_of)}


# ---- results and the rest -------------------------------------------------------------------

def _value(obs):
    """(value, unit) as stored: a number and its unit, a text, or a coded answer."""
    value = obs.find("h:value", NS)
    if value is None:
        return None, None
    kind = value.get(XSI_TYPE) or ""
    if kind in ("PQ", "INT", "REAL") or (value.get("value") and not kind):
        unit = value.get("unit")
        return value.get("value"), (None if unit in (None, "", "1") else unit)
    if kind in ("CD", "CE", "CO", "CV"):
        return value.get("displayName") or value.get("code"), None
    if kind == "IVL_PQ":
        low, high = value.find("h:low", NS), value.find("h:high", NS)
        bounds = [b.get("value") for b in (low, high) if b is not None and b.get("value")]
        return "-".join(bounds) or None, (low if low is not None else high).get("unit") if bounds else None
    return " ".join("".join(value.itertext()).split()) or None, None


def _range(obs, ids):
    rng = obs.find("h:referenceRange/h:observationRange", NS)
    if rng is None:
        return None
    text = rng.find("h:text", NS)
    if text is not None:
        ref = text.find("h:reference", NS)
        if ref is not None and (ref.get("value") or "").startswith("#"):
            return ids.get(ref.get("value")[1:])
        return " ".join("".join(text.itertext()).split()) or None
    low, high = rng.find("h:value/h:low", NS), rng.find("h:value/h:high", NS)
    bounds = [b.get("value") for b in (low, high) if b is not None and b.get("value")]
    return "-".join(bounds) or None


def _result(obs, ids, fallback_date):
    code = obs.find("h:code", NS)
    name = _label(code, ids)
    value, unit = _value(obs)
    if not name or not value:
        return None
    flag = obs.find("h:interpretationCode", NS)
    flag = flag.get("code") if flag is not None else None
    return {"name": name, "value": value, "unit": unit, "reference_range": _range(obs, ids),
            "flag": None if flag in (None, "", "N") else flag,       # "normal" is not a flag
            "code": code.get("code") if code is not None and code.get("codeSystem") == LOINC else None,
            "taken_on": _when(obs) or fallback_date}


def _results(section, ids):
    out = []
    for entry in section.findall("h:entry", NS):
        organizer = entry.find("h:organizer", NS)
        if organizer is not None:
            when = _when(organizer)
            observations = organizer.findall("h:component/h:observation", NS)
        else:
            when, observations = None, entry.findall("h:observation", NS)
        out += [r for r in (_result(o, ids, when) for o in observations) if r]
    return out


def _observations(section):
    """The clinical observations under a concern act, skipping any marked "not present"."""
    for obs in section.iterfind("h:entry/h:act/h:entryRelationship/h:observation", NS):
        if obs.get("negationInd") != "true":
            yield obs


def _allergies(section, ids):
    out = []
    for obs in _observations(section):
        substance = obs.find("h:participant/h:participantRole/h:playingEntity", NS)
        if substance is None:
            continue
        name = _label(substance.find("h:code", NS), ids) or (substance.findtext("h:name", namespaces=NS) or "").strip()
        reactions = [_label(r, ids) for r in obs.iterfind("h:entryRelationship[@typeCode='MFST']/h:observation/h:value", NS)]
        reactions = [r.lower() for r in reactions if r]
        if name:
            out.append(f"{name} ({', '.join(reactions)})" if reactions else name)
    return out


def _problems(section, ids):
    return [p for p in (_label(o.find("h:value", NS), ids) for o in _observations(section)) if p]


def _immunizations(section, ids):
    out = []
    for sa in section.iterfind("h:entry/h:substanceAdministration", NS):
        if sa.get("negationInd") == "true":        # recorded as NOT given
            continue
        name = _label(sa.find("h:consumable/h:manufacturedProduct/h:manufacturedMaterial/h:code", NS), ids)
        if name:
            out.append({"name": name, "date": _when(sa)})
    return out


# ---- the document ---------------------------------------------------------------------------

def _parse(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("that file is empty, or too large to be one person's health summary")
    try:
        root = SafeXML.fromstring(data, forbid_dtd=True)
    except (ParseError, ValueError, TypeError) as problem:   # defusedxml's refusals are ValueErrors
        raise ValueError("that file is not a readable record file") from problem
    if root.tag != f"{{{H}}}ClinicalDocument":
        raise ValueError("that file is not a C-CDA health record (it has no ClinicalDocument)")
    return root


def _sections(root):
    found = {}
    for section in root.iterfind(".//h:section", NS):
        roots = {t.get("root") for t in section.findall("h:templateId", NS)}
        for name, base in _SECTION_IDS.items():
            if base in roots or f"{base}.1" in roots:
                found.setdefault(name, []).append(section)
    return found


def _plural(n, word, many=None):
    return f"{n} {word if n == 1 else (many or word + 's')}"


def _summary(d):
    bits = [_plural(len(d["medications"]), "medicine"), _plural(len(d["lab_results"]), "result"),
            _plural(len(d["allergies"]), "allergy", "allergies"), _plural(len(d["problems"]), "problem")]
    text = "From your patient portal's record file: " + ", ".join(bits) + "."
    if d["immunizations"]:
        text += " Vaccinations: " + "; ".join(
            f"{v['name']}" + (f" ({v['date']})" if v["date"] else "") for v in d["immunizations"]) + "."
    return text


_CARD_ITEMS = re.compile(r"[,;/\n]")
_NONE_KNOWN = {"none", "no known allergies", "no known drug allergies", "nka", "nkda", "n/a"}


def _item(text):
    """(name, reaction) of one card or file entry: "Penicillin G (hives)"."""
    name, _, rest = text.strip().partition("(")
    return name.strip().casefold(), rest.rstrip(") ").strip().casefold()


def merged(existing, items):
    """The card's own list with these items added, each once. Nothing typed there is
    removed, except a "no known allergies" the file now contradicts.

    Matching is by whole entry, never by part of a word: a substring test let "Peanut" on
    the card hide "Nut" from the file, and on an emergency card a missing allergy is the
    dangerous mistake. A known allergy with a reaction the card does not yet name is added
    too - "Penicillin (anaphylaxis)" beside "Penicillin (rash)" - because the severity is
    the part a nurse needs.
    """
    text = (existing or "").strip()
    if text.casefold() in _NONE_KNOWN and items:
        text = ""
    known = {_item(entry) for entry in _CARD_ITEMS.split(text) if entry.strip()}
    for item in items:
        name, reaction = _item(item)
        if (name, reaction) in known or (not reaction and any(n == name for n, _ in known)):
            continue
        text = f"{text}, {item}" if text else item
        known.add((name, reaction))
    return text


def read(data):
    """A draft record from a C-CDA file - the shape extract.read_document returns, plus
    allergies, problems and immunizations. ValueError if the file is not one to trust."""
    try:
        return _read(_parse(data))
    except (ArithmeticError, AttributeError, TypeError, IndexError) as problem:
        # A file shaped like no C-CDA we have seen: refused, never a crash on the Add screen.
        raise ValueError("that file is not a record file MedVault can read") from problem


def _read(root):
    as_of = _date((root.find("h:effectiveTime", NS) if root.find("h:effectiveTime", NS) is not None
                   else root).get("value"))
    sections = _sections(root)

    def each(name, reader):
        rows = []
        for section in sections.get(name, []):
            rows += reader(section, _narrative(section))
        return rows[:MAX_ROWS]

    meds = each("medications", lambda s, ids: [m for m in (
        _medication(sa, ids, as_of) for sa in s.iterfind("h:entry/h:substanceAdministration", NS)) if m])
    provider = (root.findtext(".//h:custodian//h:representedCustodianOrganization/h:name", namespaces=NS)
                or root.findtext(".//h:author//h:representedOrganization/h:name", namespaces=NS) or "").strip()
    draft = {
        "kind": "visit", "service_date": as_of, "provider": provider or None,
        "title": (root.findtext("h:title", namespaces=NS) or "").strip() or "Health summary from a patient portal",
        "medications": meds,
        "lab_results": each("results", _results) + each("vitals", _results),
        "allergies": each("allergies", _allergies), "problems": list(dict.fromkeys(each("problems", _problems))),
        "immunizations": each("immunizations", _immunizations),
    }
    return {**draft, "summary": _summary(draft)}
