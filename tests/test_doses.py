#!/usr/bin/env python3
"""The dose log and the stock count: what was taken, what was missed, when it runs out.

Ideas taken from MedTimer (github.com/Futsch1/medTimer, MIT): a dose is an event that is
taken or skipped, a skipped dose uses no stock, and stock is counted in the dose's own
unit with no conversion. Like the Scheduler's tests, most of these are about what it must
not claim: a strength is not a count, and a forecast it cannot make is said, not guessed.

Run with  python3 tests/test_doses.py
"""
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import doses      # noqa: E402
import schedule   # noqa: E402

TODAY = datetime.date(2026, 11, 3)


def med(name="Amoxicillin", dose="1 tablet", frequency="twice daily", med_id=7, **extra):
    return {"id": med_id, "name": name, "dose": dose, "frequency": frequency, **extra}


def at(hhmm):
    hour, minute = map(int, hhmm.split(":"))
    return datetime.datetime.combine(TODAY, datetime.time(hour, minute))


def board(meds, now, logged=()):
    day = schedule.plan(meds, TODAY)
    return doses.board(day, list(logged), now)


# ---- reading how much one dose uses ---------------------------------------------

def test_the_count_is_read_off_the_dose():
    assert doses.per_dose(med(dose="1 tablet")) == 1
    assert doses.per_dose(med(dose="2 capsules")) == 2
    assert doses.per_dose(med(dose="½ tablet")) == 0.5
    assert doses.per_dose(med(dose="two puffs")) == 2


def test_only_the_first_number_counts_as_in_medtimer():
    """"1 capsule (25 mg)": one capsule is what leaves the box; 25 mg describes it."""
    assert doses.per_dose(med(dose="1 capsule (25 mg)")) == 1
    assert doses.unit(med(dose="1 capsule (25 mg)")) == "capsule"


def test_a_strength_is_not_a_count():
    """"500 mg" says how strong each tablet is, not how many are taken. Reading 500 off it
    would empty a 30-tablet box on the first dose."""
    for strength in ("500 mg", "0.5 mg", "10 ml/kg", "", None, "as directed"):
        assert doses.per_dose(med(dose=strength)) is None, strength


def test_a_count_the_patient_typed_wins_over_the_label():
    assert doses.per_dose(med(dose="500 mg", per_dose=1)) == 1


# ---- today's doses: taken, skipped, due, missed ------------------------------------

def test_a_dose_still_to_come_is_upcoming():
    rows = board([med()], now=at("07:00"))
    assert [r["status"] for r in rows] == ["upcoming", "upcoming"]


def test_a_dose_whose_time_has_come_is_due_not_missed():
    rows = board([med()], now=at("08:30"))
    assert rows[0]["status"] == "due"


def test_a_dose_long_past_with_nothing_recorded_is_missed():
    late = (datetime.datetime.combine(TODAY, datetime.time(8)) +
            datetime.timedelta(minutes=doses.GRACE_MINUTES + 1))
    rows = board([med()], now=late)
    assert rows[0]["status"] == "missed"
    assert [r["at"] for r in doses.missed(rows)] == ["08:00"]


def test_a_recorded_dose_is_taken_or_skipped_whatever_the_clock_says():
    logged = [{"med_id": 7, "day": TODAY.isoformat(), "at": "08:00", "status": "taken"},
              {"med_id": 7, "day": TODAY.isoformat(), "at": "20:00", "status": "skipped"}]
    rows = board([med()], now=at("23:59"), logged=logged)
    assert [r["status"] for r in rows] == ["taken", "skipped"]
    assert doses.missed(rows) == [], "a dose the patient chose to skip is not a missed dose"


def test_a_log_entry_from_another_day_does_not_count_today():
    logged = [{"med_id": 7, "day": "2026-11-02", "at": "08:00", "status": "taken"}]
    rows = board([med()], now=at("23:59"), logged=logged)
    assert rows[0]["status"] == "missed"


# ---- stock ---------------------------------------------------------------------------

def test_stock_never_goes_below_zero():
    assert doses.after_taking(0.5, 1) == 0
    assert doses.after_taking(10, 2) == 8


