#!/usr/bin/env python3
"""Lab results over time: every value of one test, oldest first, the same result once.

The model is Mere Medical's (github.com/cfu288/mere-medical, MIT): results are one test
when they share a LOINC code, and a result that arrived twice - a discharge summary and
the lab's own report both carrying the 12 October A1c - is shown once, counted twice.
Where there is no code, results are one test only when their names match exactly once
case and punctuation are set aside: haemoglobin and haemoglobin A1c are different tests,
and drawing them on one line would be worse than not drawing them at all.

Nothing here judges a value. The flag and the range are the lab's own, as stored.
"""
import datetime
import re

import db

_NUMBER = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*$")


def _name_key(name):
    return " ".join(re.sub(r"[^\w%]+", " ", (name or "").casefold()).split())


def number(value):
    """The value as a number, for a chart; None for "Negative", "<5" and the like."""
    return float(value) if _NUMBER.match(str(value or "")) else None


def _unit(point):
    return (point.get("unit") or "").strip()


def _real_date(value):
    try:
        datetime.date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def _dedupe(points):
    seen = {}
    for point in points:
        same = (point["date"], str(point["value"]).strip(), _unit(point))
        if same in seen:
            seen[same]["sources"] += 1
        else:
            seen[same] = {**point, "sources": 1}
    return list(seen.values())


def _group(key, items):
    points = _dedupe(sorted(items, key=lambda p: (p["date"] is None, p["date"] or "")))
    dated = [p for p in points if p["date"] and _real_date(p["date"])]
    units = {_unit(p) for p in points}
    return {"key": key, "name": points[-1]["name"], "points": points, "latest": points[-1],
            "chartable": (len(dated) == len(points) >= 2 and len(units) == 1
                          and all(number(p["value"]) is not None for p in points))}


def series(rows):
    """Rows (a result plus the date it was taken) grouped into tests, the most-measured first."""
    code_by_name = {}
    for r in rows:
        if r.get("code"):
            code_by_name.setdefault(_name_key(r["name"]), r["code"])
    groups = {}
    for r in rows:
        key = r.get("code") or code_by_name.get(_name_key(r["name"])) or "name:" + _name_key(r["name"])
        groups.setdefault(key, []).append(r)
    return sorted((_group(key, items) for key, items in groups.items()),
                  key=lambda g: (-len(g["points"]), g["name"].casefold()))


def history(con, owner_ids):
    """Every result on these owners' records, grouped into tests. A result's own date when
    its source gave one, else the date on the document it came from."""
    records = {r["id"]: r for r in db.list_records(con, limit=10_000, owner_ids=owner_ids)}
    rows = []
    for record_id, results in db.lab_results_by_record(con, owner_ids).items():
        record = records.get(record_id)
        if not record:
            continue
        rows += [{**t, "date": t.get("taken_on") or record.get("service_date"), "record_id": record_id,
                  "record_title": record["title"], "provider": record.get("provider")} for t in results]
    return series(rows)
