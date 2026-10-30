#!/usr/bin/env python3
"""The usability fixes, held in place.

Each test is one finding from the UX review, written so the fix cannot quietly go away:
saves that said nothing, a one-tap removal of a doctor, a "switch them off below" with no
switch, a bill screen that turned away anyone with an empty vault, a sign-out only at the
foot of one screen, text colours under WCAG AA, and paragraphs where a line would do.

The app tests run the real app against a throwaway vault - see test_bill_screen.py for
why that is safe.
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tests"))

import ui                                          # noqa: E402
from test_bill_screen import BILL, _app, _shown, offline_vault   # noqa: E402


def _toasts(at):
    return [t.value for t in at.toast]


def _click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


# ---- visibility of system status ---------------------------------------------------

def test_saving_the_card_says_so():
    """st.success() followed by st.rerun() was wiped before anybody saw it."""
    with offline_vault() as (_, alice, _):
        at = _click(_app(alice), "Save my card")
        assert "Card saved." in _toasts(at)


def test_a_finished_medicine_leaves_the_card_and_says_so():
    """The screen said "switch them off below" and there was no switch."""
    import db
    with offline_vault() as (con, alice, _):
        rx = db.add_record(con, kind="prescription", title="Rx", service_date="2026-10-01",
                           owner_id=alice["id"])
        db.add_medication(con, rx, {"name": "Amoxicillin", "dose": "500 mg",
                                    "frequency": "three times daily"})
        at = _click(_app(alice), "Mark as finished")
        assert db.list_medications(con, active_only=True, owner_id=alice["id"]) == []
        assert any("Amoxicillin marked as finished" in t for t in _toasts(at))
        # A fresh session for the undo: Streamlit 1.37's test runner cannot carry widget
        # state across a run in which the calendar button's contents changed.
        _click(_app(alice), "I'm taking this again")
        assert len(db.list_medications(con, active_only=True, owner_id=alice["id"])) == 1


# ---- error prevention ----------------------------------------------------------------

def test_removing_a_doctor_asks_first():
    import accounts
    import careteam
    with offline_vault() as (con, alice, _):
        accounts.create(con, email="dr@example.test", password="password1", role="clinician",
                        display_name="Dr Who",
                        npi_record={"npi": "0000000000", "name": "WHO", "specialty": "GP",
                                    "license": "X", "license_state": "MA"})
        careteam.add(con, alice["id"], "dr@example.test")
        at = _click(_app(alice), "Remove")
        assert careteam.team(con, alice["id"]), "one tap removed the doctor"
        assert any(b.label == "Keep" for b in at.button)
        _click(at, "Keep")
        assert careteam.team(con, alice["id"])
        at = _click(_click(at, "Remove"), "Yes, remove Dr Who")
        assert careteam.team(con, alice["id"]) == []
        assert any("Removed Dr Who" in t for t in _toasts(at))


def test_deleting_a_record_asks_first_and_takes_only_that_record():
    import db
    with offline_vault() as (con, alice, bob):
        rx = db.add_record(con, kind="prescription", title="Inhaler script",
                           service_date="2026-10-12", owner_id=alice["id"])
        db.add_medication(con, rx, {"name": "Fluticasone", "frequency": "twice daily"})
        at = _app(alice)
        delete = [b for b in at.button if b.label == "Delete"]
        assert len(delete) == 2, "each of Alice's two records gets its own delete"
        delete[0].click().run()
        assert db.get_record(con, rx), "one tap deleted a record"
        assert _shown(at, "Its 1 medicine comes off your card and reminders too")
        _click(at, "Keep it")
        assert db.get_record(con, rx)
        at = _click(_click(at, "Delete"), "Yes, delete it")
        assert db.get_record(con, rx) is None
        assert db.list_medications(con, active_only=False, owner_id=alice["id"]) == []
        assert any("Deleted “Inhaler script”" in t for t in _toasts(at))
        assert len(db.list_records(con, owner_id=bob["id"])) == 1, "Bob's record went too"


def test_a_clinician_is_never_offered_a_delete():
    import accounts
    import careteam
    with offline_vault() as (con, alice, _):
        doc, _ = accounts.create(con, email="dr@example.test", password="password1",
                                 role="clinician", display_name="Dr Who",
                                 npi_record={"npi": "0000000000", "name": "WHO",
                                             "specialty": "GP", "license": "X",
                                             "license_state": "MA"})
        careteam.add(con, alice["id"], "dr@example.test")
        at = _app(doc)
        assert _shown(at, "chest X-ray"), "the clinician should see the record"
        assert not [b for b in at.button if b.label == "Delete"]


def test_the_patient_sees_when_their_doctor_last_saw_their_records():
    import accounts
    import careteam
    with offline_vault() as (con, alice, _):
        doc, _ = accounts.create(con, email="dr@example.test", password="password1",
                                 role="clinician", display_name="Dr Who",
                                 npi_record={"npi": "0000000000", "name": "WHO",
                                             "specialty": "GP", "license": "X",
                                             "license_state": "MA"})
        careteam.add(con, alice["id"], "dr@example.test")
        assert _shown(_app(alice), "No sign-in recorded yet")
        _app(doc)                                  # the doctor signs in
        assert careteam.last_seen(con, alice["id"])[doc["id"]]["visits"] == 1
        assert _shown(_app(alice), "Last signed in with access to your records")


def test_the_sign_in_date_is_the_viewers_day_not_the_servers():
    """From the review: 9:30 pm in Boston is already the next day in UTC."""
    import datetime
    import zoneinfo
    import screen_card
    at = datetime.datetime(2026, 10, 31, 1, 30, tzinfo=datetime.timezone.utc).timestamp()
    line = screen_card._last_saw({"last_seen_at": at, "visits": 2},
                                 zoneinfo.ZoneInfo("America/New_York"))
    assert "30 October 2026" in line and "2 sign-ins" in line


def test_an_overdue_follow_up_offers_the_number_on_the_card():
    import db
    with offline_vault() as (con, alice, _):
        db.save_profile(con, alice["id"], {"gp_name": "Dr. Priya Nair",
                                           "gp_phone": "+1 617 555 0190"})
        db.add_record(con, kind="visit", title="Clinic visit", service_date="2026-10-12",
                      provider="Dr. Priya Nair, Back Bay Family Practice",
                      summary="Follow up in 1 week.", owner_id=alice["id"])
        at = _app(alice)
        html = " ".join(m.value for m in at.markdown)
        assert "href='tel:+16175550190'" in html
        assert "To ask about it" in html


def test_a_lab_reports_results_are_checked_before_filing_and_kept_after():
    import db
    draft = {"kind": "lab", "service_date": "2026-03-14", "provider": "Doylestown Hospital",
             "title": "Basic metabolic panel", "summary": "Blood chemistry results.",
             "medications": [],
             "lab_results": [{"name": "Sodium", "value": "140", "unit": "mmol/L",
                              "reference_range": "135-145", "flag": None},
                             {"name": "Potassium", "value": "5.4", "unit": "mmol/L",
                              "reference_range": "3.5-5.1", "flag": "H"}]}
    def filing(medvault):
        # The Add screen draws this half only while a file sits in its uploader, which
        # the test runner cannot fill - so the half is run on its own.
        import sys
        sys.path.insert(0, medvault)
        import screen_records
        import session
        import ui
        ui.show_flash()                     # app.py's job, on the run after a filing
        screen_records.check_and_file(session.vault())

    with offline_vault() as (con, alice, _):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_resource.clear()
        at = AppTest.from_function(filing, default_timeout=60,
                                   args=(str(ROOT / "medvault"),))
        at.session_state["account"] = alice
        at.session_state["draft"] = draft
        at.session_state["draft_file"] = ("panel.pdf", "application/pdf", b"%PDF-1.4")
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert _shown(at, "Results found · 2")
        _click(at, "File this record")
        assert any("with 2 result(s)" in t for t in _toasts(at))
        [rid] = [r["id"] for r in db.list_records(con, owner_id=alice["id"])
                 if r["title"] == "Basic metabolic panel"]
        assert len(db.lab_results_by_record(con, [alice["id"]])[rid]) == 2
        html = " ".join(m.value for m in _app(alice).markdown)
        assert "<b>Potassium</b><span>5.4 mmol/L · range 3.5-5.1 · flagged H</span>" in html
        assert "Read off the report by an AI reader" in html


# ---- nothing in the way of the first visit -------------------------------------------

def test_a_bill_can_be_checked_before_anything_is_filed():
    """Only the records cross-check needs records; the prices never did."""
    import accounts
    with offline_vault() as (con, _, _):
        carol, _ = accounts.create(con, email="carol@example.test", password="password1",
                                   role="patient", display_name="Carol")
        at = _app(carol)
        assert _shown(at, "Three agents take it from here")
        at.radio(key="bill_source").set_value("Paste the lines").run()
        next(t for t in at.text_area if "Paste" in t.label).set_value(BILL).run()
        _click(at, "Check this bill")
        assert at.session_state["bill_run"]["problem"] is None
        assert {c["verdict"] for c in at.session_state["bill_run"]["checked"]} == {"VAULT_THIN"}


# ---- user control ----------------------------------------------------------------------

def test_the_header_offers_a_way_out_on_every_screen():
    strip = ui.signed_in_strip({"display_name": "A B", "email": "a@b.c", "role": "patient"})
    assert "href='?signout=1'" in strip and "target='_self'" in strip


def test_following_the_header_link_signs_out():
    with offline_vault() as (_, alice, _):
        at = _app(alice)
        at.query_params["signout"] = "1"
        at.run()
        assert "account" not in at.session_state
        assert _shown(at, "panelmark")
        assert not at.query_params.get("signout")


# ---- recognition, and text that gets read ----------------------------------------------

def _literal(node):
    return "".join(n.value for n in ast.walk(node)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str))


def test_no_caption_is_a_paragraph():
    """Fifteen captions ran past 160 characters. What has to be read goes in the line;
    the reasoning goes behind ui.hint()'s toggle."""
    long = []
    for path in sorted((ROOT / "medvault").glob("screen_*.py")) + [ROOT / "medvault" /
                                                                   "bill_render.py"]:
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "caption"
                    and node.args and len(_literal(node.args[0])) > 160):
                long.append(f"{path.name}:{node.lineno}")
    assert not long, f"captions that should be a hint with a Why: {long}"


