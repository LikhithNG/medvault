#!/usr/bin/env python3
"""Turning the lines of a bill somebody typed or pasted into line items.

Lifted out of app.py so it is one implementation rather than two. The Bill screen and
tools/make_outputs.py both call this, which is the only way the sample letters in
outputs/ can honestly be described as what the app produces - a second copy of a parser
drifts from the first one, quietly, and then the documentation is wrong without anybody
editing it.
"""
import re

from codes import find_code

DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
MONEY = re.compile(r"([\d,]+\.\d{2})")
# The quantity column: a bare integer sitting between the description and the amount.
QTY = re.compile(r"(?:^|\s)(\d{1,3})\s+[\d,]+\.\d{2}\s*$")


def line(raw):
    """One row in, one line item out. None for a row with nothing on it."""
    raw = (raw or "").strip()
    if not raw:
        return None

    found_date = DATE.search(raw)
    amounts = MONEY.findall(raw)
    code = find_code(raw)

    # The quantity this parser used to ignore entirely and set to 1. A blood draw billed
    # 2 at a published $50 is $100 and correct; read as one unit it looked like $50 over,
    # and the letter said so in writing.
    qty = QTY.search(raw)
    units = int(qty.group(1)) if qty else 1

    # The description is what is left once the date, the code and the money have been
    # taken out. Keeping the whole row printed "72148 2026-03-14 72148 MRI LUMBAR" on the
    # card - the code twice and a date nobody needed there.
    desc = raw
    for part in filter(None, [found_date.group(0) if found_date else None, code] + amounts):
        desc = desc.replace(part, " ")
    desc = re.sub(r"\s{2,}", " ", desc).strip(" \t|,-")
    if qty:
        # Strip the quantity off the end of what is left. Slicing by the match's own
        # offsets does not work: those index the original row, and the amounts and the
        # code have already been removed from this string.
        desc = re.sub(rf"\s*\b{qty.group(1)}\b\s*$", "", desc).strip()

    return {"description": desc or (code or raw),
            "service_date": found_date.group(0) if found_date else None,
            "code": code, "units": units,
            "charged": float(amounts[-1].replace(",", "")) if amounts else None}


# Words that mark a row as a summary of the bill rather than a charge on it. Only ever
# applied to a row that carries no code: "TOTAL KNEE ARTHROPLASTY" is a procedure.
SUMMARY = ("TOTAL", "SUBTOTAL", "BALANCE", "AMOUNT DUE", "AMOUNT PAID", "PAYMENTS",
           "ADJUSTMENTS", "INSURANCE PAID", "PATIENT RESPONSIBILITY", "DUE BY",
           "PREVIOUS BALANCE", "GRAND TOTAL")


def is_charge(item):
    """Whether a parsed row is a charge, or part of the paperwork around the charges.

    This matters more than it sounds. Pasting the whole bill is the obvious thing to do,
    and without this the statement's own "TOTAL DUE 3,532.00" became an eleventh line
    item with no published price - so the sample bill where every line is exactly at the
    published price reported six flags and $3,532 unexplained. A tool that invents a
    finding on a correct bill is worse than one that finds nothing.
    """
    if not item or item.get("charged") is None:
        return False                      # a header or a note is not a charge
    if item.get("code"):
        return True                       # a coded row is a charge, whatever it is called
    desc = (item.get("description") or "").upper()
    return not any(word in desc for word in SUMMARY)


def lines(text, charges_only=True):
    """The rows of a pasted bill. By default only the ones that are charges."""
    out = [item for item in (line(r) for r in (text or "").splitlines()) if item]
    return [item for item in out if is_charge(item)] if charges_only else out
