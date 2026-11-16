#!/usr/bin/env python3
"""Notifications: the browser tells you when a dose is due, when one is still not marked,
and when a box is running low or a medicine is about to expire.

MedTimer (github.com/Futsch1/medTimer, MIT) notifies at each dose, reminds again if
nothing is done, and warns on low stock and expiry. A web app cannot wake a phone, so
these come from the browser while MedVault is open or installed, and the calendar file
stays the reminder that works with the app closed. The plan is worked out here, in
Python, and only shown by the browser; most of these tests are about what it must not
say - a dose already taken, an as-needed medicine, or a medicine's name on a lock screen
when the patient asked for it hidden.

Run with  python3 tests/test_notify.py
"""
import datetime
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import doses      # noqa: E402
import notify     # noqa: E402
import schedule   # noqa: E402

TODAY = datetime.date(2026, 11, 3)


def at(hhmm):
    return datetime.datetime.combine(TODAY, datetime.time.fromisoformat(hhmm))


def med(name="Amoxicillin", frequency="twice daily", med_id=7, **extra):
    return {"id": med_id, "name": name, "dose": "1 tablet", "frequency": frequency, **extra}


def plan(meds, now, logged=(), private=False):
    day = schedule.plan(meds, TODAY)
    return notify.plan(doses.board(day, list(logged), now), meds, now, private=private)


def titles(items):
    return [n["title"] for n in items]


# ---- doses ---------------------------------------------------------------------------------

def test_each_dose_still_to_come_is_announced_at_its_time():
    items = plan([med()], now=at("07:00"))
    due = [n for n in items if n["title"] == "Time for Amoxicillin"]
    assert [n["at"] for n in due] == ["2026-11-03T08:00", "2026-11-03T20:00"]


def test_a_dose_not_marked_is_followed_up_when_it_becomes_not_marked():
    items = plan([med()], now=at("07:00"))
    follow = [n for n in items if n["title"] == "Not marked yet: Amoxicillin"]
    first = at("08:00") + datetime.timedelta(minutes=doses.GRACE_MINUTES)
    assert follow[0]["at"] == first.strftime("%Y-%m-%dT%H:%M")


def test_a_dose_already_marked_is_not_announced_or_followed_up():
    logged = [{"med_id": 7, "day": TODAY.isoformat(), "at": "08:00", "status": "taken"},
              {"med_id": 7, "day": TODAY.isoformat(), "at": "20:00", "status": "skipped"}]
    assert [n for n in plan([med()], now=at("07:00"), logged=logged) if "Amoxicillin" in n["title"]] == []


def test_a_dose_long_past_and_unmarked_is_raised_now_not_at_a_time_gone_by():
    items = plan([med()], now=at("11:00"))
    follow = next(n for n in items if n["tag"].endswith("08:00-check"))
    assert follow["at"] == "2026-11-03T11:00"
    assert not any(n["title"] == "Time for Amoxicillin" and n["at"] == "2026-11-03T08:00" for n in items)


def test_an_as_needed_medicine_never_sends_a_dose_notification():
    items = plan([med("Ibuprofen", "every 8 hours as needed")], now=at("07:00"))
    assert items == []


def test_every_notification_has_its_own_tag_so_none_is_shown_twice():
    items = plan([med(), med("Montelukast", "at bedtime", med_id=8)], now=at("07:00"))
    tags = [n["tag"] for n in items]
    assert len(tags) == len(set(tags))
    assert all(TODAY.isoformat() in t for t in tags), "a tag must name its day, or tomorrow is skipped"


# ---- stock and expiry ----------------------------------------------------------------------

def test_a_box_running_low_is_raised_once_in_the_morning():
    items = plan([med(stock=4)], now=at("07:00"))
    [low] = [n for n in items if n["tag"].startswith("stock-")]
    assert low["at"] == "2026-11-03T09:00"
    assert low["title"] == "Refill Amoxicillin soon"
    assert "4 tablets left" in low["body"]


def test_an_empty_box_is_raised_straight_away():
    [out] = [n for n in plan([med(stock=0)], now=at("15:30")) if n["tag"].startswith("stock-")]
    assert out["at"] == "2026-11-03T15:30" and out["title"] == "Out of Amoxicillin"


def test_a_medicine_about_to_expire_is_raised_and_one_far_off_is_not():
    soon = plan([med(expires="2026-11-20")], now=at("07:00"))
    later = plan([med(expires="2027-06-01")], now=at("07:00"))
    assert [n["title"] for n in soon if n["tag"].startswith("expiry-")] == ["Amoxicillin expires 20 Nov 2026"]
    assert not [n for n in later if n["tag"].startswith("expiry-")]


# ---- privacy and the page ------------------------------------------------------------------

def test_a_private_notification_names_no_medicine():
    """A lock screen is read by whoever picks the phone up."""
    items = plan([med(stock=4, expires="2026-11-20")], now=at("07:00"), private=True)
    assert items and not any("Amoxicillin" in n["title"] + n["body"] for n in items)


def test_a_medicine_name_cannot_break_out_of_the_page_script():
    """Names are read off photographs; one ending a <script> tag must stay text."""
    nasty = med("</script><script>alert(1)</script>")
    html = notify.page(plan([nasty], now=at("07:00")))
    assert "</script><script>alert(1)" not in html
    assert html.count("</script>") == 1


def _run(items, worker="none"):
    """The page's own script in Node against a stand-in browser; None when Node is not here."""
    node = shutil.which("node")
    if not node:
        return None
    harness = ROOT / "tests" / "fixtures" / "notify_harness.js"
    out = subprocess.run([node, str(harness)], input=notify.page(items), capture_output=True,
                         text=True, timeout=30, env={"TZ": "UTC", "PATH": "", "SW": worker})
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


ITEMS = [{"tag": "a", "at": "2026-11-03T07:00", "title": "Past", "body": ""},
         {"tag": "b", "at": "2026-11-03T20:00", "title": "Later", "body": ""}]


def test_the_page_script_shows_what_is_due_once_and_schedules_the_rest():
    result = _run(ITEMS)
    if result is None:
        return
    assert result["shown"] == ["Past"], result
    assert result["scheduled"] == 1, result
    assert result["shown_after_reload"] == ["Past"], "a reload showed the same notification again"


def test_a_service_worker_still_installing_is_waited_for():
    """register() resolves while the worker installs, and showNotification rejects until
    it is active. The first notification after turning them on was lost that way, and
    marked as shown, so it never came back."""
    result = _run(ITEMS, worker="installing")
    if result is None:
        return
    assert result["shown"] == ["Past"], result
    assert result["remembered"] == ["a"], result


def test_a_notification_that_could_not_be_shown_is_not_marked_as_shown():
    result = _run(ITEMS, worker="failing")
    if result is None:
        return
    assert result["shown"] == [] and result["remembered"] == [], result


def test_an_html_comment_in_a_name_does_not_stop_every_notification():
    """"<!--<script>" inside a script puts the HTML parser in a state where the real
    </script> no longer closes it, and the whole page script became a syntax error."""
    nasty = [{"tag": "a", "at": "2026-11-03T07:00", "title": "Time for <!--<script> pills", "body": "<!--"}]
    html = notify.page(nasty)
    assert "<!--" not in html and html.count("<script") == 1
    result = _run(nasty)
    if result is None:
        return
    assert result["shown"] == ["Time for <!--<script> pills"], result


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
