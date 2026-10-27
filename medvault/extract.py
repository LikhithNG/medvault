#!/usr/bin/env python3
"""The Reader - Madison **Intelligence**: read an uploaded document and turn it
into a record the vault can hold.

Two channels, same contract: a photograph goes to a vision model, a PDF with a text layer is
read locally first and only its text is sent. A PDF that yields no text is treated as a
photograph, because a scan is a photograph that happens to be in a PDF.

What this module will not do is guess. Every field it cannot read comes back null, and the
interface shows the gap rather than filling it. A vault that invents a dosage is worse than
a shoebox of paper, because paper does not sound confident.
"""
import base64, io as _io, json, os, re

from schema import KIND_ORDER, RECORD_FIELDS, MED_FIELDS

# A phone camera produces 3-5 MB per shot. None of that resolution helps a model read
# printed text, and all of it is carried in the request body as base64, which is a third
# bigger again. The first test photograph here was 147 KB and still ran past a 60-second
# timeout; an un-resized phone photo would never have returned at all.
MAX_EDGE = int(os.environ.get("MEDVAULT_MAX_EDGE", "1400"))
JPEG_QUALITY = 82


def shrink(mime, data):
    """Downscale an uploaded image for the reader.

    Takes and returns (mime_type, bytes) - the same order the image pair travels in
    everywhere else in this codebase, so it can be called as shrink(*image).

    Falls back to the original bytes if Pillow is unavailable or the file is not an image
    it can open - a document that reads slowly is better than one that cannot be read.
    """
    try:
        from PIL import Image
    except ImportError:
        return mime, data
    try:
        im = Image.open(_io.BytesIO(data))
        im.load()
    except Exception:
        return mime, data
    if max(im.size) <= MAX_EDGE and len(data) < 400_000:
        return mime, data
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((MAX_EDGE, MAX_EDGE))
    buf = _io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return "image/jpeg", buf.getvalue()

SCHEMA = {
    'type': 'object',
    'properties': {
        'kind':         {'type': 'string', 'enum': KIND_ORDER},
        'service_date': {'type': 'string'},
        'provider':     {'type': 'string'},
        'title':        {'type': 'string'},
        'summary':      {'type': 'string'},
        'medications': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {k: {'type': 'string'} for k in MED_FIELDS},
                'required': ['name'],
            },
        },
    },
    # 'medications' is required so the model has to answer the question rather than
    # omit the key. An empty list is the right answer for a lab report; silence is
    # not the right answer for a prescription, and silence is what optional produced.
    'required': ['kind', 'title', 'summary', 'medications'],
}

_FIELDS = "\n".join(f"- {k}: {v}" for k, v in RECORD_FIELDS.items())
_MEDS = "\n".join(f"  - {k}: {v}" for k, v in MED_FIELDS.items())

PROMPT = f"""You are reading one page of a patient's own medical paperwork so it can be
filed in their personal records. Report only what is printed on it.

Fill these fields:
{_FIELDS}

If the document prescribes, dispenses or lists medicines, you must list EVERY one of
them under "medications" - one entry per medicine, even if there are several. If the
document prescribes no medicines at all, return an empty list. For each medicine:
{_MEDS}

Rules, in order of importance:
1. Never invent a date, a dose, a provider or a diagnosis. If it is not printed, use null.
   A missing field is correct. A plausible guess is a safety problem.
2. Do not interpret results. "Haemoglobin 11.2 g/dL" is what it says; whether that is low is
   not yours to decide and the patient has a doctor for it.
3. "summary" is for the patient, not a clinician. Plain words, one or two sentences, no
   abbreviations the page did not already use.
4. "title" is short enough to read in a list - under about six words.
"""


def _as_text_prompt(text):
    return PROMPT + "\n\nThe document's text follows.\n\n" + text[:18000]


# Scripts that have no business appearing inside an otherwise-Latin medical field. Seen in
# the wild: a reason field came back as "For the sinus infection整度" - two CJK characters
# whose byte values (0x6574, 0x5ea6) look like a mis-decoded pair rather than anything the
# model meant. Stripping them only when the field is otherwise Latin leaves a genuinely
# non-Latin name or note alone.
_FOREIGN = re.compile(
    r"[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef\U00020000-\U0003ffff]")
