#!/usr/bin/env python3
"""The records bot: the parts that must not depend on a model.

Nothing here calls one. What is tested is the ring around it — the questions that never
reach it, the checks that run before it, the context it is handed, and the relabelling
applied to what comes back. A fake reader stands in for the model so the plumbing can be
checked without a key, a network, or a different answer every run.
"""
import datetime
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import accounts   # noqa: E402
import ask        # noqa: E402
import db         # noqa: E402

TODAY = datetime.date(2026, 10, 26)


def a_patient(allergies=""):
    con = db.connect(tempfile.mktemp(suffix=".db"))
    acct, _ = accounts.create(con, email="p@example.com", password="12345678",
                              role="patient")
    if allergies:
        db.save_profile(con, acct["id"], {"allergies": allergies})
    return con, acct["id"]


def a_prescription(con, owner, meds, date="2026-03-14", title="Prescription"):
    rid = db.add_record(con, kind="prescription", title=title, service_date=date,
                        owner_id=owner)
    for m in meds:
        db.add_medication(con, rid, m)
    return rid


class FakeReader:
    """Stands in for gemini.generate, returning whatever the test wants to examine."""

    def __init__(self, payload=None, ok=True, error=None):
        self.payload, self.ok, self.error = payload, ok, error
        self.prompt = None

    def generate(self, prompt, schema=None, temperature=0.0):
        self.prompt = prompt
        if not self.ok:
            return {"ok": False, "error": self.error, "model": "fake"}
        return {"ok": True, "json": self.payload, "model": "fake"}


# ---- the questions a model never sees --------------------------------------

def test_an_emergency_is_answered_without_asking_a_model():
    for question in ("I have chest pain right now", "my throat is closing",
                     "I think I took too many of these"):
        result = ask.triage(question)
        assert result and result["kind"] == "emergency"
        assert "911" in result["answer"]


def test_an_ordinary_question_is_not_treated_as_an_emergency():
    assert ask.triage("what is the fluticasone for?") is None
    assert ask.triage("when did I last have a blood test") is None


def test_a_dose_decision_is_relabelled_whatever_the_model_called_it():
    con, owner = a_patient()
    reader = FakeReader({"kind": "from_records", "answer": "Sure, halve it.",
                         "records_used": []})

    out = ask.answer(con, owner, "should i stop taking the amoxicillin?", reader=reader)

    assert out["kind"] == "for_prescriber"


# ---- the checks that run before it -----------------------------------------

def test_a_finished_course_is_worked_out_from_the_prescription_itself():
    med = {"service_date": "2026-03-14", "duration": "7 days"}
    assert ask.course_ended(med, TODAY) == datetime.date(2026, 3, 21)


def test_a_course_still_running_is_not_flagged():
    med = {"service_date": "2026-10-25", "duration": "7 days"}
    assert ask.course_ended(med, TODAY) is None


def test_a_course_with_no_stated_duration_is_unknown_not_overdue():
    assert ask.course_ended({"service_date": "2026-01-01"}, TODAY) is None
    assert ask.course_ended({"service_date": "2026-01-01", "duration": "as needed"},
                            TODAY) is None


def test_an_allergy_is_caught_through_the_drug_family_not_only_the_name():
    """"Allergic to penicillin" plus amoxicillin share no letters. This is the case."""
    hits = ask.allergy_conflicts([{"name": "Amoxicillin-Clavulanate"}],
                                 {"allergies": "Penicillin (rash), shellfish"})

    assert len(hits) == 1
    assert hits[0]["family"] == ["penicillin"]


def test_no_recorded_allergy_produces_no_conflicts():
    assert ask.allergy_conflicts([{"name": "Amoxicillin"}], {}) == []
    assert ask.allergy_conflicts([{"name": "Amoxicillin"}],
                                 {"allergies": "none known"}) == []


def test_the_same_medicine_twice_and_both_current_is_flagged():
    con, owner = a_patient()
    a_prescription(con, owner, [{"name": "Ibuprofen", "reason": "pain"}], "2026-03-01")
    a_prescription(con, owner, [{"name": "ibuprofen", "reason": "pain"}], "2026-04-02")

    titles = [f["title"] for f in ask.brief(con, owner, TODAY)]

    assert any("listed 2 times" in t for t in titles)


