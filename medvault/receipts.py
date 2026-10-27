#!/usr/bin/env python3
"""No receipt, no flag.

The Assignment 2 PRD promised that every flag carries a receipt — the hospital's own
published figure, the basis it was compared on, the file URL and the date that file was
collected — and that this is "enforced in schema, not in a code review". It was not
enforced anywhere, and two of the four fields were not on the object at all.

This is the enforcement. A line whose verdict asserts a dollar comparison has to carry a
complete receipt or it does not get quoted: not in the letter, not on a card, not in an
answer. The point is not tidiness. A patient who walks into a billing office quoting a
figure that cannot be traced back to a document loses the conversation, and a tool that
let them do it caused that.

Verdicts that assert no comparison — a duplicate code, a line that could not be read, a
code the hospital publishes no price for — carry no receipt because there is no published
figure behind them. That is not a missing receipt; it is a different kind of finding, and
the distinction is the whole reason NOT_POSTED must never be rendered as an overcharge.
"""

# The four fields the PRD named, as they are spelled on a checked line.
REQUIRED = ("posted_price", "basis", "source_url", "collected_date")

# Verdicts that put a dollar figure in front of someone and therefore owe a receipt.
ASSERTS_A_COMPARISON = {"ABOVE_POSTED", "QUANTITY_SUSPECT", "VERIFIED"}


def missing_fields(line):
    """Which receipt fields this line is short of. Empty tuple means complete."""
    return tuple(f for f in REQUIRED if line.get(f) in (None, ""))


def owes_a_receipt(line):
    return (line or {}).get("verdict") in ASSERTS_A_COMPARISON


def has_receipt(line):
    return not owes_a_receipt(line) or not missing_fields(line)


def receipt(line):
    """The receipt itself, for rendering. None when the line does not have one."""
    if not owes_a_receipt(line) or missing_fields(line):
        return None
    return {f: line[f] for f in REQUIRED}


def quotable(lines):
    """Split lines into the ones that may be quoted and the ones that may not.

    Returned rather than filtered silently: a dropped line is reported to the reader, so
    the guard can never quietly shrink a letter the way the earlier version of the letter
    quietly dropped a flagged line.
    """
    ok, withheld = [], []
    for line in lines or []:
        (ok if has_receipt(line) else withheld).append(line)
    return ok, withheld


def audit(reviewed):
    """Every line that owes a receipt and does not have one. Empty list means the bill
    passes the guarantee the PRD makes."""
    return [{"code": l.get("code"), "verdict": l.get("verdict"),
             "missing": missing_fields(l)}
            for l in (reviewed or {}).get("lines", []) if not has_receipt(l)]