_LATIN = re.compile(r"[A-Za-z]")


def _strip_artifacts(text):
    """Remove stray non-Latin characters from a field that is otherwise English."""
    if not _LATIN.search(text):
        return text                   # genuinely non-Latin content: leave it alone
    return _FOREIGN.sub("", text).strip()


def _clean(value):
    """Empty strings and the model's various ways of saying nothing all become None."""
    if value is None:
        return None
    v = _strip_artifacts(str(value).strip())
    # Collapse the whitespace a stripped character can leave behind.
    v = re.sub(r"\s{2,}", " ", v).strip()
    if not v or v.lower() in {"null", "none", "n/a", "na", "unknown", "not printed", "-"}:
        return None
    return v


DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _clean_date(value):
    """The first real calendar date anywhere in the value, or None.

    This used to require the whole field to be exactly YYYY-MM-DD. A model under a
    structured-output schema returned "2026-09-18 Whittled down: 2026-09-18 -> ..." - it had
    leaked its own reasoning into the string - and the strict match threw away a date that
    was plainly there, three times over. Reading the date out of the noise is both more
    forgiving and no less safe: the calendar check below still rejects anything impossible.
    """
    v = _clean(value)
    if not v:
        return None
    m = DATE.search(v)
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    try:
        import datetime
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None          # 2026-13-45 and friends


def _shape(raw):
    """One model answer in, one record dict out, with nothing trusted on the way through."""
    meds = []
    for m in (raw.get("medications") or []):
        name = _clean(m.get("name"))
        if not name:
            continue                     # a dose with no medicine attached helps nobody
        meds.append({k: _clean(m.get(k)) for k in MED_FIELDS} | {"name": name})

    kind = _clean(raw.get("kind"))
    return {
        "kind":         kind if kind in KIND_ORDER else "other",
        "service_date": _clean_date(raw.get("service_date")),
        "provider":     _clean(raw.get("provider")),
        "title":        _clean(raw.get("title")) or "Untitled record",
        "summary":      _clean(raw.get("summary")),
        "medications":  meds,
    }


def read_document(*, text=None, image=None):
    """Extract a record. `image` is an (mime_type, raw_bytes) pair.

    Returns (record_or_None, meta). meta always says what happened, so the interface can
    tell a missing key apart from an unreadable page - the distinction that cost Itemized
    four separate defects to get right.
    """
    import gemini

    if not text and not image:
        return None, {"ok": False, "error": "nothing to read"}

    if image:
        mime, data = shrink(*image)
        payload = (mime, base64.b64encode(data).decode())
        r = gemini.generate(PROMPT, schema=SCHEMA, image=payload)
    else:
        r = gemini.generate(_as_text_prompt(text), schema=SCHEMA)

    if not r.get("ok"):
        return None, {"ok": False, "error": r.get("error"), "model": r.get("model"),
                      "pool_exhausted": r.get("pool_exhausted", False)}

    raw = r.get("json")
    if raw is None:
        try:
            raw = json.loads(r.get("text") or "")
        except (json.JSONDecodeError, TypeError):
            return None, {"ok": False, "error": "the reader did not return a record",
                          "model": r.get("model")}

    return _shape(raw), {"ok": True, "model": r.get("model")}


