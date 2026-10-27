#!/usr/bin/env python3
"""Check the reference table's enforcement counts against CMS, live.

Run from the project root:  python3 tools/verify_enforcement.py

Why this exists. The Assignment 3 feedback docked half a point because "the quality report
is made by the Python build step" — a dataset certified by the same code that produced it
is not checked, it is asserted. This is the independent check: a second implementation,
written later and from the data's side rather than the builder's, re-pulling CMS's
Hospital Price Transparency enforcement file in full and comparing hospital by hospital.

It paginates to exhaustion deliberately. The submitted n8n workflow read `?size=5000` with
no offset loop and so saw 5,000 of 13,355 actions; this reads all of them, which is how
the comparison can mean anything.

What it found on its first run (2026-10-26) is the reason it is worth keeping: two
hospitals recorded as 0 enforcement actions are not clean records, they are failed joins.
"BAYLOR SCOTT & WHITE ALL SAINTS MEDICAL CENTER - FORT WORTH" is listed by CMS without the
city suffix and has 2 actions; "Community Hospital of Stokes" is listed as "LIFEBRITE
COMMUNITY HOSPITAL OF STOKES" and has 5. A zero that means "not found" and a zero that
means "nothing happened" are different claims, and this project's own caveats say so.
"""
import collections
import csv
import difflib
import json
import pathlib
import sys
import urllib.request

BASE = ("https://data.cms.gov/data-api/v1/dataset/"
        "6a3aa708-3c9d-411a-a1a4-e046d3ade7ef/data")
UA = {"User-Agent": "medvault/1.0 (INFO7375 coursework; python-urllib)"}
PAGE = 5000
ROOT = pathlib.Path(__file__).resolve().parent.parent
TABLE = ROOT / "data" / "a3_reference_table.csv"


def pull_all():
    """Every enforcement action, not the first page of them."""
    rows, offset = [], 0
    while True:
        req = urllib.request.Request(f"{BASE}?size={PAGE}&offset={offset}", headers=UA)
        with urllib.request.urlopen(req, timeout=90) as r:
            batch = json.loads(r.read())
        if not batch:
            break
        rows += batch
        offset += PAGE
        if len(batch) < PAGE:
            break
    return rows


def counts_by_hospital(actions):
    out = collections.Counter()
    for a in actions:
        out[(a["Hosp_Name"].strip().upper(), a["State"].strip().upper())] += 1
    return out


def table_claims(path=TABLE):
    claims = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        key = (r["hospital_name"].strip().upper(), r["hospital_state"].strip().upper())
        claims[key] = (int(r["hospital_cms_enforcement_actions"] or 0),
                       r["enforcement_match_method"])
    return claims


def compare(claims, live):
    """One row per hospital: what the table says, what CMS says, and the nearest name
    when the two do not join."""
    report = []
    by_state = collections.defaultdict(set)
    for name, state in live:
        by_state[state].add(name)

    for (name, state), (claimed, method) in sorted(claims.items()):
        actual = live.get((name, state), 0)
        near = []
        if actual == 0:
            for candidate in difflib.get_close_matches(name, by_state[state], n=3,
                                                       cutoff=0.6):
                near.append((candidate, live[(candidate, state)]))
        report.append({"hospital": name, "state": state, "claimed": claimed,
                       "exact_match": actual, "method": method, "near": near})
    return report


def main():
    actions = pull_all()
    print(f"CMS enforcement actions pulled: {len(actions):,}\n")
    live = counts_by_hospital(actions)
    report = compare(table_claims(), live)

    agree = [r for r in report if r["claimed"] == r["exact_match"]]
    print(f"{len(agree)}/{len(report)} hospitals agree exactly with the live file.\n")

    suspect = [r for r in report if r["exact_match"] == 0 and r["near"]]
    if suspect:
        print("Zeros that are probably failed joins rather than clean records:")
        for r in suspect:
            print(f"\n  table : {r['hospital']} ({r['state']}) -> "
                  f"{r['claimed']} action(s), matched by {r['method']}")
            for candidate, n in r["near"]:
                print(f"  CMS   : {candidate} -> {n} action(s)")
    else:
        print("No zero in the table has a near-name in CMS with actions against it.")

    return 1 if suspect else 0


if __name__ == "__main__":
    sys.exit(main())