def test_a_hint_hides_only_the_reasoning():
    html = ui.hint("The line that matters.", "The reasoning.")
    assert html.index("The line that matters.") < html.index("<details>")
    assert "<summary>Why?</summary>" in html
    assert "<details>" not in ui.hint("Just a line.")


# ---- contrast ---------------------------------------------------------------------------

def _token(name):
    return re.search(rf"--{name}:(#[0-9A-Fa-f]{{6}})", ui.CSS).group(1)


def _ratio(a, b):
    def lum(h):
        r, g, b_ = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b_)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_every_text_colour_passes_wcag_aa_on_every_background_it_sits_on():
    """--faint was 2.7-3.0:1. Small text needs 4.5:1."""
    backgrounds = [_token(n) for n in ("card", "bg", "accent-soft", "ok-soft", "warn-soft")]
    for text in ("ink", "soft", "faint", "accent"):
        for back in backgrounds:
            assert _ratio(_token(text), back) >= 4.5, (text, back, _ratio(_token(text), back))


def test_a_warning_is_amber_on_both_streamlit_versions():
    """Every alert was painted blue, and Streamlit tints a warning yellow on top - the two
    mixed into a green, so "you have used today's AI reads" read as a success. 1.37 marks
    a warning stNotificationContentWarning, 1.66 stAlertContentWarning."""
    for marker in ("stNotificationContentWarning", "stAlertContentWarning"):
        rule = re.search(rf'\[data-testid="stAlert"\]:has\(\[data-testid="{marker}"\]\)'
                         r'\{([^}]*)\}', ui.CSS)
        assert rule and "var(--warn-soft)" in rule.group(1), marker
    ink = re.search(r'stAlertContentWarning"\]\) \*\{color:(#[0-9A-Fa-f]{6})', ui.CSS)
    assert ink and _ratio(ink.group(1), _token("warn-soft")) >= 4.5


