#!/usr/bin/env python3
"""The Bill screen, driven through the real app with Streamlit's AppTest.

The screen used to keep its findings for exactly one run: asking a question underneath
them, or downloading the letter, wiped the lot. Keeping them introduced the opposite
danger - findings that outlive what they were worked out from - and a review caught two
cases of it before they shipped: a record filed after the check left "nothing behind
this line" (and a letter saying so) on screen, and a second person signing in on the
same phone could be shown the first person's results. These run the app to prove all
three stay fixed.

Everything here runs against a throwaway SQLite file. The remote database is switched off
before the app is touched and the module-level default path is pointed at the temp file,
because another test may already have imported db with the real vault.db as its default.
"""
import contextlib
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

BILL = ("2026-03-14  70450  CT HEAD/BRAIN WO CONTRAST   1   3,100.00\n"
        "2026-03-14  71046  XRAY CHEST 2-VIEWS          1     299.00")
OFFLINE = {"TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": "", "GEMINI_API_KEY": ""}


@contextlib.contextmanager
def offline_vault():
    """A temp vault with two patients, and no way for the app to reach anything live."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "bill.db"
        # MEDVAULT_DB as well as db.DEFAULT_PATH, and set before db is imported. The app
        # drops and reloads its modules when it sees them as stale (freshness.py), and a
        # reloaded db reads the variable, not the attribute patched below - so without it
        # a reload would point the app at the real vault.db.
        wanted = {**OFFLINE, "MEDVAULT_DB": str(path)}
        saved = {k: os.environ.get(k) for k in wanted}
        # The app may reload the medvault modules (freshness.py). Put back the ones every
        # other test file imported, so no test is left holding a module the rest of the
        # process has replaced.
        modules = {n: m for n, m in sys.modules.items()
                   if (getattr(m, "__file__", None) or "").startswith(str(ROOT / "medvault"))}
        stamps = dict(getattr(sys, "_medvault_code_stamps", {}) or {})
        os.environ.update(wanted)
        import accounts
        import db
        import store
        assert not store.configured(), "the remote database is still switched on"
        old_default = db.DEFAULT_PATH
        db.DEFAULT_PATH = path
        con = db.connect(str(path))
        try:
            alice, _ = accounts.create(con, email="alice@example.test",
                                       password="password1", role="patient",
                                       display_name="Alice Anderson")
            bob, _ = accounts.create(con, email="bob@example.test", password="password1",
                                     role="patient", display_name="Bob Brown")
            db.add_record(con, kind="imaging", title="Alice's chest X-ray",
                          service_date="2026-03-14", owner_id=alice["id"])
            db.add_record(con, kind="lab", title="Bob's blood panel",
                          service_date="2026-03-20", owner_id=bob["id"])
            yield con, alice, bob
        finally:
            con.close()
            db.DEFAULT_PATH = old_default
            for name in [n for n, m in sys.modules.items()
                         if (getattr(m, "__file__", None) or "").startswith(
                             str(ROOT / "medvault"))]:
                del sys.modules[name]
            sys.modules.update(modules)
            setattr(sys, "_medvault_code_stamps", stamps)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def _app(account):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_resource.clear()        # the app's connection must be to this temp vault
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["account"] = account
    return at.run()


def _check(at, bill=BILL):
    at.radio(key="bill_source").set_value("Paste the lines").run()
    next(t for t in at.text_area if "Paste" in t.label).set_value(bill).run()
    next(b for b in at.button if b.label == "Check this bill").click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _shown(at, text):
    return any(text in m.value for m in at.markdown)


def test_a_checked_bill_survives_the_question_asked_underneath_it():
    with offline_vault() as (_, alice, _):
        at = _check(_app(alice))
        assert _shown(at, "lines have nothing behind them")
        at.text_input(key="ask_q").set_value("what do I do next?").run()
        assert not at.exception, [e.value for e in at.exception]
        assert _shown(at, "lines have nothing behind them"), "the question wiped the bill"


def test_filing_the_missing_record_retires_the_old_finding():
    import db
    with offline_vault() as (con, alice, _):
        at = _check(_app(alice))
        assert at.session_state["bill_run"]["summary"]["unsupported"] == 1
        db.add_record(con, kind="imaging", title="CT head", summary="CT head without contrast",
                      service_date="2026-03-14", owner_id=alice["id"])
        at.run()
        assert not _shown(at, "lines have nothing behind them"), \
            "a finding about the old records was redrawn after a new one was filed"
        assert _shown(at, "Three agents take it from here")


def test_signing_out_leaves_nothing_for_the_next_person():
    with offline_vault() as (_, alice, bob):
        at = _check(_app(alice))
        at.session_state["ask_log"] = [{"q": "Alice's private question", "a": {}}]
        next(b for b in at.button if b.label == "Sign out").click().run()
        for key in ("account", "bill_run", "bill_read", "ask_log"):
            assert key not in at.session_state, f"{key} survived signing out"

        at.session_state["account"] = bob
        at.run()
        at.radio(key="bill_source").set_value("Paste the lines").run()
        next(t for t in at.text_area if "Paste" in t.label).set_value(BILL).run()
        assert not _shown(at, "Alice's chest X-ray"), "Bob was shown Alice's records"
        assert _shown(at, "Three agents take it from here")


def test_a_blank_question_does_not_take_the_screen_down():
    with offline_vault() as (_, alice, _):
        at = _check(_app(alice))
        at.text_input(key="ask_q").set_value("   ").run()
        assert not at.exception, [e.value for e in at.exception]



def test_a_bill_from_an_unlisted_hospital_still_shows_a_repeated_code():
    with offline_vault() as (_, alice, _):
        at = _app(alice)
        at.radio(key="bill_source").set_value("Paste the lines").run()
        box = next(t for t in at.text_area if t.label == "Paste the bill's lines")
        box.input("2026-03-14  70450  CT HEAD  1  3,100.00\n"
                  "2026-03-14  70450  CT HEAD  1  3,100.00").run()
        next(b for b in at.button if b.label == "Check this bill").click().run()
        assert not at.exception, [e.value for e in at.exception]
        shown = " ".join(m.value for m in at.markdown)
        assert "Code 70450 is billed more than once on 2026-03-14" in shown


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
