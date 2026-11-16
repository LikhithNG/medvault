#!/usr/bin/env python3
"""Reading a patient portal's record file (HL7 C-CDA) with no AI at all.

The idea is Mere Medical's (github.com/cfu288/mere-medical, MIT), which reads these files
section by section by template id. A portal file carries the names, codes and dates the
hospital itself stored, so nothing has to be guessed off a photograph - and most of these
tests are about the places where a careless reader would still guess: an as-needed
inhaler put on a clock, a finished course left on the card, a file that is not a medical
record at all, or one built to attack the parser.

Run with  python3 tests/test_ccda.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import ccda       # noqa: E402
import schedule   # noqa: E402

SAMPLE = (ROOT / "tests" / "fixtures" / "portal_summary.xml").read_bytes()


def draft():
    return ccda.read(SAMPLE)


def med(name):
    return next(m for m in draft()["medications"] if m["name"].startswith(name))


def result(code, date):
    return next(r for r in draft()["lab_results"] if r["code"] == code and r["taken_on"] == date)


# ---- the document itself -----------------------------------------------------------

def test_the_document_is_filed_as_a_visit_summary_with_its_own_date_and_source():
    d = draft()
    assert (d["kind"], d["service_date"], d["provider"]) == ("visit", "2026-10-14", "Back Bay Family Practice")
    assert d["title"] == "Continuity of Care Document"


# ---- medicines ------------------------------------------------------------------------

def test_a_medicine_keeps_its_name_dose_and_how_often():
    inhaler = med("Fluticasone")
    assert inhaler["dose"] == "2 puffs"
    assert inhaler["frequency"] == "twice daily"
    assert inhaler["reason"] == "Asthma"
    assert schedule.times_for(schedule.parse(inhaler["frequency"])) == ["08:00", "20:00"]


def test_a_unitless_dose_takes_its_form_from_the_product():
    """doseQuantity value="1" with no unit, on "Montelukast 10 MG Oral Tablet"."""
    assert med("Montelukast")["dose"] == "1 tablet"


def test_a_course_with_an_end_date_ends_on_that_date():
    """The file says the course runs 12 Oct to 10 Nov. The Scheduler counts a duration from
    the record's date, which for a summary exported on 14 Oct would ring two days past the
    end - so the end date itself goes in, and the Scheduler takes it over the count."""
    import datetime
    montelukast = med("Montelukast")
    assert montelukast["duration"] == "30 days, until 2026-11-10"
    assert schedule.course_end({**montelukast, "service_date": "2026-10-14"}) == datetime.date(2026, 11, 10)


def test_an_as_needed_medicine_is_never_turned_into_a_timetable():
    """The file says every 4 hours, and also that it is only for wheezing. Read as "every
    4 hours" alone, the Scheduler would ring a rescue inhaler six times a day."""
    reliever = med("Albuterol")
    assert "as needed" in reliever["frequency"]
    assert schedule.parse(reliever["frequency"])["prn"]


def test_a_finished_course_arrives_finished():
    assert med("Prednisone")["active"] is False
    assert med("Montelukast")["active"] is True


# ---- results, allergies, problems, vaccines ----------------------------------------------

def test_each_result_keeps_its_own_date_code_unit_range_and_flag():
    """A portal file holds results from many visits; each keeps the date it was taken."""
    a1c = result("4548-4", "2026-10-12")
    assert (a1c["value"], a1c["unit"], a1c["reference_range"], a1c["flag"]) == ("6.1", "%", "4.0-5.6", "H")
    assert result("4548-4", "2026-04-12")["value"] == "5.9"
    glucose = result("2345-7", "2026-10-12")
    assert (glucose["value"], glucose["reference_range"]) == ("110", "70-99")


def test_a_text_result_is_kept_and_a_normal_flag_is_not_invented_as_a_warning():
    protein = result("5804-0", "2026-10-12")
    assert protein["value"] == "Negative"
    assert protein["flag"] is None


def test_vital_signs_come_in_as_results():
    bp = result("8480-6", "2026-10-12")
    assert (bp["value"], bp["unit"]) == ("128", "mm[Hg]")


def test_an_allergy_is_read_with_its_reaction_from_the_narrative():
    assert draft()["allergies"] == ["Penicillin G (hives)"]


def test_problems_and_vaccines_are_read():
    d = draft()
    assert d["problems"] == ["Asthma"]
    assert d["immunizations"] == [{"name": "Influenza, seasonal, injectable, preservative free",
                                   "date": "2025-10-01"}]
    assert "Influenza" in d["summary"] and "1 allergy" in d["summary"]


# ---- what it refuses ------------------------------------------------------------------------

def _refused(data):
    try:
        ccda.read(data)
    except ValueError:
        return True
    return False


def test_a_file_that_is_not_a_medical_record_is_refused():
    assert _refused(b"<html><body>not a record</body></html>")
    assert _refused(b"%PDF-1.4 binary")
    assert _refused(b"")


def test_an_xml_bomb_is_refused_not_expanded():
    """Entity expansion ("billion laughs") and external entities are an XML parser's two
    classic ways to be attacked through an upload."""
    bomb = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
            b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
            b'<ClinicalDocument xmlns="urn:hl7-org:v3"><title>&lol2;</title></ClinicalDocument>')
    external = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                b'<ClinicalDocument xmlns="urn:hl7-org:v3"><title>&x;</title></ClinicalDocument>')
    assert _refused(bomb)
    assert _refused(external)


def _with(old, new):
    assert SAMPLE.count(old) >= 1, old
    return ccda.read(SAMPLE.replace(old, new, 1))


def test_an_impossible_interval_is_not_turned_into_a_schedule():
    """period value="1e999" raised OverflowError and took the Add screen down; "0 days"
    was read as weekly; "-4 hours" and a 300-digit period became frequencies."""
    for bad in (b"1e999", b"inf", b"nan", b"0", b"-4", b"1e308"):
        d = _with(b'<period value="12" unit="h"/>', b'<period value="' + bad + b'" unit="h"/>')
        assert next(m for m in d["medications"] if m["name"].startswith("Fluticasone"))["frequency"] is None, bad


def test_an_impossible_dose_is_left_empty():
    for bad in (b"nan", b"-1", b"inf", b"0"):
        d = _with(b'<doseQuantity value="2" unit="{puff}"/>', b'<doseQuantity value="' + bad + b'" unit="{puff}"/>')
        assert next(m for m in d["medications"] if m["name"].startswith("Fluticasone"))["dose"] is None, bad


def test_a_file_too_large_to_be_one_patients_summary_is_refused():
    assert _refused(b"<a>" + b" " * (ccda.MAX_BYTES + 1) + b"</a>")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
