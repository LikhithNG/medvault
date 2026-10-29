#!/usr/bin/env python3
"""Measure the Reader on the photographs a patient actually sends.

    python3 tools/reader_eval.py              # every sample photo, through the real model
    python3 tools/reader_eval.py --bills 3    # fewer bills, fewer model calls

tools/accuracy_test.py measures the Checker, and its --reader mode hands the Reader each
bill as text. A patient sends a photograph. This reads the sample photographs in samples/
through the same path the Bill and Add screens use (extract.read_bill_verified and
extract.read_document, image in) and scores what comes back against what is printed.

For a bill, the truth is the bill's own text file beside its photo, parsed by the same
parser the Bill screen uses for pasted lines. A line is read right when its code, its
quantity and its amount all match a printed line; a line that matches none was invented.
For the prescription, the truth is what the page says, written down below.

Synthetic documents only - every sample says so on its face. Each bill is one or two
model calls and the prescription one, so the whole run is under twenty requests.
Results go to outputs/reader_eval.json.
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tools"))

from accuracy_test import wilson   # noqa: E402

SAMPLES = ROOT / "samples"
OUT = ROOT / "outputs" / "reader_eval.json"

# What samples/prescription_photo.jpg says, read off the page by a person.
PRESCRIPTION = {
    "kind": "prescription",
    "service_date": "2026-09-18",
    "provider_mentions": ("riverbend", "osei"),
    "medications": [
        {"name": "amoxicillin", "dose": "875", "per_day": 2, "prn": False, "days": "10"},
        {"name": "fluticasone", "dose": "50", "per_day": 1, "prn": False, "days": "21"},
        {"name": "ibuprofen", "dose": "400", "per_day": None, "prn": True, "days": "5"},
    ],
}


def score_bill(truth, read):
    """(lines read right, printed lines missed, lines invented) - matched as multisets,
    so the order the model lists them in does not matter."""
    left = list(read)
    right, missed = 0, []
    for want in truth:
        hit = next((g for g in left
                    if (g.get("code") or "") == (want.get("code") or "")
                    and int(g.get("units") or 1) == int(want.get("units") or 1)
                    and isinstance(g.get("charged"), (int, float))
                    and abs(g["charged"] - want["charged"]) < 0.005), None)
        if hit is None:
            missed.append(want)
        else:
            right += 1
            left.remove(hit)
    return right, missed, left


def score_prescription(record, truth=PRESCRIPTION):
    """Every fact on the page the record should carry: [(check, passed)]."""
    import schedule
    checks = [("kind", record.get("kind") == truth["kind"]),
              ("date", record.get("service_date") == truth["service_date"]),
              ("provider", any(w in (record.get("provider") or "").lower()
                               for w in truth["provider_mentions"]))]
    meds = record.get("medications") or []
    checks.append(("medicine count", len(meds) == len(truth["medications"])))
    for want in truth["medications"]:
        got = next((m for m in meds if want["name"] in (m.get("name") or "").lower()), None)
        name = want["name"]
        checks.append((f"{name}: found", got is not None))
        if got is None:
            continue
        parsed = schedule.parse(got.get("frequency"))
        checks += [(f"{name}: dose", want["dose"] in (got.get("dose") or "")),
                   (f"{name}: as needed", parsed["prn"] == want["prn"]),
                   (f"{name}: times a day",
                    want["prn"] or parsed["per_day"] == want["per_day"]),
                   (f"{name}: duration", want["days"] in (got.get("duration") or ""))]
    return checks


def run(bills=None):
    import extract
    import paste
    report = {"when": datetime.datetime.now().isoformat(timespec="seconds"),
              "bills": [], "prescription": None}
    photos = sorted((SAMPLES / "bills").glob("*.jpg"))[:bills]
    for photo in photos:
        truth = paste.lines((photo.with_suffix(".txt")).read_text())
        started = time.perf_counter()
        read, meta = extract.read_bill_verified(image=("image/jpeg", photo.read_bytes()))
        right, missed, invented = score_bill(truth, read if meta.get("ok") else [])
        report["bills"].append({
            "bill": photo.stem, "ok": bool(meta.get("ok")), "error": meta.get("error"),
            "model": meta.get("model"), "provider": meta.get("provider"),
            "reconciled": meta.get("reconciled"), "attempts": meta.get("attempts"),
            "printed": len(truth), "read_right": right,
            "missed": [f"{m.get('code')} {m.get('charged')}" for m in missed],
            "invented": [f"{g.get('code')} {g.get('charged')}" for g in invented],
            "seconds": round(time.perf_counter() - started, 1)})

    photo = SAMPLES / "prescription_photo.jpg"
    started = time.perf_counter()
    record, meta = extract.read_document(image=("image/jpeg", photo.read_bytes()))
    checks = score_prescription(record or {}) if meta.get("ok") else []
    report["prescription"] = {
        "ok": bool(meta.get("ok")), "error": meta.get("error"), "model": meta.get("model"),
        "checks": [{"check": c, "passed": p} for c, p in checks],
        "passed": sum(p for _, p in checks), "total": len(checks),
        "seconds": round(time.perf_counter() - started, 1), "read": record}

    printed = sum(b["printed"] for b in report["bills"])
    right = sum(b["read_right"] for b in report["bills"])
    invented = sum(len(b["invented"]) for b in report["bills"])
    lo, hi = wilson(right, printed)
    report["totals"] = {"printed_lines": printed, "read_right": right,
                        "line_accuracy": round(right / printed, 4) if printed else None,
                        "ci": [round(lo, 4), round(hi, 4)], "invented_lines": invented,
                        "bills_reconciled": sum(b["reconciled"] is True
                                                for b in report["bills"]),
                        "bills": len(report["bills"])}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--bills", type=int, default=None, help="read only the first N bills")
    args = parser.parse_args()
    report = run(args.bills)
    for b in report["bills"]:
        mark = "ok  " if b["read_right"] == b["printed"] and not b["invented"] else "MISS"
        print(f"  {mark} {b['bill']:<26} {b['read_right']}/{b['printed']} lines"
              f" · reconciled {b['reconciled']} · {b['model'] or b['error']} · {b['seconds']}s"
              + (f" · missed {b['missed']}" if b["missed"] else "")
              + (f" · invented {b['invented']}" if b["invented"] else ""))
    p = report["prescription"]
    print(f"\n  prescription: {p['passed']}/{p['total']} facts · {p['model'] or p['error']}"
          f" · {p['seconds']}s")
    for c in p["checks"]:
        if not c["passed"]:
            print(f"    MISSED {c['check']}")
    t = report["totals"]
    print(f"\n  bill lines read right: {t['read_right']}/{t['printed_lines']}"
          f" · 95% CI [{100 * t['ci'][0]:.1f}%, {100 * t['ci'][1]:.1f}%]"
          f" · invented {t['invented_lines']} · reconciled {t['bills_reconciled']}/{t['bills']}")
    OUT.write_text(json.dumps(report, indent=1, default=str))
    print(f"written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
