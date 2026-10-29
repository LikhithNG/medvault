#!/usr/bin/env python3
"""The Scheduler: when to take what.

The output of this agent is an instruction somebody follows at 2 a.m., so most of these
tests are about what it must refuse to do rather than what it does.
"""
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import schedule   # noqa: E402

TODAY = datetime.date(2026, 10, 27)


def med(name, frequency, **extra):
    return {"id": abs(hash(name)) % 1000, "name": name, "dose": "1 tablet",
            "frequency": frequency, **extra}


# ---- what it refuses ------------------------------------------------------------

def test_as_needed_is_never_put_on_a_clock():
    """The vault's own sample data: ibuprofen "every 8 hours as needed". A naive reminder
    rings three times a day - an NSAID on a timetable the doctor wrote as 'only if you
    need it'."""
    day = schedule.plan([med("Ibuprofen", "every 8 hours as needed")], TODAY)

    assert day["doses"] == []
    assert [e["med"]["name"] for e in day["as_needed"]] == ["Ibuprofen"]


def test_as_needed_never_reaches_the_calendar():
    day = schedule.plan([med("Ibuprofen", "every 8 hours as needed"),
                         med("Amoxicillin", "twice daily")], TODAY)
    ics = schedule.calendar(day)

    assert "Amoxicillin" in ics
    assert "Ibuprofen" not in ics, "an as-needed medicine was turned into an alarm"


def test_a_frequency_it_cannot_read_is_refused_not_guessed():
    for unclear in ("take as directed", "use as instructed", "", None):
        day = schedule.plan([med("Mystery", unclear)], TODAY)
        assert day["doses"] == [], unclear
        assert len(day["unreadable"]) == 1, unclear


def test_a_finished_course_stops_ringing():
    finished = med("Amoxicillin", "three times daily", service_date="2026-03-14",
                   duration="7 days")
    day = schedule.plan([finished], TODAY)

    assert day["doses"] == []
    assert len(day["finished"]) == 1


# ---- what it reads ---------------------------------------------------------------

def test_the_common_frequencies_are_read():
    cases = {"once daily": 1, "twice daily": 2, "three times a day": 3,
             "four times daily": 4, "bid": 2, "tid": 3, "every 8 hours": 3,
             "every 12 hours": 2, "q6h": 4, "at bedtime": 1}
    for text, per_day in cases.items():
        assert len(schedule.times_for(schedule.parse(text))) == per_day, text


def test_twice_daily_is_twelve_hours_apart_from_the_patients_own_morning():
    parsed = schedule.parse("twice daily")
    assert schedule.times_for(parsed) == ["08:00", "20:00"]
    assert schedule.times_for(parsed, day_start="06:30") == ["06:30", "18:30"]


def test_every_n_hours_means_every_n_hours():
    assert schedule.times_for(schedule.parse("every 8 hours"), "06:00") == \
        ["06:00", "14:00", "22:00"]


def test_bedtime_means_bedtime_not_morning():
    assert schedule.times_for(schedule.parse("one tablet at bedtime")) == ["22:00"]


def test_food_instructions_travel_with_the_dose():
    parsed = schedule.parse("three times a day with food")
    assert schedule.note(parsed) == "with food"


def test_weekly_is_listed_rather_than_rung_daily():
    day = schedule.plan([med("Methotrexate", "once weekly")], TODAY)
    assert day["doses"] == [] and len(day["weekly"]) == 1


# ---- course length -----------------------------------------------------------

def test_a_seven_day_course_ends_on_day_seven():
    """14 March is day 1, so day 7 is 20 March. Not 21 March - that is the day after."""
    assert schedule.course_end({"service_date": "2026-03-14", "duration": "7 days"}) == \
        datetime.date(2026, 3, 20)


def test_a_course_with_no_length_has_no_end():
    assert schedule.course_end({"service_date": "2026-03-14"}) is None


def test_the_companion_and_the_scheduler_agree_on_when_a_course_ends():
    """They disagreed by a day. Two agents giving one patient two end dates for one
    prescription is worse than either being slightly wrong alone."""
    import ask
    course = {"service_date": "2026-03-14", "duration": "7 days"}
    assert ask.course_ended(course, TODAY) == schedule.course_end(course)