def test_a_medicine_with_no_reason_is_raised_as_a_question():
    con, owner = a_patient()
    a_prescription(con, owner, [{"name": "Atorvastatin"}])

    bodies = [f["body"] for f in ask.brief(con, owner, TODAY)]

    assert any("does not say what" in b for b in bodies)


# ---- what the model is handed ----------------------------------------------

def test_the_context_holds_this_patients_records_and_no_one_elses():
    con = db.connect(tempfile.mktemp(suffix=".db"))
    a, _ = accounts.create(con, email="a@example.com", password="12345678", role="patient")
    b, _ = accounts.create(con, email="b@example.com", password="12345678", role="patient")
    db.add_record(con, kind="lab", title="A blood panel", owner_id=a["id"])
    db.add_record(con, kind="imaging", title="B knee MRI", owner_id=b["id"])

    text, sources = ask.context_pack(con, a["id"])

    assert "A blood panel" in text
    assert "B knee MRI" not in text, "one patient's context held another's records"
    assert all(db.get_record(con, i)["owner_id"] == a["id"] for i in sources)


# ---- what comes back from it -----------------------------------------------

def test_an_answer_claiming_the_records_but_citing_none_is_relabelled():
    """A badge that says "from your records" has to be backed by a record."""
    con, owner = a_patient()
    reader = FakeReader({"kind": "from_records", "answer": "You are on three medicines.",
                         "records_used": []})

    out = ask.answer(con, owner, "what am I taking?", reader=reader)

    assert out["kind"] == "general"


def test_a_cited_record_comes_back_with_the_answer():
    con, owner = a_patient()
    rid = a_prescription(con, owner, [{"name": "Ibuprofen"}], title="Sinusitis script")
    reader = FakeReader({"kind": "from_records", "answer": "For the sinus infection.",
                         "records_used": [rid]})

    out = ask.answer(con, owner, "why am I on ibuprofen?", reader=reader)

    assert out["kind"] == "from_records"
    assert out["sources"][rid]["title"] == "Sinusitis script"


def test_a_citation_of_a_record_that_is_not_theirs_is_dropped():
    con = db.connect(tempfile.mktemp(suffix=".db"))
    a, _ = accounts.create(con, email="a@example.com", password="12345678", role="patient")
    b, _ = accounts.create(con, email="b@example.com", password="12345678", role="patient")
    theirs = db.add_record(con, kind="lab", title="B's panel", owner_id=b["id"])
    reader = FakeReader({"kind": "from_records", "answer": "It says so here.",
                         "records_used": [theirs]})

    out = ask.answer(con, a["id"], "what did the lab say?", reader=reader)

    assert out["sources"] == {}
    assert out["kind"] == "general"


def test_a_reader_failure_is_reported_rather_than_papered_over():
    con, owner = a_patient()
    reader = FakeReader(ok=False, error="HTTP 503")

    out = ask.answer(con, owner, "what is this for?", reader=reader)

    assert out["kind"] == "error" and out["answer"] is None and "503" in out["error"]


def test_the_prompt_carries_the_question_and_the_records():
    con, owner = a_patient()
    a_prescription(con, owner, [{"name": "Fluticasone"}], title="Nasal spray script")
    reader = FakeReader({"kind": "general", "answer": "ok", "records_used": []})

    ask.answer(con, owner, "what is fluticasone?", reader=reader)

    assert "what is fluticasone?" in reader.prompt
    assert "Nasal spray script" in reader.prompt
    assert "Never tell them to start, stop, change" in reader.prompt


def test_a_past_stroke_in_a_records_question_is_not_an_emergency():
    """The ambiguous words need a present-tense marker, or the vault cannot be asked
    about the thing that put half these records in it."""
    assert ask.triage("what was I given after my stroke in 2019?") is None
    assert ask.triage("which medicines am I on for seizures?") is None
    assert ask.triage("I think I'm having a stroke")["kind"] == "emergency"


def test_the_emergency_answer_is_html_not_markdown():
    """It is rendered inside a raw HTML bubble, where ** is just two asterisks."""
    answer = ask.triage("I have chest pain")["answer"]
    assert "**" not in answer and "<b>" in answer