def pdf_text(upload):
    """Text out of a PDF's text layer. (text, note) or (None, reason)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, "pdf support is not installed on this server"
    try:
        reader = PdfReader(upload)
        pages = [(pg.extract_text() or "") for pg in reader.pages]
    except Exception as e:
        return None, f"this file could not be opened as a PDF ({str(e)[:80]})"
    text = "\n".join(pages).strip()
    if len(text) < 40:
        return None, "scanned"           # no text layer: it is a photograph in a PDF wrapper
    return text, f"{len(reader.pages)} page(s)"


# ---- reading a bill ---------------------------------------------------------
# A bill is not a record: it has line items with codes, units and amounts, and the checks
# that run on it need all four. Schema and prompt carried over from Itemized, where they
# were measured at precision 1.000 / recall 1.000 across 115 statements.

BILL_SCHEMA = {
    'type': 'object',
    'properties': {
        'hospital_name_on_bill': {'type': 'string'},
        'date_of_service': {'type': 'string'},
        'total_printed': {'type': 'number'},
        'line_items': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'code':         {'type': 'string'},
                    'description':  {'type': 'string'},
                    'units':        {'type': 'integer'},
                    'charged':      {'type': 'number'},
                    'service_date': {'type': 'string'},
                },
                'required': ['code', 'units', 'charged'],
            },
        },
    },
    'required': ['line_items'],
}

BILL_PROMPT = """You are reading an itemised hospital bill. Extract EVERY charge line on
the page - a bill with five rows must return five objects.

Work down the table one row at a time and emit an object for each, in the order printed.
Do not stop after the first row. Do not summarise. Do not merge rows that share a code.

For each row:
- code: the billing code as printed (CPT like 99284, HCPCS like J2405 or G0379). Never
  invent one; leave it empty if the row prints no code.
- description: the text as printed, abbreviations and all. Do not expand them.
- units: the quantity column. 1 if no quantity is shown.
- charged: that row's amount, as a plain number - no currency symbol, no commas.
- service_date: that row's own date as YYYY-MM-DD if printed, otherwise null.

Also report hospital_name_on_bill and date_of_service by reading them off the top of this
statement. If they are not printed on it, return null - never a placeholder.

Ignore totals, balances, subtotals, payments and adjustments: they are not charge lines.
Report the printed grand total separately as total_printed, so the lines can be checked
against it. Null if the statement prints no total.

