#!/usr/bin/env python3
"""A lab report's results, each one as printed.

A lab report used to be filed as a title and a sentence of summary - "Basic metabolic
panel, results within the ranges shown" - and the numbers on it were gone. These tests hold
the Reader to copying each result off the page (name, value, unit, the lab's own range,
and a flag only if the lab printed one), the vault to keeping them with their record, and
the Companion to being able to answer "what was my sodium?" from them, citing the report.

What they also hold: nothing here decides whether a result is normal. The range and the
flag are the lab's, copied; MedVault adds no judgement of its own.
"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tests"))

import accounts   # noqa: E402
import ask        # noqa: E402
import db         # noqa: E402
import extract    # noqa: E402
from schema import LAB_FIELDS   # noqa: E402

SODIUM = {"name": "Sodium", "value": "140", "unit": "mmol/L",
          "reference_range": "135-145", "flag": None}
POTASSIUM = {"name": "Potassium", "value": "5.4", "unit": "mmol/L",
             "reference_range": "3.5-5.1", "flag": "H"}


def _patient(email="p@example.test"):
    con = db.connect(tempfile.mktemp(suffix=".db"))
    me, _ = accounts.create(con, email=email, password="password1", role="patient",
                            display_name="Pat")
    return con, me["id"]


def _panel(con, owner, results=(SODIUM, POTASSIUM)):
    rid = db.add_record(con, kind="lab", title="Basic metabolic panel",
                        service_date="2026-03-14", owner_id=owner)
    for result in results:
        db.add_lab_result(con, rid, result)
    return rid


# ---- what the Reader is asked for -------------------------------------------------------

def test_every_result_field_must_be_answered_even_if_with_null():
    item = extract.SCHEMA["properties"]["lab_results"]["items"]
    assert set(item["required"]) == set(LAB_FIELDS)
    for field in set(LAB_FIELDS) - {"name", "value"}:
        assert item["properties"][field].get("nullable"), field
    assert "lab_results" in extract.SCHEMA["required"], "silence is not an answer"


def test_the_prompt_asks_for_every_result_and_never_for_a_judgement():
    assert "lab_results" in extract.PROMPT
    assert "only if the lab printed one" in extract.PROMPT
    assert "Do not interpret results" in extract.PROMPT


def test_results_are_kept_as_printed():
    rec = extract._shape({"kind": "lab", "lab_results": [
        {"name": " Sodium ", "value": "140", "unit": "mmol/L",
         "reference_range": "135-145", "flag": "null"},
        {"name": "Potassium", "value": "5.4", "unit": "mmol/L",
         "reference_range": "3.5-5.1", "flag": "H"}]})
    assert rec["lab_results"] == [SODIUM, POTASSIUM]


def test_a_result_with_no_name_or_no_value_is_not_a_result():
    rec = extract._shape({"kind": "lab", "lab_results": [
        {"name": "Sodium", "value": None}, {"name": "", "value": "140"},
        "Glucose 5.1", {"name": "Glucose", "value": "5.1"}]})
    assert [r["name"] for r in rec["lab_results"]] == ["Glucose"]
    assert rec["lab_results"][0]["flag"] is None, "a flag must never be filled in"


def test_a_prescription_reads_with_no_results():
    rec = extract._shape({"kind": "prescription", "medications": [{"name": "Albuterol"}]})
    assert rec["lab_results"] == []


def test_a_runaway_answer_is_capped():
    rec = extract._shape({"kind": "lab", "lab_results": [
        {"name": f"Test {n}", "value": str(n)} for n in range(1000)]})
    assert len(rec["lab_results"]) == extract.MAX_LAB_RESULTS


# ---- what the vault keeps --------------------------------------------------------------

def test_results_are_kept_with_their_record():
    con, owner = _patient()
    rid = _panel(con, owner)
    rows = db.lab_results_by_record(con, owner_ids=[owner])[rid]
    assert [(r["name"], r["value"], r["flag"]) for r in rows] == [
        ("Sodium", "140", None), ("Potassium", "5.4", "H")]


def test_one_patients_results_are_not_anothers():
    con, owner = _patient()
    other, _ = accounts.create(con, email="o@example.test", password="password1",
                               role="patient", display_name="Other")
    _panel(con, owner)
    assert db.lab_results_by_record(con, owner_ids=[other["id"]]) == {}
    assert db.lab_results_by_record(con, owner_ids=[]) == {}


def test_deleting_the_report_deletes_its_results_even_without_foreign_keys():
    con, owner = _patient()
    con.execute("PRAGMA foreign_keys = OFF")
    rid = _panel(con, owner)
    assert db.delete_record(con, rid, owner_id=owner)
    assert con.execute("SELECT COUNT(*) AS n FROM lab_results").fetchone()["n"] == 0


def test_results_survive_an_export_and_an_import():
    con, owner = _patient()
    _panel(con, owner)
    exported = db.export_vault(con, owner)
    con2, owner2 = _patient("q@example.test")
    done = db.import_vault(con2, owner2, exported)
    assert done["lab_results_added"] == 2
    [rows] = db.lab_results_by_record(con2, owner_ids=[owner2]).values()
    assert [r["name"] for r in rows] == ["Sodium", "Potassium"]


def test_an_imported_result_with_no_value_is_dropped_not_trusted():
    con, owner = _patient()
    data = {"records": [{"id": 7, "kind": "lab", "title": "Panel"}],
            "lab_results": [{"record_id": 7, "name": "Sodium", "value": ""},
                            {"record_id": 7, "name": ["not", "text"], "value": "1"},
                            {"record_id": 7, "name": "Glucose", "value": "5.1",
                             "flag": "x" * 5000}]}
    done = db.import_vault(con, owner, json.dumps(data))
    assert done["lab_results_added"] == 1
    [rows] = db.lab_results_by_record(con, owner_ids=[owner]).values()
    assert rows[0]["name"] == "Glucose" and len(rows[0]["flag"]) <= 50


def test_an_old_export_with_no_results_still_imports():
    con, owner = _patient()
    done = db.import_vault(con, owner, json.dumps(
        {"records": [{"id": 1, "kind": "lab", "title": "Panel"}]}))
    assert done["records_added"] == 1 and done["lab_results_added"] == 0


# ---- what the Companion is given -------------------------------------------------------

def test_the_companion_reads_each_result_under_its_report():
    con, owner = _patient()
    rid = _panel(con, owner)
    text, sources = ask.context_pack(con, owner)
    head = text.index(f"[record {rid}]")
    sodium = text.index("Sodium: 140 mmol/L (the lab's range 135-145)")
    assert head < sodium, "the result has to sit under the record it is cited by"
    assert "Potassium: 5.4 mmol/L (the lab's range 3.5-5.1) · flagged by the lab: H" in text
    assert rid in sources


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
