#!/usr/bin/env python3
"""How many AI reads an account may start in a day, and how many the whole site may.

The free Gemini tier allows about 20 requests a day per model. Six models make roughly 120
a day for the entire site, shared by every account, and nothing stopped one account from
spending all of them: a room of people opening the link during a presentation could switch
the AI off for everybody, the presenter included. These hold the limit in place, and hold
the two things a limit must never do - refuse an answer that never needed a model (an
emergency, a dose decision), or keep anything about the patient.

The app tests run the real app against a throwaway vault, with the network switched off.
"""
import contextlib
import datetime
import os
import pathlib
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tests"))

import accounts                                    # noqa: E402
import ask                                         # noqa: E402
import db                                          # noqa: E402
import quota                                       # noqa: E402
from test_bill_screen import _app, offline_vault  # noqa: E402

LIMITS = {"MEDVAULT_DAILY_PER_ACCOUNT": "3", "MEDVAULT_DAILY_SITE": "5",
          "MEDVAULT_UNCAPPED": ""}


@contextlib.contextmanager
def _env(**values):
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _vault():
    con = db.connect(str(pathlib.Path(tempfile.mkdtemp()) / "quota.db"))

    def person(email):
        made, _ = accounts.create(con, email=email, password="password1", role="patient",
                                  display_name=email.split("@")[0])
        return made
    return con, person


def _spend(con, account, times):
    for _ in range(times):
        quota.spend(con, account)


# ---- the allowance ------------------------------------------------------------------

def test_a_new_account_starts_with_its_full_allowance():
    con, person = _vault()
    with _env(**LIMITS):
        a = quota.allowance(con, person("alice@example.test"))
    assert (a.used, a.limit, a.left, a.refused) == (0, 3, 3, None)


def test_an_account_is_refused_once_it_has_used_its_allowance():
    con, person = _vault()
    alice = person("alice@example.test")
    with _env(**LIMITS):
        _spend(con, alice, 2)
        assert quota.allowance(con, alice).refused is None
        quota.spend(con, alice)
        a = quota.allowance(con, alice)
    assert a.refused == "account" and a.left == 0


def test_one_accounts_use_does_not_spend_anothers():
    con, person = _vault()
    alice, bob = person("alice@example.test"), person("bob@example.test")
    with _env(**LIMITS):
        _spend(con, alice, 3)
        a = quota.allowance(con, bob)
    assert a.used == 0 and a.refused is None


def test_the_site_ceiling_refuses_everyone_once_it_is_reached():
    con, person = _vault()
    alice, bob, carol = (person(f"{n}@example.test") for n in ("alice", "bob", "carol"))
    with _env(**LIMITS):
        _spend(con, alice, 3)
        _spend(con, bob, 2)
        a = quota.allowance(con, carol)
    assert a.used == 0 and a.refused == "site"


def test_a_listed_account_is_never_refused_but_its_use_still_counts():
    """The presenter's account. Listed by email, matched without regard to case or spaces."""
    con, person = _vault()
    presenter, carol = person("presenter@example.test"), person("carol@example.test")
    with _env(**{**LIMITS, "MEDVAULT_UNCAPPED": " Presenter@Example.test , x@y.z"}):
        _spend(con, presenter, 6)
        mine, theirs = quota.allowance(con, presenter), quota.allowance(con, carol)
    assert mine.refused is None and mine.limit is None and mine.left is None
    assert theirs.refused == "site"


def test_yesterdays_use_does_not_count_today():
    con, person = _vault()
    alice = person("alice@example.test")
    yesterday = (datetime.date.fromisoformat(quota.today())
                 - datetime.timedelta(days=1)).isoformat()
    for _ in range(3):
        db.count_ai_use(con, alice["id"], yesterday)
    with _env(**LIMITS):
        assert quota.allowance(con, alice).used == 0


def test_old_days_are_cleared_as_new_ones_are_counted():
    con, person = _vault()
    alice = person("alice@example.test")
    db.count_ai_use(con, alice["id"], "2026-01-01")
    with _env(**LIMITS):
        quota.spend(con, alice)
    days = {r["day"] for r in con.execute("SELECT day FROM ai_use").fetchall()}
    assert days == {quota.today()}


