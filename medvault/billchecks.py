#!/usr/bin/env python3
"""Checks that need nothing but the bill itself.

Borrowed from DAVANO's `itemize`, which lists these under "needs nothing but the bill" -
the useful observation being that a surprising amount can be found without any price file
at all. No reference data, no network, no model.
"""
import re

# HCPCS Level II codes that exist specifically to mean "not otherwise classified". They are
# legitimate - a new drug needs somewhere to go - but on a patient's bill they are a line
# that declines to say what was provided, and they are worth asking about every time.
UNSPECIFIED = {
    "J3490": "Unclassified drug",
    "J3590": "Unclassified biologic",
    "J9999": "Unclassified chemotherapy drug",
    "A9270": "Non-covered item or service",
    "A9699": "Unclassified radiopharmaceutical",
    "E1399": "Miscellaneous durable medical equipment",
    "J7999": "Compounded drug, not otherwise classified",
    "L9999": "Unclassified orthotic or prosthetic",
    "Q9977": "Unclassified drug or biological",
    "99199": "Unlisted special service or procedure",
}

# A charge that is a round multiple of the unit price is the normal case; anything off by
# more than a cent is either a discount, a surcharge or a mistake, and the patient is
# entitled to know which.
TOLERANCE = 0.01


def arithmetic(line):
    """units x unit price should equal the charge. When it does not, say by how much.

    Only runs when a unit price is genuinely known - printed on the bill, or carried from a
    published price file. It deliberately does NOT run on a price read off a photograph by
    a model: asked for a per-unit column that was not there, the reader divided the charge
    by the quantity instead, which makes the multiplication true by construction and the
    check useless. A check that cannot fail is worse than no check, so bill extraction no
    longer returns a unit price at all.
    """
    units = line.get("units")
    unit_price = line.get("unit_price") or line.get("posted_price")
    charged = line.get("charged")
    if not (isinstance(units, (int, float)) and units > 0
            and isinstance(unit_price, (int, float)) and unit_price > 0
            and isinstance(charged, (int, float))):
        return None

    expected = round(units * unit_price, 2)
    gap = round(charged - expected, 2)
    if abs(gap) <= TOLERANCE:
        return None
    return {
        "rule": "arithmetic",
        "title": "The line does not multiply out",
        "detail": (f"{units:g} at ${unit_price:,.2f} each is ${expected:,.2f}, "
                   f"but the line is billed ${charged:,.2f} — "
                   f"{'over' if gap > 0 else 'under'} by ${abs(gap):,.2f}."),
        "ask": "Ask the billing office to explain how this line was calculated.",
    }


def unspecified(line):
    """A code that declines to say what was provided."""
    code = (line.get("code") or "").strip().upper()
    if code not in UNSPECIFIED:
        return None
    return {
        "rule": "unspecified_code",
        "title": f"Code {code} does not say what this was",
        "detail": (f"{code} means “{UNSPECIFIED[code]}”. It is a real billing code, but it "
                   "identifies nothing specific, so there is no published price to compare "
                   "it against and no way to tell whether the amount is reasonable."),
        "ask": f"Ask what was actually provided under code {code}, and for the price of "
               "the specific item or drug.",
    }


def repeat_key(line):
    """What makes two lines the same charge: the same code on the same day. None for a line
    that cannot be a repeat - no code, or no positive amount.

    The one rule for a duplicate, used here and by the Checker. It used to be "the code
    appears again anywhere on the bill", which called a daily blood count on three days two
    duplicates, and two lines with no code at all duplicates of each other.
    """
    code = (line.get("code") or "").strip().upper()
    charged = line.get("charged")
    if not code or not isinstance(charged, (int, float)) or charged <= 0:
        return None
    return code, line.get("service_date") or None


def duplicates(lines):
    """Every line repeating an earlier line's code on the same day: (line_index, finding).

    Found from the bill alone, so it runs for every bill. It used to need a hospital chosen,
    which left a bill from any hospital not in the price table with no duplicate check.
    """
    seen, out = set(), []
    for i, line in enumerate(lines):
        key = repeat_key(line)
        if key is None:
            continue
        if key not in seen:
            seen.add(key)
            continue
        code, day = key
        what = (line.get("description") or "").strip()
        out.append((i, {
            "rule": "duplicate", "code": code, "charged": line["charged"],
            "description": what, "service_date": day,
            "title": f"Code {code} is billed more than once" + (f" on {day}" if day else ""),
            "detail": (f"{code}{f' ({what})' if what else ''} appears again for "
                       f"${line['charged']:,.2f}. Sometimes that is legitimate — two bags of "
                       "saline in one visit is ordinary — so it is a question, not an "
                       "established error."),
            "ask": (f"Ask whether {code} was provided more than once that day, and to take "
                    "the repeat off the bill if it was not."),
        }))
    return out


CHECKS = (arithmetic, unspecified)


def run(lines):
    """Every bill-only check against every line, in bill order: (line_index, finding)."""
    out = []
    for i, line in enumerate(lines):
        for check in CHECKS:
            found = check(line)
            if found:
                out.append((i, found))
    out += duplicates(lines)
    return sorted(out, key=lambda pair: pair[0])
