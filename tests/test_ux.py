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


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