def test_the_counter_holds_who_when_and_how_many_and_nothing_else():
    con, _ = _vault()
    columns = {r["name"] for r in con.execute("PRAGMA table_info(ai_use)").fetchall()}
    assert columns == {"account_id", "day", "n"}, columns


def test_the_limits_come_from_the_environment_and_survive_a_typo():
    """A mistyped secret must not take every screen down with a ValueError."""
    con, person = _vault()
    alice = person("alice@example.test")
    with _env(MEDVAULT_DAILY_PER_ACCOUNT="7", MEDVAULT_DAILY_SITE="lots",
              MEDVAULT_UNCAPPED=""):
        a = quota.allowance(con, alice)
    assert a.limit == 7 and a.site_limit == quota.SITE
    for typo in ("-3", "", "  ", "2.5", "ten"):
        with _env(MEDVAULT_DAILY_PER_ACCOUNT=typo, MEDVAULT_DAILY_SITE="50",
                  MEDVAULT_UNCAPPED=""):
            assert quota.allowance(con, alice).limit == quota.PER_ACCOUNT, typo


# ---- taking a read ----------------------------------------------------------------------

def test_a_read_is_taken_only_while_there_is_room_for_it():
    con, person = _vault()
    alice = person("alice@example.test")
    with _env(**LIMITS):
        taken = [quota.take(con, alice) for _ in range(4)]
        used = quota.allowance(con, alice).used
    assert taken == [True, True, True, False] and used == 3


def test_two_tabs_that_both_saw_room_for_the_last_read_get_one_between_them():
    """Both tabs drew the button with one read left. The check and the count are one
    statement, so the second press finds no room - it does not run a read past the limit."""
    con, person = _vault()
    alice = person("alice@example.test")
    with _env(**LIMITS):
        _spend(con, alice, 2)
        tab_one, tab_two = quota.allowance(con, alice), quota.allowance(con, alice)
        assert tab_one.refused is None and tab_two.refused is None
        assert [quota.take(con, alice), quota.take(con, alice)] == [True, False]


def test_the_site_ceiling_is_held_by_the_same_statement():
    con, person = _vault()
    alice, bob = person("alice@example.test"), person("bob@example.test")
    with _env(**LIMITS):
        _spend(con, alice, 3)
        assert [quota.take(con, bob) for _ in range(3)] == [True, True, False]


def test_a_listed_account_always_gets_its_read():
    con, person = _vault()
    presenter = person("presenter@example.test")
    with _env(**{**LIMITS, "MEDVAULT_UNCAPPED": "presenter@example.test"}):
        assert all(quota.take(con, presenter) for _ in range(7))
        assert quota.allowance(con, presenter).used == 7


def test_a_database_that_does_not_report_a_row_count_does_not_lock_everyone_out():
    """store.Cursor reports -1 when the remote database leaves the count out."""
    class Quiet:
        rowcount = -1

    class Con:
        def execute(self, *args):
            return Quiet()

        def commit(self):
            pass
    assert db.take_ai_use(Con(), 1, quota.today(), 3, 5) is True


def test_a_counter_that_cannot_be_written_never_costs_the_read():
    """Bookkeeping that fails must not cost the patient the answer - runtime.record's rule."""
    broken = sqlite3.connect(":memory:")          # no ai_use table
    with _env(**LIMITS):
        assert quota.take(broken, {"id": 1, "email": "alice@example.test"}) is True


# ---- what the screen is told --------------------------------------------------------

