#!/usr/bin/env python3
"""The agent runtime: budgets, traces, and what a trace may not contain.

The privacy test is the one that matters most. A trace is operational data - timings,
models, kinds of failure - and the day it starts holding questions, answers or record
text it becomes a second copy of the patient's health record that nobody designed as one.
"""
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import agents    # noqa: E402
import db        # noqa: E402
import runtime   # noqa: E402


def _vault():
    tmp = tempfile.mkdtemp()
    return db.connect(str(pathlib.Path(tmp) / "t.db"))


def test_a_span_times_the_run_and_notes_what_the_model_said():
    finished = []
    with runtime.span("Companion", done=finished.append) as s:
        s.saw({"ok": True, "model": "gemini-x", "attempts": 2})
    run = finished[0]
    assert run.agent == "Companion" and run.ok and run.model == "gemini-x"
    assert run.attempts == 2 and run.seconds >= 0 and not run.over_budget


def test_a_failure_is_recorded_and_raised_again_unchanged():
    con, finished = _vault(), []
    try:
        with runtime.span("Checker", trace=con, done=finished.append):
            raise ValueError("boom")
    except ValueError as problem:
        assert str(problem) == "boom"
    else:
        raise AssertionError("the span swallowed the exception")
    assert finished[0].ok is False
    assert con.execute("SELECT ok FROM agent_runs").fetchone()["ok"] == 0


def test_a_model_failure_reported_in_a_result_is_a_failed_run():
    finished = []
    with runtime.span("Reader", done=finished.append) as s:
        s.saw({"ok": False, "error": "HTTP 503: UNAVAILABLE", "model": None})
    assert finished[0].ok is False and finished[0].error_kind == "overloaded"


def test_failures_are_sorted_into_kinds_an_operator_can_act_on():
    cases = {"deadline reached (30s budget)": "timeout",
             "TimeoutError: timed out": "timeout",
             "HTTP 429: RESOURCE_EXHAUSTED": "quota",
             "HTTP 503: model overloaded": "overloaded",
             "malformed JSON from model": "malformed",
             "URLError: <urlopen error [Errno 8]>": "network",
             "GEMINI_API_KEY is not set": "not_configured",
             "something nobody anticipated": "other"}
    for text, kind in cases.items():
        assert runtime.classify(text) == kind, text


def test_the_trace_cannot_hold_anything_about_the_patient():
    con = _vault()
    columns = {r["name"] for r in con.execute("PRAGMA table_info(agent_runs)").fetchall()}
    assert columns == {"id", "agent", "started_at", "seconds", "ok", "model", "attempts",
                       "error_kind", "over_budget"}, columns
    with runtime.span("Companion", trace=con) as s:
        s.saw({"ok": False, "error": "HTTP 400: your question about penicillin was bad"})
    row = dict(con.execute("SELECT * FROM agent_runs").fetchone())
    assert "penicillin" not in repr(row).lower(), "raw provider text reached the trace"


def test_only_the_agents_a_person_starts_are_traced():
    con = _vault()
    for name in ("Scheduler", "Liaison"):
        with runtime.span(name, trace=con):
            pass
    assert con.execute("SELECT COUNT(*) AS n FROM agent_runs").fetchone()["n"] == 0


def test_a_trace_that_cannot_be_written_never_costs_the_answer():
    broken = sqlite3.connect(":memory:")          # no agent_runs table
    with runtime.span("Advocate", trace=broken) as s:
        s.saw({"ok": True})
    # reaching here is the assertion


def test_the_summary_reports_rates_and_percentiles_per_agent():
    con = _vault()
    for seconds, ok in ((1.0, True), (2.0, True), (3.0, False), (40.0, True)):
        runtime.record(con, runtime.Run(agent="Companion", started_at=0, seconds=seconds,
                                        ok=ok, model="m", error_kind=None if ok else "timeout",
                                        over_budget=seconds > 30))
    (row,) = runtime.summary(con)
    assert row["agent"] == "Companion" and row["runs"] == 4
    assert row["ok_rate"] == 0.75 and row["over_budget"] == 1
    assert row["last_failure"] == "timeout" and row["p50"] == 2.5


def test_an_unknown_agent_is_refused():
    try:
        with runtime.span("Oracle"):
            pass
    except KeyError:
        return
    raise AssertionError("ran an agent the registry does not know")


def test_every_agent_has_a_budget_and_says_what_leaves_the_server():
    for agent in agents.AGENTS:
        assert agent["budget_s"] > 0, agent["name"]
        assert isinstance(agent["egress"], tuple), agent["name"]
        assert isinstance(agent["traced"], bool), agent["name"]


def test_an_agent_that_calls_a_model_says_which_provider_gets_what():
    for agent in agents.AGENTS:
        if agent["generative"]:
            assert any("Gemini" in e or "Groq" in e for e in agent["egress"]), agent["name"]


def test_what_the_checker_sends_out_is_codes_and_nothing_else():
    (only,) = agents.BY_NAME["Checker"]["egress"]
    assert "CPT codes only" in only and "nothing about the patient" in only


def test_the_agents_that_send_nothing_out_import_no_network_client():
    for agent in agents.AGENTS:
        if agent["egress"]:
            continue
        source = (ROOT / "medvault" / f"{agent['module']}.py").read_text()
        for client in ("urllib.request", "import gemini", "import groq", "requests"):
            assert client not in source, f"{agent['name']} imports {client}"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
