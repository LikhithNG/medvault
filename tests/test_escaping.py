#!/usr/bin/env python3
"""Nothing typed, read off a page, or set by another account is drawn as markup.

Almost every screen builds its cards as HTML strings and hands them to st.markdown with
unsafe_allow_html. A test pass planting markup in every field found the emergency card,
the medicines, the schedule and the bill findings printing their values raw: an allergy
note reading "</div>" broke the screen, a medicine name read off a scanned page went in as
markup, and a clinician's display name could put markup on a patient's screen.

These plant one payload in every source a screen draws from - the card, a record and its
medicines, a clinician's account and registry details, a patient's name, a pasted bill -
and look at every screen, as a patient and as a clinician, for the payload unescaped.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tests"))

from test_bill_screen import _app, offline_vault   # noqa: E402

X = "<img src=x onerror=alert(1)>"
PAYLOAD = f"{X}</div></div>"


def _raw(at):
    """Every markdown block on the page that carries the payload as live markup."""
    return [m.value[:120] for m in at.markdown if X in (m.value or "")]


def _plant(con, alice, bob):
    import accounts
    import careteam
    import db
    db.save_profile(con, alice["id"], {
        "full_name": PAYLOAD, "date_of_birth": PAYLOAD, "allergies": PAYLOAD + "\n\nnuts",
        "conditions": PAYLOAD, "emergency_name": PAYLOAD, "emergency_relation": PAYLOAD,
        "emergency_phone": PAYLOAD, "gp_name": PAYLOAD, "gp_phone": PAYLOAD,
        "insurer": PAYLOAD, "member_id": PAYLOAD})
    rx = db.add_record(con, kind="prescription", title=PAYLOAD, service_date="2026-10-01",
                       provider=PAYLOAD, summary=PAYLOAD + " Follow up in 2 weeks.",
                       owner_id=alice["id"])
    # A date is free text on the Add screen and in an import: a clinician's review
    # screen printed it raw.
    db.add_record(con, kind="lab", title="Panel", service_date=PAYLOAD,
                  summary="line one\n\n![x](https://evil.example/p.png)", owner_id=alice["id"])
    for name in (PAYLOAD, "Amoxicillin"):
        db.add_medication(con, rx, {"name": name, "dose": PAYLOAD,
                                    "frequency": "twice daily", "duration": "7 days",
                                    "reason": PAYLOAD})
    db.add_medication(con, rx, {"name": "Amoxicillin", "dose": "500 mg",
                                "frequency": "three times daily"})
    doc, _ = accounts.create(con, email="dr@example.test", password="password1",
                             role="clinician", display_name=PAYLOAD,
                             npi_record={"npi": "0000000000", "name": PAYLOAD,
                                         "specialty": PAYLOAD, "license": PAYLOAD,
                                         "license_state": "MA"})
    careteam.add(con, alice["id"], "dr@example.test")
    return doc


def test_nothing_on_a_patients_screens_is_drawn_as_markup():
    with offline_vault() as (con, alice, bob):
        _plant(con, alice, bob)
        at = _app(alice)
        assert not at.exception, [e.value for e in at.exception]
        assert not _raw(at), _raw(at)


def test_nothing_on_a_clinicians_screens_is_drawn_as_markup():
    import accounts
    with offline_vault() as (con, alice, bob):
        doc = _plant(con, alice, bob)
        con.execute("UPDATE accounts SET display_name = ? WHERE id = ?", (PAYLOAD, alice["id"]))
        con.commit()
        at = _app(accounts.get(con, doc["id"]))
        assert not at.exception, [e.value for e in at.exception]
        assert not _raw(at), _raw(at)


def test_a_pasted_bill_is_not_drawn_as_markup_in_its_findings():
    with offline_vault() as (con, alice, bob):
        _plant(con, alice, bob)
        at = _app(alice)
        at.radio(key="bill_source").set_value("Paste the lines").run()
        box = next(t for t in at.text_area if t.label == "Paste the bill's lines")
        box.input(f"2026-03-14  70450  {PAYLOAD}  1  3,100.00\n"
                  f"2026-03-14  70450  {PAYLOAD}  1  3,100.00").run()
        next(b for b in at.button if b.label == "Check this bill").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert not _raw(at), _raw(at)


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
