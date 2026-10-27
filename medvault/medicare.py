#!/usr/bin/env python3
"""A national benchmark for any CPT code, and a plain-English name for it.

The reference table this project ships covers 262 codes across 9 hospitals, which is the
weakest thing about it: a bill from anywhere else gets the rights checks, the arithmetic and
the records cross-check, and nothing at all under "is this the right amount". This fills
that gap with a national Medicare benchmark that works for any covered code.

Two honest notes about the source, both of which belong in the interface:

1. The endpoint is a third-party service that republishes the CMS Physician Fee Schedule.
   It is not CMS itself. The figures it returns carry CMS's own effective year and dataset
   name, which is checkable, but a republisher can be wrong or go away in a way that
   data.cms.gov cannot.

2. **A Medicare rate is not a price cap.** Medicare pays what Medicare pays; a hospital is
   entitled to charge a commercial patient more, and routinely does. The benchmark answers
   "how does this compare to what the federal programme allows", which is context for a
   conversation, not evidence of an overcharge. The interface must never phrase it as one.

Coverage is CPT. HCPCS Level II codes - J-codes for drugs, G-codes, A-codes - are not in
the dataset and come back as misses.

Responses are cached to disk. They change about once a year, a demo should not depend on a
network, and nobody should be hammering a free service to re-read the same code.
"""
import json, os, pathlib, re, time, urllib.error, urllib.request

API = "https://medical-costs-api.david-568.workers.dev/api/procedures/"
UA = "medvault/1.0 (INFO7375 coursework; python-urllib)"
TIMEOUT = 12

CACHE = pathlib.Path(os.environ.get(
    "MEDVAULT_MEDICARE_CACHE",
    pathlib.Path(__file__).resolve().parent.parent / "data" / "medicare_cache.json"))
# CMS republishes the fee schedule annually; a month is comfortably inside that.
TTL_SECONDS = 30 * 24 * 3600

CPT = re.compile(r"^\d{5}$")

_memory = None


def _load():
    global _memory
    if _memory is None:
        try:
            _memory = json.loads(CACHE.read_text())
        except (OSError, json.JSONDecodeError):
            _memory = {}
    return _memory


def _save():
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(_memory, indent=1, sort_keys=True))
    except OSError:
        pass            # a cache that cannot be written is a slow lookup, not a failure


def _shape(code, data):
    consumer = data.get("consumerDescription") or {}
    # The endpoint also returns a "commercialEstimates" low/high band. It is not observed
    # commercial pricing: on every code checked it is exactly 1.5x and 2.5x the Medicare
    # rate, to three decimals - a multiplier, not a measurement. Displaying it as
    # "commercial plans typically pay $287.58-$479.30" put false precision on an
    # assumption and cited it to the CMS fee schedule, which publishes no commercial
    # rates at all. In a tool whose whole claim is that every figure says where it came
    # from, that was the worst line on the screen. It is not read.
    rate = data.get("nationalFacilityRate")
    return {
        "code": code,
        "found": True,
        # The plain-English name. This is the half of the answer that matters most on a
        # patient's screen: a bill says "HCHG CORE CBC AUTO" and this says what that is.
        "name": consumer.get("consumerName") or data.get("description"),
        "plain": consumer.get("plainDescription"),
        "category": data.get("category"),
        "medicare_rate": round(float(rate), 2) if rate is not None else None,
        "effective_year": data.get("effectiveYear"),
        "dataset": data.get("sourceDataset"),
    }


# Fields a caller may rely on. A cache written before a field was retired must not hand
# that field back: the commercial band was removed from the parser and a two-week-old
# cache entry went on serving it, which is the quiet way a retired claim returns.
RETURNED = ("code", "found", "why", "name", "plain", "category",
            "medicare_rate", "effective_year", "dataset")


def _clean(entry):
    return {k: v for k, v in (entry or {}).items() if k in RETURNED}


def lookup(code, use_cache=True):
    """One code. Returns a dict with found=True/False. Never raises."""
    code = (code or "").strip().upper()
    if not CPT.match(code):
        # HCPCS is not in this dataset, and saying so beats a silent miss.
        return {"code": code, "found": False,
                "why": "Only 5-digit CPT codes are in this dataset."}

    cache = _load()
    hit = cache.get(code)
    if use_cache and hit and (time.time() - hit.get("_at", 0)) < TTL_SECONDS:
        return _clean(hit)

    req = urllib.request.Request(API + code,
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        out = {"code": code, "found": False,
               "why": ("Not in the national fee schedule." if e.code == 404
                       else f"The benchmark service answered HTTP {e.code}.")}
        if e.code == 404:                       # a real miss is worth remembering
            cache[code] = out | {"_at": time.time()}; _save()
        return out
    except Exception as e:
        return {"code": code, "found": False,
                "why": f"The benchmark service could not be reached ({type(e).__name__})."}

    data = payload.get("data") if payload.get("success") else None
    out = _shape(code, data) if data else {
        "code": code, "found": False, "why": "Not in the national fee schedule."}
    cache[code] = out | {"_at": time.time()}
    _save()
    return _clean(out)


def lookup_many(codes):
    """Several codes, de-duplicated. Returns {code: result}."""
    return {c: lookup(c) for c in dict.fromkeys(
        (c or "").strip().upper() for c in codes if c)}


def multiple_of_medicare(charged, units, medicare_rate):
    """How many times the Medicare allowance a line was billed at. None when unknowable."""
    if not medicare_rate or not charged:
        return None
    expected = medicare_rate * max(int(units or 1), 1)
    if expected <= 0:
        return None
    return round(charged / expected, 1)
