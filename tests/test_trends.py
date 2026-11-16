#!/usr/bin/env python3
"""Lab results over time, and a search that understands plain words.

Both ideas are Mere Medical's (github.com/cfu288/mere-medical, MIT). Mere groups every
result by its LOINC code, merges the identical ones that arrived twice, and shows earlier
values beside the latest. And a Mere user searched "high blood sugar", found nothing, and
reported search as broken; Mere's answer was AI embeddings sent to OpenAI. Here the answer
is a short local list of plain words, so a search sends nothing anywhere.

Run with  python3 tests/test_trends.py
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
import accounts, ccda, db, lay_terms, trends                         # noqa: E402


def row(name, value, date, code=None, unit="%", record_id=1, flag=None):
    return {"name": name, "value": value, "unit": unit, "date": date, "code": code, "flag": flag,
            "reference_range": None, "record_id": record_id, "record_title": "Panel", "provider": None}


def by_name(groups, name):
    return next(g for g in groups if g["name"] == name)


# ---- grouping --------------------------------------------------------------------------

def test_results_with_the_same_code_are_one_test_oldest_first():
    groups = trends.series([row("Hemoglobin A1c", "6.1", "2026-10-12", code="4548-4"),
                            row("HbA1c", "5.9", "2026-04-12", code="4548-4")])
    assert len(groups) == 1
    assert [p["value"] for p in groups[0]["points"]] == ["5.9", "6.1"]


def test_an_uncoded_result_joins_the_coded_test_of_the_same_name():
    groups = trends.series([row("Hemoglobin A1c", "6.1", "2026-10-12", code="4548-4"),
                            row("hemoglobin a1c", "5.7", "2025-10-01")])
    assert len(groups) == 1 and len(groups[0]["points"]) == 2


def test_similar_names_that_are_different_tests_stay_apart():
    """Haemoglobin and haemoglobin A1c are different tests; merging them would draw a
    blood count and a diabetes marker on one line."""
    groups = trends.series([row("Hemoglobin", "13.2", "2026-10-12", unit="g/dL"),
                            row("Hemoglobin A1c", "6.1", "2026-10-12")])
    assert len(groups) == 2


def test_the_same_result_from_two_documents_is_shown_once():
    """A discharge summary and the lab's own report both carry the 12 Oct A1c."""
    groups = trends.series([row("Hemoglobin A1c", "6.1", "2026-10-12", record_id=1),
                            row("Hemoglobin A1c", "6.1", "2026-10-12", record_id=2),
                            row("Hemoglobin A1c", "5.9", "2026-04-12", record_id=2)])
    points = groups[0]["points"]
    assert [p["value"] for p in points] == ["5.9", "6.1"]
    assert points[-1]["sources"] == 2


def test_a_chart_is_offered_only_for_numbers_in_one_unit():
    numbers = trends.series([row("Glucose", "110", "2026-10-12", unit="mg/dL"),
                             row("Glucose", "98", "2026-04-12", unit="mg/dL")])[0]
    words = trends.series([row("Protein", "Negative", "2026-10-12", unit=None),
                           row("Protein", "Trace", "2026-04-12", unit=None)])[0]
    mixed = trends.series([row("Glucose", "6.1", "2026-10-12", unit="mmol/L"),
                           row("Glucose", "110", "2026-04-12", unit="mg/dL")])[0]
    assert numbers["chartable"] and not words["chartable"] and not mixed["chartable"]


def test_an_undated_result_is_listed_but_not_placed_on_a_timeline():
    group = trends.series([row("Glucose", "110", None, unit="mg/dL"),
                           row("Glucose", "98", "2026-04-12", unit="mg/dL")])[0]
    assert [p["date"] for p in group["points"]] == ["2026-04-12", None]
    assert not group["chartable"]


# ---- from the vault -------------------------------------------------------------------------

def two_patients():
    con = db.connect(tempfile.mktemp(suffix=".db"))
    a, _ = accounts.create(con, email="a@example.com", password="12345678", role="patient")
    b, _ = accounts.create(con, email="b@example.com", password="12345678", role="patient")
    return con, a["id"], b["id"]


def test_a_portal_files_results_keep_their_own_dates_in_the_vault():
    con, me, other = two_patients()
    draft = ccda.read((ROOT / "tests" / "fixtures" / "portal_summary.xml").read_bytes())
    rid = db.add_record(con, kind="visit", title=draft["title"], service_date=draft["service_date"],
                        owner_id=me, read_by=ccda.READER)
    db.add_lab_results(con, rid, draft["lab_results"])
    a1c = next(g for g in trends.history(con, [me]) if g["key"] == "4548-4")
    assert [(p["date"], p["value"]) for p in a1c["points"]] == [("2026-04-12", "5.9"), ("2026-10-12", "6.1")]
    assert trends.history(con, [other]) == [], "B was shown A's results"


