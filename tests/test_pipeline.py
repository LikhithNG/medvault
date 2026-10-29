#!/usr/bin/env python3
"""The bill pipeline runs without a screen, reports itself as events, and traces itself.

It used to exist only inside the Bill screen, between the calls that drew the relay, so
the hand-off from Checker to Advocate could not be run - or tested - without rendering a
Streamlit page. These run it as a plain function.
"""
import ast
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import checker   # noqa: E402
import db        # noqa: E402
import paste     # noqa: E402
import pipeline  # noqa: E402
import rights    # noqa: E402

LINES = paste.lines("2026-03-14  70450  CT HEAD/BRAIN W/O CONTRAST  1  3,076.10\n"
                    "2026-03-14  72148  MRI LUMBAR WITHOUT  1  9,374.04")
TABLE = checker.load_reference()
CTX = rights.context(coverage=rights.UNKNOWN, emergency=None, nonprofit_hospital=None,
                     in_network_facility=None, gfe_amount=None)


def _run(hospital, trace=None):
    events = []
    out = pipeline.check_lines(LINES, hospital=hospital, ctx=CTX, records=[],
                               patient_name="Test Patient", price_table=TABLE,
                               on_step=events.append, trace=trace)
    return out, events


def test_it_imports_nothing_that_draws():
    tree = ast.parse((ROOT / "medvault" / "pipeline.py").read_text())
    names = {a.name.split(".")[0] for n in ast.walk(tree)
             if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom) and n.module}
    assert not names & {"streamlit", "agentsui", "ui", "bill_render", "screen_bill"}, names


def test_without_a_hospital_it_prices_against_medicare_and_writes_no_letter():
    out, events = _run(None)
    assert out["priced"] is None and out["letter"] is None
    assert [(e["agent"], e["state"]) for e in events] == [
        ("Checker", "work"), ("Checker", "done"), ("Advocate", "skip")]


def test_a_flagged_bill_is_handed_to_the_advocate():
    out, events = _run("Doylestown Hospital")
    assert out["flagged"] >= 1 and out["letter"]
    assert [(e["agent"], e["state"]) for e in events] == [
        ("Checker", "work"), ("Checker", "done"), ("Advocate", "work"), ("Advocate", "done")]
    done = [e for e in events if e["state"] == "done"]
    assert all(e["seconds"] >= 0 for e in done)


def test_each_agent_run_is_traced():
    con = db.connect(str(pathlib.Path(tempfile.mkdtemp()) / "t.db"))
    _run("Doylestown Hospital", trace=con)
    agents_seen = [r["agent"] for r in con.execute("SELECT agent FROM agent_runs ORDER BY id")]
    assert agents_seen == ["Checker", "Advocate"]



def _check(text, hospital):
    return pipeline.check_lines(paste.lines(text), hospital=hospital, ctx=CTX, records=[],
                                patient_name="Test Patient", price_table=TABLE)


TWICE = ("2026-03-14  70450  CT HEAD/BRAIN W/O CONTRAST  1  3,076.10\n"
         "2026-03-14  70450  CT HEAD/BRAIN W/O CONTRAST  1  3,076.10")


def test_without_a_hospital_a_repeated_code_is_still_found():
    out = _check(TWICE, None)
    assert [f["rule"] for f in out["face"]].count("duplicate") == 1


def test_with_a_hospital_a_repeat_is_reported_once_not_twice():
    """The hospital section reports it, with the price beside it; the bill's-own-face
    section does not say it again."""
    out = _check(TWICE, "Doylestown Hospital")
    assert sum(l["verdict"] == "DUPLICATE" for l in out["priced"]["lines"]) == 1
    assert not [f for f in out["face"] if f["rule"] == "duplicate"]


def test_the_checker_is_told_each_lines_date():
    out = _check("2026-03-14  70450  CT HEAD/BRAIN W/O CONTRAST  1  3,076.10\n"
                 "2026-03-15  70450  CT HEAD/BRAIN W/O CONTRAST  1  3,076.10",
                 "Doylestown Hospital")
    assert "DUPLICATE" not in [l["verdict"] for l in out["priced"]["lines"]]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