def test_the_screen_is_told_only_when_it_matters():
    plenty = quota.Allowance(used=2, limit=10, site_used=2, site_limit=50)
    low = quota.Allowance(used=8, limit=10, site_used=8, site_limit=50)
    last = quota.Allowance(used=9, limit=10, site_used=9, site_limit=50)
    spent = quota.Allowance(used=10, limit=10, site_used=10, site_limit=50)
    site = quota.Allowance(used=0, limit=10, site_used=50, site_limit=50)
    listed = quota.Allowance(used=40, limit=None, site_used=50, site_limit=50)
    assert quota.note(plenty) is None and quota.note(listed) is None
    assert "2 AI reads left" in quota.note(low)
    assert "1 AI read left" in quota.note(last)
    assert "today's 10 AI reads" in quota.note(spent)
    one = quota.note(quota.Allowance(used=1, limit=1, site_used=1, site_limit=50))
    assert "today's 1 AI read " in one
    assert "everyone" in quota.note(site)
    assert "midnight Pacific" in quota.note(spent) and "midnight Pacific" in quota.note(site)


def test_a_limit_of_nought_reads_as_switched_off_not_as_used_up():
    """Setting MEDVAULT_DAILY_PER_ACCOUNT to 0 keeps every read for the listed accounts -
    the way to hold the whole quota for a presenter. "You have used today's 0" is wrong."""
    off = quota.note(quota.Allowance(used=0, limit=0, site_used=0, site_limit=50))
    assert "switched off" in off and "used today's" not in off and "midnight" not in off


# ---- the Companion past the limit ---------------------------------------------------

class _NoModel:
    def generate(self, *args, **kwargs):
        raise AssertionError("the model was called past the limit")


def _refuse():
    return False


def _never_asked():
    raise AssertionError("the allowance was consulted for an answer that needs no model")


def test_past_the_limit_an_emergency_and_a_dose_question_are_answered_and_not_counted():
    """The allowance is never even asked about them, so they cannot be refused or counted."""
    con, person = _vault()
    alice = person("alice@example.test")
    urgent = ask.answer(con, alice["id"], "I have chest pain right now", reader=_NoModel(),
                        permit=_never_asked)
    dose = ask.answer(con, alice["id"], "Should I stop taking the amoxicillin?",
                      reader=_NoModel(), permit=_never_asked)
    assert urgent["kind"] == "emergency" and dose["kind"] == "for_prescriber"


def test_past_the_limit_a_records_question_is_not_sent_to_a_model():
    con, person = _vault()
    alice = person("alice@example.test")
    out = ask.answer(con, alice["id"], "What did my chest X-ray show?", reader=_NoModel(),
                     permit=_refuse)
    assert out["kind"] == "capped" and out["model"] is None


def test_the_allowance_is_asked_once_just_before_the_model_is():
    con, person = _vault()
    alice = person("alice@example.test")
    asked = []

    class Reader:
        def generate(self, *args, **kwargs):
            assert asked == [1], "the model was called before the allowance was taken"
            return {"ok": True, "model": "m", "json": {"kind": "general", "answer": "Hi.",
                                                       "records_used": []}}
    ask.answer(con, alice["id"], "What did my chest X-ray show?", reader=Reader(),
               permit=lambda: asked.append(1) or True)
    assert asked == [1]


# ---- the screens ----------------------------------------------------------------------

READY = {"GEMINI_API_KEY": "test-key-not-real", "MEDVAULT_DAILY_PER_ACCOUNT": "2",
         "MEDVAULT_DAILY_SITE": "50", "MEDVAULT_UNCAPPED": ""}


@contextlib.contextmanager
def _no_network():
    """Whatever the app tries to reach fails at once, as if the machine were offline."""
    def offline(*args, **kwargs):
        raise urllib.error.URLError("no network in tests")
    saved = urllib.request.urlopen
    urllib.request.urlopen = offline
    try:
        yield
    finally:
        urllib.request.urlopen = saved


class _Upload:
    """What st.file_uploader hands back, near enough for the screens."""
    name, type = "scan.png", "image/png"

    def getvalue(self):
        return b"not really a png"


@contextlib.contextmanager
def _uploaded():
    """Every file box on the page holds a file. AppTest cannot upload one itself."""
    import streamlit as st
    saved = st.file_uploader
    st.file_uploader = lambda *args, **kwargs: _Upload()
    try:
        yield
    finally:
        st.file_uploader = saved