Do not judge, correct, re-price or comment on anything.
"""


# Gemini enforces the response schema; Groq's JSON mode only asks for valid JSON, so the
# model names the keys itself - it returned the rows under "charges" rather than
# "line_items" and every line was silently dropped. The prompt now names the key, and this
# accepts the obvious synonyms as well, because a reader that loses a whole bill over a
# key name is a worse failure than a slightly loose parser.
ITEM_KEYS = ("line_items", "charges", "lines", "items", "line_item", "charge_lines")


def _as_money(value):
    """A number, or a string like "3,100.00" or "$3,100.00". None when it is neither.

    Only Gemini's schema guarantees a number here; a provider without schema enforcement
    returns whatever the model felt like, and a comma should not cost a line.
    """
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[^\d.\-]", "", value)
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def _line_items(raw):
    for key in ITEM_KEYS:
        v = raw.get(key)
        if isinstance(v, list) and v:
            return v
    # Last resort: the first list of objects anywhere in the answer.
    for v in raw.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
    return []


def _clean_line(raw):
    code = (_clean(raw.get("code")) or "").upper().replace(" ", "")
    charged = _as_money(raw.get("charged"))
    if charged is None:
        return None                      # a line with no amount is not a charge
    try:
        units = int(raw.get("units") or 1)
    except (TypeError, ValueError):
        units = 1
    # No unit_price: see the schema note above. A reader that derives one defeats the
    # arithmetic check, and cannot tell us which it did.
    return {"code": code or None,
            "description": _clean(raw.get("description")) or (code or "Unlabelled charge"),
            "units": max(units, 1), "charged": round(charged, 2),
            "service_date": _clean_date(raw.get("service_date"))}


# Groq serves open-source models on a free tier - gpt-oss, Qwen - and its key reaches none
# with vision. So the two halves of reading a bill go to different places, and the split is
# useful rather than a compromise: most bills arrive as a PDF from a patient portal, which
# has a text layer and needs no vision at all. Those run entirely on open models.
#
# Groq's JSON mode additionally refuses a prompt that does not contain the word "json",
# while Gemini copied a worked JSON example straight into its answer when one was present.
# The requirement is therefore added per provider instead of compromising the shared prompt.
JSON_NUDGE = ("\n\nReturn json with the charge rows in a key named exactly "
              "\"line_items\", plus hospital_name_on_bill, date_of_service and "
              "total_printed.")


def read_bill(*, text=None, image=None, prefer_open=True):
    """Extract a bill's line items. Returns (lines, meta).

    Text goes to Groq's open models when a key is there; a photograph needs vision and so
    goes to Gemini. meta['provider'] says which answered.
    """
    if not text and not image:
        return [], {"ok": False, "error": "nothing to read"}

    provider = None
    if image:
        import gemini
        mime, data = shrink(*image)
        payload = (mime, base64.b64encode(data).decode())
        r = gemini.generate(BILL_PROMPT, schema=BILL_SCHEMA, image=payload)
        provider = "gemini (vision)"
    else:
        body = BILL_PROMPT + "\n\nThe bill's text follows.\n\n" + text[:18000]
        r = None
        if prefer_open and os.environ.get("GROQ_API_KEY", "").strip():
            import groq
            r = groq.generate(BILL_PROMPT + JSON_NUDGE
                              + "\n\nThe bill's text follows.\n\n" + text[:18000],
                              schema=BILL_SCHEMA)
            provider = "groq (open models)"
            if not r.get("ok"):
                r = None                 # fall through to the other provider
        if r is None:
            import gemini
            r = gemini.generate(body, schema=BILL_SCHEMA)
            provider = "gemini"

    if not r.get("ok"):
        return [], {"ok": False, "error": r.get("error"), "model": r.get("model"),
                    "provider": provider}

    raw = r.get("json")
    if raw is None:
        try:
            raw = json.loads(r.get("text") or "")
        except (json.JSONDecodeError, TypeError):
            return [], {"ok": False, "error": "the reader did not return a bill",
                        "model": r.get("model"), "provider": provider}

    lines = [c for c in (_clean_line(l) for l in _line_items(raw)) if c]
    try:
        printed = round(float(raw["total_printed"]), 2) if raw.get("total_printed") else None
    except (TypeError, ValueError):
        printed = None
    return lines, {"ok": True, "model": r.get("model"), "provider": provider,
                   "hospital": _clean(raw.get("hospital_name_on_bill")),
                   "date_of_service": _clean_date(raw.get("date_of_service")),
                   "total_printed": printed}


# A bill carries its own checksum. Measured over five reads of the same photograph, this
# reader returned all five lines four times and a single line once - a silent 20% failure
# that would show a patient $3,100 of a $13,300 bill and run every check on the remainder.
# The printed total catches exactly that, so it is checked rather than trusted, and a read
# that does not reconcile is taken again before anyone is shown a number.
RECONCILE_TOLERANCE = 0.02


def reconciles(lines, total_printed):
    """Whether the lines add up to the total the bill prints. None when it prints none."""
    if total_printed is None:
        return None
    return abs(round(sum(l["charged"] for l in lines), 2) - total_printed) <= RECONCILE_TOLERANCE


def read_bill_verified(*, text=None, image=None, attempts=2):
    """read_bill, but checked against the bill's own total and retried when it disagrees.

    Returns (lines, meta) with meta['reconciled'] set to True, False or None, so the
    interface can say "this did not add up" instead of quietly showing a short bill.
    """
    best, best_meta = [], {"ok": False, "error": "not attempted"}
    for attempt in range(1, attempts + 1):
        lines, meta = read_bill(text=text, image=image)
        meta["attempts"] = attempt
        if not meta.get("ok"):
            return lines, meta

        agrees = reconciles(lines, meta.get("total_printed"))
        meta["reconciled"] = agrees
        if agrees is True:
            return lines, meta

        # A missing total is not the same as a bill without one. When this reader truncates
        # it truncates everything, the total included - the run that returned two of five
        # lines also returned no total, so there was nothing left to catch it with. An
        # unverifiable read is therefore retried rather than accepted, and the fullest
        # attempt is what survives.
        if len(lines) > len(best):
            best, best_meta = lines, meta
    return best, best_meta