def test_a_count_is_said_the_way_a_person_says_it():
    assert doses.count_text(1, "tablet") == "1 tablet"
    assert doses.count_text(9, "tablet") == "9 tablets"
    assert doses.count_text(0, "tablet") == "0 tablets"
    assert doses.count_text(0.5, "tablet") == "0.5 tablet"
    assert doses.count_text(2, "patch") == "2 patches"
    assert doses.count_text(3, "suppository") == "3 suppositories"
    assert doses.count_text(30, "ml") == "30 ml"
    assert doses.count_text(30, None) == "30"


def test_the_run_out_date_follows_the_schedule():
    """Ten tablets, one twice a day: five days."""
    state = doses.stock_state(med(stock=10), TODAY)
    assert state["runs_out"] == TODAY + datetime.timedelta(days=5)
    assert state["level"] == "low"


def test_plenty_left_is_ok():
    state = doses.stock_state(med(stock=60), TODAY)
    assert state["level"] == "ok"
    assert state["runs_out"] == TODAY + datetime.timedelta(days=30)


def test_a_tiny_dose_size_does_not_take_the_screen_down():
    """A per-dose of 0.001 from an import made the run-out date a century past what a
    date can hold, and the Medicines screen raised on every load."""
    for tiny in (0.001, 1e-300):
        state = doses.stock_state(med(stock=100000, per_dose=tiny), TODAY)
        assert state["level"] == "ok", tiny


def test_not_a_number_is_not_a_dose_size():
    assert doses.per_dose(med(dose="500 mg", per_dose=float("nan"))) is None


def test_an_empty_box_is_out():
    assert doses.stock_state(med(stock=0), TODAY)["level"] == "out"


def test_stock_nobody_entered_is_not_tracked():
    assert doses.stock_state(med(), TODAY)["level"] == "untracked"


def test_no_forecast_without_a_count_per_dose():
    """It knows how many are in the box but not how many go per dose: say so."""
    state = doses.stock_state(med(dose="500 mg", stock=30), TODAY)
    assert state["level"] == "unknown"
    assert state["runs_out"] is None


def test_no_forecast_for_an_as_needed_medicine():
    state = doses.stock_state(med(frequency="every 8 hours as needed", stock=20), TODAY)
    assert state["runs_out"] is None
    assert state["level"] == "unknown"


def test_a_course_that_ends_first_needs_no_refill():
    """A seven-day course with fourteen tablets left: it ends before the box does."""
    course = med(stock=40, duration="7 days", service_date=TODAY.isoformat())
    state = doses.stock_state(course, TODAY)
    assert state["runs_out"] is None
    assert state["level"] == "ok"
    assert state["enough"] is True


# ---- expiry ----------------------------------------------------------------------------

def test_expiry_is_flagged_once_passed_and_a_month_before():
    assert doses.expiry_state(med(expires="2026-11-02"), TODAY) == "expired"
    assert doses.expiry_state(med(expires="2026-11-20"), TODAY) == "soon"
    assert doses.expiry_state(med(expires="2027-06-01"), TODAY) is None
    assert doses.expiry_state(med(expires="not a date"), TODAY) is None
    assert doses.expiry_state(med(), TODAY) is None


# ---- the history file ---------------------------------------------------------------------

def test_the_history_csv_has_one_row_per_recorded_dose():
    rows = [{"day": "2026-11-03", "at": "08:00", "name": "Amoxicillin", "dose": "1 tablet",
             "status": "taken", "recorded_at": 1793700000.0}]
    lines = doses.history_csv(rows).strip().splitlines()
    assert lines[0] == "date,scheduled,medicine,dose,status,recorded_at"
    assert lines[1].startswith("2026-11-03,08:00,Amoxicillin,1 tablet,taken,2026-")


def test_a_name_that_looks_like_a_formula_is_not_run_by_a_spreadsheet():
    """Medicine names are read off photographs. A page printed "=HYPERLINK(...)" must reach
    the doctor's spreadsheet as text, not as a live formula."""
    rows = [{"day": "2026-11-03", "at": "08:00", "name": '=HYPERLINK("http://x","y")',
             "dose": "+1", "status": "taken", "recorded_at": 1793700000.0}]
    text = doses.history_csv(rows)
    assert "'=HYPERLINK" in text
    assert ",'+1," in text


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
