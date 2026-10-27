#!/usr/bin/env python3
"""The signed-out page.

A sign-in box on an empty grey background tells a visitor nothing about what they are
signing in to, which matters more here than in most apps: the people this is built for
arrive holding a bill they do not understand, and the page has about four seconds to say
what it will do about that.

Every claim on this page is one the app actually delivers, and the ones with numbers in
them name their source. A marketing page that overstates a tool is a worse failure here
than a plain one, because the whole product is an argument about trusting a figure.
"""
import logo

SUPPORT = "45 CFR 180"


def _icon(body, size=21):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{body}</svg>')


TICK = _icon('<path d="M20 6.5 9.4 17.2 4.2 12"/>', size=13)

VAULT_IC = _icon('<rect x="3" y="4.4" width="18" height="15.2" rx="3.2"/>'
                 '<circle cx="12" cy="12" r="3.1"/>'
                 '<path d="M12 8.9V7M12 17v-1.9M8.9 12H7M17 12h-1.9"/>')
BILL_IC = _icon('<path d="M4.5 3.5h11v17l-1.8-1.3-1.9 1.3-1.8-1.3-1.9 1.3-1.8-1.3-1.8 1.3z"/>'
                '<path d="M7.5 8h5M7.5 11.5h5"/>'
                '<circle cx="17.2" cy="14.6" r="3.3"/><path d="M19.7 17.1 21.6 19"/>')
BADGE_IC = _icon('<path d="M12 3.2 14.1 4.7l2.6-.2 1 2.4 2.2 1.4-.8 2.5.8 2.5-2.2 1.4-1 2.4'
                 '-2.6-.2L12 20.8l-2.1-1.5-2.6.2-1-2.4-2.2-1.4.8-2.5-.8-2.5 2.2-1.4 1-2.4'
                 ' 2.6.2z"/><path d="M9.2 12.1 11.2 14.2 15 10"/>')


def nav():
    return (f"<div class='navbar'>{logo.wordmark(size=20, uid='n')}"
            f"<div class='links'><span class='free'>Free to use</span></div></div>")


def hero():
    ticks = [
        "Free, and no cut of what you save",
        "Priced against published files",
        "Every figure says where it came from",
    ]
    pills = "".join(f"<span>{TICK}{t}</span>" for t in ticks)
    return (
        "<div class='hero'>"
        "<div class='eyebrow'><i></i>Records and bills, one app</div>"
        "<h1>Your medical history, and the <em>bill that follows it</em>.</h1>"
        "<p class='lead'>Keep every prescription, report and discharge summary in one "
        "place — then check the hospital's bill, line by line, against the price that "
        "hospital published and the national Medicare allowance.</p>"
        f"<div class='ticks'>{pills}</div>"
        "</div>")


FEATURES = [
    (VAULT_IC, "One vault for all of it",
     "Prescriptions, lab reports, scans, discharge summaries and insurance details, filed "
     "by date and searchable. The emergency card puts blood type, allergies and next of "
     "kin on one screen you can hold up at a desk."),
    (BILL_IC, "Every line of the bill, checked",
     "Each charge is compared against the hospital's own published price file, the national "
     "Medicare allowance, and the records already in your vault. Arithmetic, duplicates and "
     "unspecified codes are checked on the bill's own face."),
    (BADGE_IC, "Confirmed by the clinician who issued it",
     "A doctor signs in through the CMS national provider registry and confirms the records "
     "they recognise. Everything else stays labelled as filed by you — the badge is on "
     "every record, not only the confirmed ones."),
]


def feature(icon, title, body):
    return (f"<div class='feature'><div class='ic'>{icon}</div>"
            f"<h3>{title}</h3><p>{body}</p></div>")


STEPS = [
    ("File what you already have",
     "Photograph a prescription or upload a PDF. It is read, dated and filed, and the "
     "medicines inside it are pulled out into a list of what you are taking now."),
    ("Paste the bill when it arrives",
     "Name the hospital if you know it, or leave it unset. Either way every line is priced, "
     "and the law that may already cover the bill is checked first."),
    ("Take the questions to the billing office",
     "You get a letter you can send, built only from the lines that did not add up, with "
     "the source behind each number so somebody can check your working."),
]


def steps():
    out = "".join(
        f"<div class='step'><div class='n'></div><div><h4>{t}</h4><p>{b}</p></div></div>"
        for t, b in STEPS)
    return f"<div class='steps'>{out}</div>"


def footer(durable=None):
    """The last line is where the records actually live.

    It states the real answer rather than a fixed sentence, because this is the one claim
    on the page a deployment can falsify - and it is readable without signing in, which
    is how a deployment's storage can be checked from outside at all.

    `durable=None` means "work it out", and the argument is optional on purpose. The
    first version made it required-with-a-default and the caller passed it by keyword,
    which took the live site down: Streamlit reran the new app.py against a `landing`
    module still in memory from the previous deploy, and footer() did not yet accept the
    keyword. A signature that an older caller can still call cannot fail that way, and a
    landing page is the last thing that should be able to crash.
    """
    if durable is None:
        try:
            import store
            durable = store.configured()
        except Exception:        # noqa: BLE001 - a footer must never take the page down
            durable = False
    where = ("Your records are kept in a database that outlives a restart of this "
             "server." if durable else
             "Your records are kept on the server this copy runs on, and a free host "
             "wipes that disk when it restarts.")
    return (
        f"<div class='sitefoot'>{logo.wordmark(size=15, uid='f')}"
        "<div><b>A student project, built for INFO 7375 at Northeastern.</b> "
        "Not medical, billing or legal advice.</div>"
        f"<div>Published prices come from the hospital machine-readable files required by "
        f"{SUPPORT}; the national benchmark is the CMS Physician Fee Schedule. The rights "
        "section follows the No Surprises Act and IRC 501(r) and tells you what may apply "
        "to a bill, never what will.</div>"
        f"<div>{where} Two things leave it, and only when you ask for them: a document "
        "you upload to be read, and — if you use the question box — your question and "
        "the text of your records.</div>"
        "</div>")