def test_white_text_on_a_gradient_starts_dark_enough():
    """Small white type on #3B8CFF was 3.3:1. Every gradient that carries white text -
    the buttons, your own chat bubble, the avatar - starts at --accent-strong."""
    assert _ratio("#FFFFFF", _token("accent-strong")) >= 4.5
    for rule in ('button[kind="primaryFormSubmit"]{\n  background:linear-gradient(135deg,'
                 'var(--accent-strong)',
                 '.bubble.q{background:linear-gradient(135deg,var(--accent-strong)',
                 'background:linear-gradient(135deg,var(--accent-strong),var(--accent-deep));\n'
                 '  display:flex;align-items:center;justify-content:center;font-weight:800'):
        assert rule in ui.CSS, rule



# ---- from the test pass ------------------------------------------------------------

def test_a_question_of_only_spaces_is_ignored_not_logged_as_a_crash():
    """It was logged with no answer, and drawing that answer raised on every rerun after,
    with "Clear this conversation" below the crash where nobody could reach it."""
    from test_quota import READY, _env, _no_network
    with offline_vault() as (_, alice, _), _env(**READY), _no_network():
        at = _app(alice)
        at.text_input(key="ask_box").input("     ")
        next(b for b in at.button if b.label == "Ask").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert not at.session_state["ask_log"]
        at.run()
        assert not at.exception


