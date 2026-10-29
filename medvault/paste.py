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
# An amount, with its sign however the bill writes one: -154.00, (154.00), 154.00 CR,
# -$154.00. It used to read the digits only, so a reversal of $154 became a second $154
# charge - a "duplicate", with a letter asking about it.
MONEY = re.compile(r"(?<![\w.,])(\()?(-)?\$?(-)?(\d{1,3}(?:,\d{3})+|\d+)\.(\d{2})(?!\d)\)?"
                   r"(\s?CR\b)?", re.I)
# Words a bare number follows when it is part of the description, not a quantity: "ED
# VISIT LEVEL 5 8,025.00" was read as five visits, so 5x the posted price looked right.
NOT_A_QUANTITY = re.compile(r"(level|lvl|type|stage|grade|tier|class|no\.?|#|step|room"
                            r"|bed|unit|zone|part|size)", re.I)


def _amount(m):
    value = float(m.group(4).replace(",", "") + "." + m.group(5))
    return -value if (m.group(1) or m.group(2) or m.group(3) or m.group(6)) else value


def _quantity(raw, first):
    """The bare integer just before the row's first amount - the quantity column, whether
    a unit price or the total comes next, and with or without a "$". 1 when there is none."""
    before = raw[:first.start()].rstrip()
    m = re.search(r"(?:^|\s)(\d{1,3})$", before)
    if not m:
        return None
    previous = before[:m.start()].split()[-1:]
    if previous and NOT_A_QUANTITY.fullmatch(previous[0]):
        return None
    return m.group(1)


def line(raw):
    """One row in, one line item out. None for a row with nothing on it."""
    raw = (raw or "").strip()
    if not raw:
        return None

    found_date = DATE.search(raw)
    money = list(MONEY.finditer(raw))
    amounts = [m.group(0) for m in money]
    # The code is looked for once the amounts are out of the row: "MRI LUMBAR 12345.00"
    # gave the amount up as the code.
    unpriced = raw
    for part in amounts:
        unpriced = unpriced.replace(part, " ")
    code = find_code(unpriced)

    # The quantity this parser used to ignore entirely and set to 1. A blood draw billed
    # 2 at a published $50 is $100 and correct; read as one unit it looked like $50 over,
    # and the letter said so in writing.
    qty = _quantity(raw, money[0]) if money else None
    units = int(qty) if qty else 1

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
        desc = re.sub(rf"\s*\b{qty}\b\s*$", "", desc).strip()

    return {"description": desc or (code or raw),
            "service_date": found_date.group(0) if found_date else None,
            "code": code, "units": units,
            "charged": _amount(money[-1]) if money else None}


# Words that mark a row as a summary of the bill rather than a charge on it. Only ever
# applied to a row that carries no code: "TOTAL KNEE ARTHROPLASTY" is a procedure.
# Singular as well as plural: "INSURANCE ADJUSTMENT -1,200.00" and "PAYMENT RECEIVED" were
# read as charges and added to the total.
SUMMARY = ("TOTAL", "SUBTOTAL", "BALANCE", "AMOUNT DUE", "AMOUNT PAID", "PAYMENT",
           "ADJUSTMENT", "INSURANCE PAID", "PATIENT RESPONSIBILITY", "DUE BY",
           "PREVIOUS BALANCE", "GRAND TOTAL", "DISCOUNT", "COPAY", "CO-PAY", "DEDUCTIBLE",
           "COINSURANCE", "CREDIT", "REFUND", "WRITE OFF", "WRITE-OFF", "WRITEOFF",
           "CONTRACTUAL", "PAID")


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
    if item["charged"] < 0:
        return False                      # an uncoded credit is an adjustment, not a charge
    desc = (item.get("description") or "").upper()
    return not any(word in desc for word in SUMMARY)


def lines(text, charges_only=True):
    """The rows of a pasted bill. By default only the ones that are charges."""
    out = [item for item in (line(r) for r in (text or "").splitlines()) if item]
    return [item for item in out if is_charge(item)] if charges_only else out