@contextlib.contextmanager
def _uploaded_until_rekeyed():
    """Like _uploaded, but as Streamlit behaves: a box given a new key is a new, empty box.
    Yields every box drawn, in order, as (label, whether it held a file)."""
    import streamlit as st
    saved, first_key, drawn = st.file_uploader, {}, []

    def box(label, *args, **kwargs):
        first_key.setdefault(label, kwargs.get("key"))
        held = kwargs.get("key") == first_key[label]
        drawn.append((label, held))
        return _Upload() if held else None
    st.file_uploader = box
    try:
        yield drawn
    finally:
        st.file_uploader = saved


@contextlib.contextmanager
def _stand_in(module_name, attr, fn):
    """Replace one function on the module the app is using now, and put it back after.

    Imported here rather than at the top: the app's first run may have reloaded its
    modules (freshness.py), and the stand-in must be on the one it will call.
    """
    import importlib
    module = importlib.import_module(module_name)
    saved = getattr(module, attr)
    setattr(module, attr, fn)
    try:
        yield
    finally:
        setattr(module, attr, saved)


def _ask(at, question):
    at.text_input(key="ask_box").input(question)
    next(b for b in at.button if b.label == "Ask").click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_the_ask_screen_says_the_limit_instead_of_calling_the_model():
    with offline_vault() as (con, alice, _), _env(**READY), _no_network():
        _spend(con, alice, 2)
        at = _ask(_app(alice), "What did my chest X-ray show?")
        shown = " ".join(m.value for m in at.markdown)
        assert "AI unavailable" in shown
        assert any("today's 2 AI reads" in w.value for w in at.warning)
        # Whatever the question was: the triage only knows the phrasings it knows, and a
        # person in an emergency who words it differently must not read only "unavailable".
        assert "call 911" in shown


def test_an_answer_from_the_model_is_counted_and_an_emergency_is_not():
    with offline_vault() as (con, alice, _), _env(**READY), _no_network():
        at = _app(alice)
        answered = {"ok": True, "model": "stand-in",
                    "json": {"kind": "general", "answer": "No acute findings.",
                             "records_used": []}}
        with _stand_in("gemini", "generate", lambda *a, **k: answered):
            _ask(at, "I have chest pain right now")
            assert quota.allowance(con, alice).used == 0
            _ask(at, "What did my chest X-ray show?")
        assert quota.allowance(con, alice).used == 1


def test_the_add_screen_does_not_offer_a_read_past_the_limit():
    with offline_vault() as (con, alice, _), _env(**READY), _no_network(), _uploaded():
        _spend(con, alice, 2)
        at = _app(alice)
        assert not at.exception, [e.value for e in at.exception]
        assert "Read this document" not in [b.label for b in at.button]
        assert any("today's 2 AI reads" in w.value for w in at.warning)


def test_a_document_read_is_counted():
    with offline_vault() as (con, alice, _), _env(**READY), _no_network(), _uploaded():
        at = _app(alice)
        read = ({"kind": "lab", "title": "Blood panel", "service_date": None,
                 "provider": None, "summary": None, "medications": []},
                {"ok": True, "model": "stand-in"})
        with _stand_in("extract", "read_document", lambda **k: read):
            _click(at, "Read this document")
        assert quota.allowance(con, alice).used == 1


def test_a_failed_document_read_is_still_counted():
    """The request went out, so it came out of the provider's quota."""
    with offline_vault() as (con, alice, _), _env(**READY), _no_network(), _uploaded():
        at = _app(alice)
        with _stand_in("extract", "read_document",
                       lambda **k: (None, {"ok": False, "error": "HTTP 503: UNAVAILABLE"})):
            _click(at, "Read this document")
        assert any("could not be read" in e.value for e in at.error)
        assert quota.allowance(con, alice).used == 1