def test_the_emergency_card_lists_every_current_medicine():
    """It showed the newest six under "Taking now · 8": insulin and warfarin, the oldest,
    were the two left off the card somebody reads when the patient cannot speak."""
    import db
    with offline_vault() as (con, alice, _):
        db.save_profile(con, alice["id"], {"full_name": "Alice Anderson", "blood_type": "O+",
                                           "allergies": "none", "emergency_name": "Bob"})
        names = [f"Medicine{n}" for n in range(8)]
        for n, name in enumerate(names):
            rid = db.add_record(con, kind="prescription", title=f"Rx {n}",
                                service_date=f"2026-0{n + 1}-01", owner_id=alice["id"])
            db.add_medication(con, rid, {"name": name, "dose": "1 mg"})
        at = _app(alice)
        card = at.tabs[[t.label for t in at.tabs].index("Card")]
        shown = " ".join(m.value for m in card.markdown)
        missing = [n for n in names if f">{n}<" not in shown]
        assert not missing, missing



def test_the_911_answer_puts_the_call_first_and_the_card_contact_one_tap_away():
    """The emergency answer said "call 911" and stopped there. 911 is a tap away now, and
    under it the person on the patient's own card - after 911, never instead of it."""
    import db
    from test_quota import READY, _env, _no_network
    with offline_vault() as (con, alice, _), _env(**READY), _no_network():
        db.save_profile(con, alice["id"], {"full_name": "Alice Anderson",
                                           "emergency_name": "Bob <i>Builder</i>",
                                           "emergency_relation": "brother",
                                           "emergency_phone": "+1 617 555 0148"})
        at = _app(alice)
        at.text_input(key="ask_box").input("my chest is tight and I can't breathe")
        next(b for b in at.button if b.label == "Ask").click().run()
        assert not at.exception, [e.value for e in at.exception]
        reply = next(m.value for m in at.markdown if "href='tel:911'" in m.value)
        assert "href='tel:+16175550148'" in reply
        assert reply.index("href='tel:911'") < reply.index("href='tel:+16175550148'")
        assert "Bob &lt;i&gt;Builder&lt;/i&gt;" in reply


def test_the_card_number_for_the_emergency_contact_is_tap_to_call():
    """It was plain text: on the screen you hand to somebody when you cannot speak, the
    number had to be read off and typed in. A number with words in it stays unlinked."""
    import db
    with offline_vault() as (con, alice, _):
        db.save_profile(con, alice["id"], {"full_name": "Alice Anderson", "blood_type": "O+",
                                           "allergies": "none", "emergency_name": "Bob",
                                           "emergency_phone": "+1 617 555 0148"})
        at = _app(alice)
        card = at.tabs[[t.label for t in at.tabs].index("Card")]
        assert "<a href='tel:+16175550148'>+1 617 555 0148</a>" in " ".join(
            m.value for m in card.markdown)
        db.save_profile(con, alice["id"], {"emergency_phone": "617 555 0148 ext 5"})
        at = _app(alice)
        card = at.tabs[[t.label for t in at.tabs].index("Card")]
        block = next(m.value for m in card.markdown if "617 555 0148 ext 5" in m.value)
        assert "tel:" not in block


def test_every_reply_that_says_call_911_puts_the_card_contact_after_it():
    """The "AI unavailable" and "Could not answer" replies carry the 911 line too, and a
    dose question's fixed reply ends with one - deleting the contact from either of the
    first two failed nothing."""
    from unittest import mock
    import screen_ask
    person = {"name": "Bob", "relation": "", "phone": "+1 617 555 0148", "dial": "+16175550148"}
    replies = ({"kind": "capped"}, {"kind": "error", "error": "timed out"},
               {"kind": "for_prescriber", "answer": "Ask your prescriber; if you feel unwell "
                "right now, call 911.", "records_used": []})
    for reply in replies:
        drawn = []
        with mock.patch.object(screen_ask.st, "markdown", lambda body, **_: drawn.append(body)), \
             mock.patch.object(screen_ask.st, "caption", lambda *a, **k: None):
            screen_ask._render_turn({"q": "is this bad?", "a": reply}, person)
        html = " ".join(drawn)
        assert "href='tel:+16175550148'" in html, reply["kind"]
        assert html.index("href='tel:911'") < html.index("href='tel:+16175550148'"), reply["kind"]

if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