def test_an_ai_read_result_falls_back_to_its_documents_date():
    con, me, _ = two_patients()
    rid = db.add_record(con, kind="lab", title="Panel", service_date="2026-03-14", owner_id=me)
    db.add_lab_results(con, rid, [{"name": "Sodium", "value": "140", "unit": "mmol/L"}])
    [group] = trends.history(con, [me])
    assert group["points"][0]["date"] == "2026-03-14"


# ---- plain-word search ----------------------------------------------------------------------

def test_plain_words_also_search_for_the_clinical_ones():
    terms = lay_terms.expand("high blood sugar")
    assert terms[0] == "high blood sugar"
    assert {"diabetes", "glucose", "a1c"} <= set(terms)
    assert lay_terms.expand("amoxicillin") == ["amoxicillin"]


def test_no_extra_term_is_short_enough_to_match_half_the_vault():
    """A search runs as LIKE '%term%': "ct" would match every doctor and every practice."""
    extra = {t for terms in lay_terms.LAY_TERMS.values() for t in terms}
    assert all(len(t) >= 3 for t in extra), sorted(t for t in extra if len(t) < 3)


def test_searching_in_plain_words_finds_the_clinical_record():
    con, me, other = two_patients()
    db.add_record(con, kind="visit", title="Diabetes review", owner_id=me)
    db.add_record(con, kind="visit", title="Diabetes review", owner_id=other)
    found = db.list_records(con, query="high blood sugar", owner_id=me)
    assert [r["title"] for r in found] == ["Diabetes review"]


def test_a_search_finds_a_record_by_a_result_or_a_medicine_on_it():
    con, me, _ = two_patients()
    lab = db.add_record(con, kind="lab", title="Blood panel", owner_id=me)
    db.add_lab_results(con, lab, [{"name": "Hemoglobin A1c", "value": "6.1"}])
    rx = db.add_record(con, kind="prescription", title="Script", owner_id=me)
    db.add_medication(con, rx, {"name": "Metformin", "dose": "500 mg"})
    assert [r["title"] for r in db.list_records(con, query="a1c", owner_id=me)] == ["Blood panel"]
    assert [r["title"] for r in db.list_records(con, query="metformin", owner_id=me)] == ["Script"]


# ---- the card ----------------------------------------------------------------------------------

def test_allergies_from_a_file_are_added_to_the_card_without_repeating_one():
    assert ccda.merged("", ["Penicillin G (hives)"]) == "Penicillin G (hives)"
    assert ccda.merged("Peanuts", ["Penicillin G (hives)"]) == "Peanuts, Penicillin G (hives)"
    assert ccda.merged("Penicillin G (hives)", ["penicillin g (hives)"]) == "Penicillin G (hives)"
    assert ccda.merged("Latex; Penicillin G", ["Penicillin G"]) == "Latex; Penicillin G"


def test_an_allergy_that_only_looks_like_one_on_the_card_is_still_added():
    """A part of a word is not the same allergy, and on an emergency card a missing
    allergy is the dangerous mistake. A substring test hid all of these."""
    assert ccda.merged("Peanut", ["Nut"]) == "Peanut, Nut"
    assert ccda.merged("Amoxicillin", ["Moxi"]) == "Amoxicillin, Moxi"
    assert ccda.merged("sulfa allergy not penicillin", ["Penicillin"]) == "sulfa allergy not penicillin, Penicillin"


def test_a_new_reaction_to_a_known_allergy_is_added_not_dropped():
    assert (ccda.merged("Penicillin (rash)", ["Penicillin (anaphylaxis)"])
            == "Penicillin (rash), Penicillin (anaphylaxis)")


def test_no_known_allergies_gives_way_to_the_allergies_the_file_lists():
    assert ccda.merged("No known allergies", ["Latex"]) == "Latex"
    assert ccda.merged("NKDA", ["Latex"]) == "Latex"


def test_a_typed_result_date_that_is_not_a_date_is_not_stored():
    """The review screen lets a patient edit each result's date. "2026-13-45" reached the
    chart, which raised on every load of the Records screen."""
    con, me, _ = two_patients()
    rid = db.add_record(con, kind="lab", title="Panel", service_date="2026-03-14", owner_id=me)
    db.add_lab_results(con, rid, [{"name": "Sodium", "value": "140", "taken_on": "2026-13-45"},
                                  {"name": "Sodium", "value": "138", "taken_on": "banana"}])
    assert {r["taken_on"] for r in db.lab_results_by_record(con, [me])[rid]} == {None}


def test_a_point_whose_date_is_not_a_date_is_never_charted():
    group = trends.series([row("Glucose", "110", "2026-13-45", unit="mg/dL"),
                           row("Glucose", "98", "2026-04-12", unit="mg/dL")])[0]
    assert not group["chartable"]


def test_an_empty_unit_and_no_unit_are_the_same_unit():
    group = trends.series([row("Protein", "1", "2026-10-12", unit=None),
                           row("Protein", "1", "2026-10-12", unit=""),
                           row("Protein", "2", "2026-04-12", unit="")])[0]
    assert len(group["points"]) == 2 and group["chartable"]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
