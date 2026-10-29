#!/usr/bin/env python3
"""The model clients keep to the time they are given.

A Companion answer once took 46 seconds. The pool had a deadline, but it only stopped the
loop from starting another model: each request kept its own 45-second timeout and four
retries with backoff, so one slow provider could hold a patient for minutes. These stub
the network and the clock's waiting, and check that no request is ever given longer than
what is left of the caller's budget, and that a spent budget ends the call honestly.
"""
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import extract   # noqa: E402
import gemini    # noqa: E402
import groq      # noqa: E402


class _Clock:
    """Stands in for the network: every request times out, and takes the time it was
    allowed. Sleeping advances the clock instead of waiting."""

    def __init__(self):
        self.now = 1000.0
        self.timeouts = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def post(self, *args, timeout=None):
        self.timeouts.append(timeout)
        self.now += timeout or 45
        raise TimeoutError("timed out")


def _key(name):
    """A stand-in key for the length of one test, removed again after: the network is
    stubbed, but the clients refuse to start without one."""
    had = name in os.environ
    if not had:
        os.environ[name] = "test-key-not-real"
    return lambda: None if had else os.environ.pop(name, None)


def _patched(module, clock, monkey):
    saved = (module._post, module.time.time, module.time.sleep)
    module._post = clock.post
    module.time.time, module.time.sleep = clock.time, clock.sleep
    monkey.append((module, saved))


def _restore(monkey):
    for module, (post, t, sleep) in monkey:
        module._post, module.time.time, module.time.sleep = post, t, sleep


def test_no_gemini_request_outlasts_the_callers_budget():
    clock, monkey, undo = _Clock(), [], _key("GEMINI_API_KEY")
    _patched(gemini, clock, monkey)
    try:
        start = clock.now
        out = gemini.generate("q", deadline=30)
    finally:
        _restore(monkey); undo()
    assert out["ok"] is False and out.get("timed_out")
    assert all(t is not None and t <= 30 for t in clock.timeouts), clock.timeouts
    assert clock.now - start <= 30 + 1e-6, f"spent {clock.now - start:.0f}s of a 30s budget"


def test_a_hung_request_is_dropped_at_the_cap_so_the_next_model_gets_a_turn():
    """The Companion's first model hung for most of 27 seconds while the next answered in
    under one. With a 12-second cap, no request waits longer than 12."""
    clock, monkey, undo = _Clock(), [], _key("GEMINI_API_KEY")
    _patched(gemini, clock, monkey)
    try:
        gemini.generate("q", deadline=30, request_timeout=12)
    finally:
        _restore(monkey); undo()
    assert clock.timeouts and max(clock.timeouts) <= 12, clock.timeouts


def test_a_spent_budget_stops_the_pool_from_trying_every_other_model():
    clock, monkey, undo = _Clock(), [], _key("GEMINI_API_KEY")
    _patched(gemini, clock, monkey)
    try:
        gemini.generate("q", deadline=8)
    finally:
        _restore(monkey); undo()
    assert sum(clock.timeouts) <= 8 + 1e-6


def test_no_groq_request_outlasts_the_callers_budget():
    clock, monkey, undo = _Clock(), [], _key("GROQ_API_KEY")
    _patched(groq, clock, monkey)
    try:
        start = clock.now
        out = groq.generate("q", deadline=20)
    finally:
        _restore(monkey); undo()
    assert out["ok"] is False
    assert all(t is not None and t <= 20 for t in clock.timeouts), clock.timeouts
    assert clock.now - start <= 20 + 1e-6


def test_without_a_deadline_a_request_keeps_the_usual_timeout():
    clock, monkey, undo = _Clock(), [], _key("GROQ_API_KEY")
    _patched(groq, clock, monkey)
    try:
        groq._one("q", None, 0.0, "m")
    finally:
        _restore(monkey); undo()
    assert clock.timeouts[0] is None        # _post falls back to TIMEOUT


def test_the_reader_skips_a_second_read_it_has_no_time_for():
    """The fullest read so far beats a timeout: a reconciliation retry is only taken when
    the budget still has room for one."""
    calls = []

    def short_read(*, text=None, image=None, deadline=None):
        calls.append(deadline)
        time.sleep(0)                         # the read itself is instant here
        return ([{"charged": 10.0}], {"ok": True, "total_printed": 99.0})

    saved = extract.read_bill
    extract.read_bill = short_read
    try:
        extract.read_bill_verified(text="x", deadline=5)
    finally:
        extract.read_bill = saved
    assert len(calls) == 1, f"took {len(calls)} reads with 5s of budget"


def test_both_reader_prompts_say_the_page_is_data():
    assert extract.PAGE_IS_DATA in extract.PROMPT
    assert extract.PAGE_IS_DATA in extract.BILL_PROMPT


def test_a_record_of_the_wrong_shape_is_read_as_nothing_rather_than_a_crash():
    """The reader trusts nothing in a model's answer - except, it turned out, its shape: a
    JSON list, or a medicine given as a bare string, raised AttributeError on the Add
    screen. Those now come back as an empty record and are skipped, respectively."""
    for raw in ([{"title": "x"}], "a record", 7, None):
        rec = extract._shape(raw)
        assert rec["title"] == "Untitled record" and rec["medications"] == [], raw
    rec = extract._shape({"title": "Rx", "medications": ["Amoxicillin 500 mg", None,
                                                         {"name": "Ibuprofen", "dose": 400}]})
    assert [m["name"] for m in rec["medications"]] == ["Ibuprofen"]
    assert rec["medications"][0]["dose"] == "400"


def test_a_bill_answered_as_a_bare_list_is_read_as_its_lines():
    """A model nudged towards JSON (the Groq path has no schema) can answer with the list
    of lines itself, or slip a string in among them. Both raised AttributeError; a bare list
    is the lines, and a line that is not an object is skipped."""
    def answer(payload):
        import gemini
        real = gemini.generate
        gemini.generate = lambda *a, **k: {"ok": True, "model": "stand-in", "json": payload}
        try:
            return extract.read_bill(text="a bill")
        finally:
            gemini.generate = real
    groq_key = os.environ.pop("GROQ_API_KEY", None)
    try:
        lines, meta = answer([{"code": "70450", "description": "CT head", "units": 1,
                               "charged": 3100}, "a stray string", None])
        assert meta["ok"] and [l["code"] for l in lines] == ["70450"], (lines, meta)
        lines, meta = answer("not json at all")
        assert lines == [] and meta["ok"] is not None
    finally:
        if groq_key is not None:
            os.environ["GROQ_API_KEY"] = groq_key


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
