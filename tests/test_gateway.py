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
import urllib.error

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
    # A blank value is no key: the clients refuse one, and CI runs with them blank.
    saved = os.environ.get(name)
    if not (saved or "").strip():
        os.environ[name] = "test-key-not-real"

    def undo():
        if saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = saved
    return undo


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



# ---- the pool, from the test pass ----------------------------------------------------

def _http_error(code, body):
    import io
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(body.encode()))


class _PerModel(_Clock):
    """The network, answering per model: a dict of model name -> exception or answer."""

    def __init__(self, behaviour):
        super().__init__()
        self.behaviour, self.asked = behaviour, []

    def post(self, url, payload, timeout=None):
        model = next(m for m in self.behaviour if f"/models/{m}:" in url)
        self.asked.append(model)
        self.timeouts.append(timeout)
        what = self.behaviour[model]
        if isinstance(what, BaseException):
            if isinstance(what, TimeoutError):
                self.now += timeout or 45
            raise what
        return what


OK = {"candidates": [{"content": {"parts": [{"text": '{"answer": "fine"}'}]}}]}


def _pool(behaviour, **kwargs):
    clock, monkey, undo = _PerModel(behaviour), [], _key("GEMINI_API_KEY")
    saved_pool, saved_state = gemini.POOL, gemini._exhausted
    gemini.POOL, gemini._exhausted = list(behaviour), gemini.pool_state.new_state()
    _patched(gemini, clock, monkey)
    try:
        out = gemini.generate("q", schema={"type": "object"}, **kwargs)
        retired = [m for m in behaviour if gemini.pool_state.is_retired(gemini._exhausted, m)]
    finally:
        _restore(monkey); undo()
        gemini.POOL, gemini._exhausted = saved_pool, saved_state
    return out, clock.asked, retired


def test_a_hung_model_hands_over_to_the_next_one_instead_of_being_asked_again():
    """The first model hung to its 12-second cap, was asked again, and the budget ran out
    without the healthy second model ever being tried."""
    out, asked, _ = _pool({"m0": TimeoutError("timed out"), "m1": OK},
                          deadline=30, request_timeout=12)
    assert out["ok"] and out["model"] == "m1", out
    assert asked == ["m0", "m1"], asked


def test_a_model_this_key_cannot_reach_hands_over_to_the_next():
    out, asked, _ = _pool({"m0": _http_error(404, "model not found"), "m1": OK}, deadline=30)
    assert out["ok"] and asked == ["m0", "m1"], (out, asked)


def test_a_per_minute_limit_moves_on_without_retiring_the_model_for_an_hour():
    out, asked, retired = _pool({"m0": _http_error(429, "RESOURCE_EXHAUSTED per minute"),
                                 "m1": OK}, deadline=30)
    assert out["ok"] and retired == [], retired
    out, asked, retired = _pool({"m0": _http_error(429, "GenerateRequestsPerDayPerProject"),
                                 "m1": OK}, deadline=30)
    assert out["ok"] and retired == ["m0"], retired


def test_a_malformed_request_still_stops_the_pool():
    out, asked, _ = _pool({"m0": _http_error(400, "bad request 14290 tokens"), "m1": OK},
                          deadline=30)
    assert not out["ok"] and asked == ["m0"], asked


def test_an_unreadable_response_is_a_failure_not_a_traceback():
    import http.client
    for broken in (http.client.IncompleteRead(b"partial"), ["a", "json", "array"],
                   ValueError("Expecting value: an HTML page")):
        out, _, _ = _pool({"m0": broken}, deadline=30)
        assert out["ok"] is False and out["error"], broken


