#!/usr/bin/env python3
"""The national benchmark must be useful without being mistaken for a price cap.

Offline: every test here uses a seeded cache rather than the network, so the suite does not
depend on a third-party service being up.

Run with  python3 tests/test_medicare.py
"""
import json, pathlib, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))


def fresh_module(seed=None):
    """medicare.py with a private cache, so tests never hit the network or each other."""
    import importlib, os
    path = tempfile.mktemp(suffix=".json")
    if seed:
        pathlib.Path(path).write_text(json.dumps(seed))
    os.environ["MEDVAULT_MEDICARE_CACHE"] = path
    import medicare
    importlib.reload(medicare)
    return medicare


SEEDED = {
    "70450": {"code": "70450", "found": True, "name": "CT Scan of the Head without Contrast",
              "plain": "A CT of the head.", "category": "Radiology",
              "medicare_rate": 106.55, "commercial_low": 160.0, "commercial_high": 266.0,
              "effective_year": 2026, "dataset": "CMS_PFS", "_at": time.time()},
    "99999": {"code": "99999", "found": False, "why": "Not in the national fee schedule.",
              "_at": time.time()},
}


def test_a_cached_code_needs_no_network():
    m = fresh_module(SEEDED)
    r = m.lookup("70450")
    assert r["found"] and r["medicare_rate"] == 106.55
    assert r["name"] == "CT Scan of the Head without Contrast"
    assert "_at" not in r, "the cache timestamp must not leak into the result"


def test_the_plain_english_name_is_the_point():
    # A bill says "HCHG CT HEAD/BRAIN W/O CONTRAST". This is what closes that gap, and it
    # is sourced rather than invented, which is why the project can now show it at all.
    m = fresh_module(SEEDED)
    assert "CT Scan of the Head" in m.lookup("70450")["name"]


def test_hcpcs_is_reported_as_out_of_scope_not_as_missing():
    m = fresh_module(SEEDED)
    for code in ("J3490", "A0427", "G0379"):
        r = m.lookup(code)
        assert r["found"] is False
        assert "CPT" in r["why"], f"{code} should say why, not just fail"


def test_rubbish_input_does_not_reach_the_network():
    m = fresh_module(SEEDED)
    for bad in ("", None, "abc", "1234", "123456"):
        assert m.lookup(bad)["found"] is False


def test_a_known_miss_is_remembered_rather_than_re_fetched():
    m = fresh_module(SEEDED)
    assert m.lookup("99999")["found"] is False


def test_the_multiple_is_computed_per_unit():
    m = fresh_module(SEEDED)
    # four blood draws at $9.34 allowed is $37.36; billed $260 is about 7x
    assert m.multiple_of_medicare(260.0, 4, 9.34) == 7.0
    assert m.multiple_of_medicare(106.55, 1, 106.55) == 1.0
    assert m.multiple_of_medicare(1619.0, 1, 106.55) == 15.2


def test_the_multiple_is_none_when_it_cannot_be_known():
    m = fresh_module(SEEDED)
    assert m.multiple_of_medicare(100.0, 1, None) is None
    assert m.multiple_of_medicare(None, 1, 50.0) is None
    assert m.multiple_of_medicare(100.0, 1, 0) is None


def test_lookup_many_deduplicates():
    m = fresh_module(SEEDED)
    out = m.lookup_many(["70450", "70450", "99999", "", None])
    assert set(out) == {"70450", "99999"}


def test_no_commercial_estimate_is_surfaced():
    """The endpoint returns a low/high "commercial" band that is exactly 1.5x and 2.5x the
    Medicare rate on every code — a multiplier, not a measurement. It was being shown as
    "commercial plans typically pay $287.58–$479.30" and cited to the CMS fee schedule,
    which publishes no commercial rates at all. It must not come back."""
    m = fresh_module(SEEDED)
    out = m.lookup("70450")
    assert "commercial_low" not in out and "commercial_high" not in out


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