# ---- the day and the next dose --------------------------------------------------

def test_the_days_doses_come_back_in_time_order():
    day = schedule.plan([med("B", "at bedtime"), med("A", "twice daily")], TODAY)
    assert [d["at"] for d in day["doses"]] == ["08:00", "20:00", "22:00"]


def test_next_due_is_the_next_one_still_to_come():
    day = schedule.plan([med("A", "twice daily")], TODAY)
    noon = datetime.datetime(2026, 10, 27, 12, 0)
    assert schedule.next_due(day, noon)["at"] == "20:00"
    assert schedule.next_due(day, datetime.datetime(2026, 10, 27, 23, 0)) is None


# ---- the calendar file ----------------------------------------------------------

def test_the_calendar_is_well_formed():
    day = schedule.plan([med("Amoxicillin", "twice daily",
                             service_date="2026-10-27", duration="7 days")], TODAY)
    ics = schedule.calendar(day, stamp="20261027T000000Z")

    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == ics.count("END:VEVENT") == 2
    assert ics.count("BEGIN:VALARM") == 2, "a reminder with no alarm does not remind"
    assert "\n" not in ics.replace("\r\n", ""), "bare LF line endings"


def test_no_line_in_the_calendar_is_longer_than_the_spec_allows():
    """RFC 5545: 75 octets. A phone calendar that meets a longer one may drop the event."""
    long_reason = "For a sinus infection that has not cleared after two weeks " * 3
    day = schedule.plan([med("Amoxicillin-Clavulanate", "twice daily",
                             reason=long_reason)], TODAY)
    for line in schedule.calendar(day).split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line[:40]


def test_a_course_with_an_end_stops_repeating_on_that_day():
    day = schedule.plan([med("Amoxicillin", "twice daily", service_date="2026-10-27",
                             duration="7 days")], TODAY)
    assert "RRULE:FREQ=DAILY;UNTIL=20261102T235959" in schedule.calendar(day)


def test_an_open_ended_course_says_to_delete_the_reminder_when_stopping():
    day = schedule.plan([med("Fluticasone", "once daily")], TODAY)
    ics = schedule.calendar(day)
    assert "RRULE:FREQ=DAILY\r\n" in ics
    assert "Delete this reminder" in ics.replace("\r\n ", "")


def test_the_calendar_says_the_time_is_a_suggestion():
    day = schedule.plan([med("Amoxicillin", "twice daily")], TODAY)
    assert "not part of the prescription" in schedule.calendar(day).replace("\r\n ", "")


def test_text_is_escaped_for_the_calendar():
    assert schedule._escape("a;b,c\\d\ne") == r"a\;b\,c\\d\ne"



# ---- from the test pass ------------------------------------------------------------

def test_a_medicine_taken_some_days_is_never_rung_every_day():
    """ "twice a week" was read as twice a DAY, "once a month" as daily: for a weekly drug
    like methotrexate, a daily reminder is exactly how people get hurt."""
    for f in ("twice a week", "three times a week", "3 times weekly", "once a month",
              "monthly", "once every 2 weeks", "fortnightly", "every other day",
              "every other day at bedtime", "on alternate days", "every 3 days",
              "on Mondays at bedtime", "once weekly"):
        day = schedule.plan([med("Methotrexate", f)], TODAY)
        assert day["doses"] == [] and len(day["weekly"]) == 1, f


def test_five_and_six_times_a_day_are_read_as_five_and_six():
    assert schedule.parse("five times daily")["per_day"] == 5
    assert schedule.parse("6 times a day")["per_day"] == 6
    assert len(schedule.times_for(schedule.parse("five times daily"))) == 5


def test_every_way_of_saying_only_if_needed_is_never_rung():
    for f in ("twice daily if required", "when required", "as necessary",
              "if necessary", "one tablet when needed"):
        assert schedule.parse(f)["prn"], f


def test_an_evening_dose_is_given_an_evening_time():
    assert schedule.times_for(schedule.parse("once daily in the evening")) == ["18:00"]
    assert schedule.times_for(schedule.parse("every evening")) == ["18:00"]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