def test_groq_moves_on_after_a_per_minute_limit():
    clock, monkey, undo = _Clock(), [], _key("GROQ_API_KEY")
    asked = []

    def post(payload, timeout=None):
        asked.append(payload["model"])
        if payload["model"] == "g0":
            raise _http_error(429, "Rate limit reached: tokens per minute (TPM)")
        return {"choices": [{"message": {"content": '{"answer": "fine"}'}}]}
    saved_pool = groq.POOL
    groq.POOL = ["g0", "g1"]
    _patched(groq, clock, monkey)
    groq._post = post
    try:
        out = groq.generate("q", schema={"type": "object"}, deadline=30)
    finally:
        _restore(monkey); undo()
        groq.POOL = saved_pool
    assert out["ok"] and out["model"] == "g1", (out, asked)


# ---- the reader, from the test pass ------------------------------------------------

def test_a_failed_second_read_does_not_cost_the_first_one():
    reads = iter([([{"charged": 10.0}], {"ok": True, "total_printed": 99.0}),
                  ([], {"ok": False, "error": "HTTP 503"})])
    saved = extract.read_bill
    extract.read_bill = lambda **k: next(reads)
    try:
        lines, meta = extract.read_bill_verified(text="x", deadline=60)
    finally:
        extract.read_bill = saved
    assert lines == [{"charged": 10.0}] and meta["ok"] and meta["attempts"] == 2


def test_a_bill_read_as_having_no_charges_says_so_rather_than_not_attempted():
    saved = extract.read_bill
    extract.read_bill = lambda **k: ([], {"ok": True, "total_printed": None})
    try:
        lines, meta = extract.read_bill_verified(text="x", deadline=60)
    finally:
        extract.read_bill = saved
    assert lines == [] and meta["ok"] is True, meta


def test_a_printed_total_written_as_money_is_still_a_total():
    import gemini as g
    saved = g.generate
    g.generate = lambda *a, **k: {"ok": True, "model": "m", "json": {
        "line_items": [{"code": "70450", "description": "CT", "units": 1, "charged": 3399}],
        "total_printed": "$3,399.00"}}
    groq_key = os.environ.pop("GROQ_API_KEY", None)
    try:
        lines, meta = extract.read_bill(text="a bill")
    finally:
        g.generate = saved
        if groq_key is not None:
            os.environ["GROQ_API_KEY"] = groq_key
    assert meta["total_printed"] == 3399.0, meta


def test_a_rotated_phone_photo_is_shrunk_the_right_way_up():
    """Shrinking dropped the photo's orientation tag, so the reader got the page sideways."""
    import io
    from PIL import Image
    im = Image.new("RGB", (3000, 2000), "white")
    exif = im.getexif()
    exif[0x0112] = 6                                  # rotate 90° clockwise to display
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    mime, data = extract.shrink("image/jpeg", buf.getvalue())
    out = Image.open(io.BytesIO(data))
    assert out.size[0] < out.size[1], out.size        # portrait, as the phone showed it


def test_a_transparent_image_is_shrunk_onto_white_not_black():
    import io
    from PIL import Image
    im = Image.new("RGBA", (3000, 2000), (0, 0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    mime, data = extract.shrink("image/png", buf.getvalue())
    assert Image.open(io.BytesIO(data)).convert("RGB").getpixel((10, 10)) == (255, 255, 255)



def test_the_readers_money_keeps_a_credits_sign():
    assert extract._as_money("(150.00)") == -150.0
    assert extract._as_money("1,234.50 CR") == -1234.5
    assert extract._as_money("-154.00") == -154.0
    assert extract._as_money("$3,100.00") == 3100.0
    assert extract._as_money(3100) == 3100.0



def test_a_caller_can_put_its_preferred_models_first_and_keep_the_rest_behind_them():
    out, asked, _ = _pool({"m0": _http_error(503, "overloaded"), "m1": OK, "m2": OK},
                          deadline=30, prefer=("m2",))
    assert out["ok"] and out["model"] == "m2" and asked == ["m2"], asked
    out, asked, _ = _pool({"m0": OK, "m1": OK, "m2": _http_error(404, "not for this key")},
                          deadline=30, prefer=("m2", "not-in-the-pool"))
    assert out["model"] == "m0" and asked == ["m2", "m0"], asked


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