def test_a_document_read_with_the_last_allowance_can_still_be_filed():
    with offline_vault() as (con, alice, _), _env(**READY), _no_network(), _uploaded():
        _spend(con, alice, 1)
        at = _app(alice)
        read = ({"kind": "lab", "title": "Blood panel", "service_date": None,
                 "provider": None, "summary": None, "medications": []},
                {"ok": True, "model": "stand-in"})
        with _stand_in("extract", "read_document", lambda **k: read):
            _click(at, "Read this document")
        labels = [b.label for b in at.button]
        # No button left that would be dropped on the next run, and the count says why.
        assert "Read this document" not in labels and "File this record" in labels
        assert any("today's 2 AI reads" in w.value for w in at.warning)
        _click(at, "File this record")
        titles = [r["title"] for r in db.list_records(con, owner_id=alice["id"])]
        assert "Blood panel" in titles


def test_a_filed_document_leaves_the_upload_box_empty():
    """Filing used to leave the photo in the box under a live "Read this document" - one
    more click read it again, spending a read, and offered to file it a second time."""
    with offline_vault() as (con, alice, _), _env(**READY), _no_network(), \
            _uploaded_until_rekeyed() as drawn:
        at = _app(alice)
        read = ({"kind": "lab", "title": "Blood panel", "service_date": None,
                 "provider": None, "summary": None, "medications": []},
                {"ok": True, "model": "stand-in"})
        with _stand_in("extract", "read_document", lambda **k: read):
            _click(at, "Read this document")
        _click(at, "File this record")
        # What the app drew, not at.button: AppTest on 1.37 keeps the elements of the run
        # that st.rerun() cut short, so "Read this document" lingers there either way.
        boxes = [held for label, held in drawn if label == "Photo or PDF"]
        assert boxes[0] and not boxes[-1], "the filed document is still in the box"
        assert quota.allowance(con, alice).used == 1


def test_a_bill_already_read_is_neither_refused_nor_counted_again():
    """Changing the hospital on a bill read before the limit costs nothing."""
    with offline_vault() as (con, alice, _), _env(**READY), _no_network(), _uploaded():
        at = _app(alice)
        read = ([{"code": "", "service_date": None, "description": "Visit", "units": 1,
                  "charged": 10.0}], {"ok": True, "model": "stand-in"})
        with _stand_in("extract", "read_bill_verified", lambda **k: read):
            _click(at, "Check this bill")
        _spend(con, alice, 1)                     # now at the limit
        _click(at, "Check this bill")
        errors = " ".join(e.value for e in at.error)
        assert "AI reads" not in errors and "No billing codes found" in errors
        assert quota.allowance(con, alice).used == 2


def test_a_bill_photo_is_not_read_past_the_limit_and_pasting_is_offered():
    with offline_vault() as (con, alice, _), _env(**READY), _no_network(), _uploaded():
        _spend(con, alice, 2)
        at = _click(_app(alice), "Check this bill")
        errors = " ".join(e.value for e in at.error)
        assert "AI reads" in errors and "Paste the lines" in errors


def test_a_bill_read_is_counted_even_when_it_finds_nothing_to_check():
    """The model was asked, so the read is spent, whatever came back."""
    with offline_vault() as (con, alice, _), _env(**READY), _no_network(), _uploaded():
        at = _app(alice)
        # A line the way the Reader returns one from a summary statement: no code.
        read = ([{"code": "", "service_date": None, "description": "Visit", "units": 1,
                  "charged": 10.0}], {"ok": True, "model": "stand-in"})
        with _stand_in("extract", "read_bill_verified", lambda **k: read):
            _click(at, "Check this bill")
        assert quota.allowance(con, alice).used == 1



def test_when_the_model_fails_the_reply_still_leads_with_911():
    """With the model the second net for emergencies the patterns miss, a model that does
    not answer must not leave a patient in an emergency with only "could not answer"."""
    with offline_vault() as (con, alice, _), _env(**READY), _no_network():
        at = _app(alice)
        failed = {"ok": False, "model": None, "error": "HTTP 503: UNAVAILABLE"}
        with _stand_in("gemini", "generate", lambda *a, **k: failed):
            _ask(at, "she's slumped and mumbling and I can't get her to answer me")
        shown = " ".join(m.value for m in at.markdown)
        assert "Could not answer" in shown and "call 911" in shown


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
