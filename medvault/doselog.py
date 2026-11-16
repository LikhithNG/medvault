#!/usr/bin/env python3
"""The dose log and the stock count, in the vault. The arithmetic is doses.py's.

Stock is moved by the log and only by the log, which is what keeps the count honest: a
taken dose takes doses.per_dose() off and records exactly what it took, so undoing it, or
changing it to skipped, puts back that amount and no other. Every change checks whose
medicine it is first; a medicine belongs to the owner of the record it came off.
"""
import math
import time

import db
import doses

DOSE_STATUSES = ("taken", "skipped")
STOCK_MAX = 100_000          # a box, not a warehouse: past this it is a typo (db.TRIGGERS caps at it too)
SMALLEST = 0.01              # a dose or refill smaller than this is a typo, and made run-out dates overflow
_KEEP = object()             # set_stock: "leave this field as it is", as opposed to None, "clear it"


def _quantity(value, positive=False):
    """A stock-sized number, or None. For values from outside: never raises."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None      # NaN compares False with everything, so it passed every check below
    if value < 0 or value > STOCK_MAX or (positive and value < SMALLEST):
        return None
    return float(value)


def _owned_medication(con, med_id, owner_id):
    """The medicine, if it came off one of this owner's records. PermissionError otherwise:
    a stock or log change that does not check whose medicine it is changes anybody's."""
    if owner_id is None:
        raise ValueError("a medicine's stock and doses need to know whose medicine it is")
    row = con.execute("SELECT m.* FROM medications m JOIN records r ON r.id = m.record_id"
                      " WHERE m.id = ? AND r.owner_id = ?", (med_id, owner_id)).fetchone()
    if not row:
        raise PermissionError("that medicine is not in this vault")
    return dict(row)


def set_stock(con, med_id, owner_id, *, stock=_KEEP, per_dose=_KEEP, refill_size=_KEEP, expires=_KEEP):
    """Change what the box holds, how much a dose takes, the refill size or the expiry date.

    Only the fields passed are changed; None clears one. A value that is not a sensible
    count, or a date that is not a date, raises ValueError and nothing is written.
    """
    _owned_medication(con, med_id, owner_id)
    given = {"stock": (stock, False), "per_dose": (per_dose, True), "refill_size": (refill_size, True)}
    changes = {}
    for column, (value, positive) in given.items():
        if value is _KEEP:
            continue
        if value is not None and _quantity(value, positive) is None:
            raise ValueError(f"{column} must be a number from {SMALLEST if positive else 0} "
                             f"to {STOCK_MAX:,}")
        changes[column] = None if value is None else float(value)
    if expires is not _KEEP:
        if expires not in (None, "") and not db._iso_date(expires):
            raise ValueError("expires must be a date such as 2027-01-31")
        changes["expires"] = db._iso_date(expires) if expires else None
    if not changes:
        return
    assignments = ", ".join(f"{column} = ?" for column in changes)    # column names are fixed above
    con.execute(f"UPDATE medications SET {assignments} WHERE id = ?", (*changes.values(), med_id))
    con.commit()


def record_dose(con, med_id, day, at, status, owner_id):
    """Mark one scheduled dose taken or skipped. Returns the stock afterwards (None: not counted).

    Marking a dose again replaces the first mark: its row comes out, and db.TRIGGERS put
    back what it used, before the new row goes in and takes its own amount. Each of the two
    statements moves the log and the box together, so a connection lost between them
    leaves the dose unmarked and the box whole, never one changed without the other. A
    taken dose uses doses.per_dose(), or what is left if that is less; a skipped one uses
    nothing, and a dose with no count ("500 mg") is logged without touching the stock.
    """
    if status not in DOSE_STATUSES:
        raise ValueError(f"a dose is {' or '.join(DOSE_STATUSES)}")
    if not db._iso_date(day) or not db._HHMM.fullmatch(str(at)):
        raise ValueError("a dose needs a date such as 2026-11-03 and a time such as 08:00")
    each = doses.per_dose(_owned_medication(con, med_id, owner_id))
    con.execute("DELETE FROM dose_log WHERE med_id = ? AND day = ? AND at = ?", (med_id, day, at))
    if status == "taken" and each:
        used, used_args = "(SELECT MIN(stock, ?) FROM medications WHERE id = ? AND stock IS NOT NULL)", (each, med_id)
    else:
        used, used_args = "NULL", ()
    # OR IGNORE: if another session marked this dose between the two statements, its mark
    # stands and this one is dropped, rather than raising on the screen. An ignored row
    # fires no trigger, so nothing is taken off twice.
    con.execute(f"INSERT OR IGNORE INTO dose_log (med_id, day, at, status, used, recorded_at)"
                f" VALUES (?, ?, ?, ?, {used}, ?)", (med_id, day, at, status, *used_args, time.time()))
    con.commit()
    return _owned_medication(con, med_id, owner_id)["stock"]


def undo_dose(con, med_id, day, at, owner_id):
    """Take a dose's mark off; db.TRIGGERS put back what it used. Returns whether there was one.

    The amount put back is what the mark took, even if the box was recounted since: a
    recount after a dose already has that dose out of it, so undo it only for a dose
    that was not really taken.
    """
    _owned_medication(con, med_id, owner_id)
    cur = con.execute("DELETE FROM dose_log WHERE med_id = ? AND day = ? AND at = ?", (med_id, day, at))
    con.commit()
    return cur.rowcount == 1


def refill(con, med_id, owner_id):
    """Add the medicine's refill size to its stock. Returns the new stock."""
    med = _owned_medication(con, med_id, owner_id)
    if not med.get("refill_size"):
        raise ValueError("set how many come in a refill first")
    new = min(STOCK_MAX, (med["stock"] or 0) + med["refill_size"])
    con.execute("UPDATE medications SET stock = ? WHERE id = ?", (new, med_id))
    con.commit()
    return new


def dose_log(con, owner_id, since=None):
    """This owner's recorded doses, oldest first, with the medicine's name and dose."""
    if owner_id is None:
        raise ValueError("dose_log needs to know whose doses it is listing")
    sql = ("SELECT l.med_id, l.day, l.at, l.status, l.used, l.recorded_at, m.name, m.dose"
           " FROM dose_log l JOIN medications m ON m.id = l.med_id"
           " JOIN records r ON r.id = m.record_id WHERE r.owner_id = ?")
    args = [owner_id]
    if since:
        sql += " AND l.day >= ?"
        args.append(str(since))
    return db._rows(con.execute(sql + " ORDER BY l.day, l.at, m.name", args))
