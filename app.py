#!/usr/bin/env python3
"""MedVault — every piece of your medical paperwork, on the phone in your pocket.

Built phone-first. The question behind every screen is "could someone hold this up at a
hospital desk and have it be useful", which is a harder test than "does it look like an app".
"""
import datetime
import json
import os
import pathlib
import sys
import time

import streamlit as st

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "medvault"))

st.set_page_config(page_title="MedVault — your records, and the bill that follows",
                   page_icon=str(HERE / "static" / "icon-192.png"),
                   layout="centered", initial_sidebar_state="collapsed")

# Every setting that may come from a hosting platform's secrets rather than from .env.
# Streamlit puts secrets in st.secrets and NOT in os.environ, so anything missing from
# this tuple is silently ignored when deployed - which has now happened twice. It cost
# Itemized a working reader (GEMINI_API_KEY was omitted) and cost MedVault a working
# database (both TURSO keys were omitted, so a vault with a real database behind it went
# on quietly writing to a disk that gets wiped). tests/test_secrets.py reads the source
# for environment lookups and fails when one is not listed here.
SECRET_KEYS = ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_POOL", "GEMINI_TIMEOUT",
               "GEMINI_DEADLINE",
               "GROQ_API_KEY", "GROQ_MODEL", "GROQ_POOL", "GROQ_TIMEOUT",
               "POOL_RETIRE_SECONDS", "MEDVAULT_MAX_EDGE",
               "MEDVAULT_DB", "MEDVAULT_HOSTED", "MEDVAULT_MEDICARE_CACHE",
               "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "TURSO_TIMEOUT")
CRED_TRACE = []


def _load_credentials():
    """Promote credentials into the environment, where the reader looks for them.

    Same shape as Itemized's loader, including the lesson that cost that project two
    defects: read st.secrets through load_if_toml_exists() rather than guessing where the
    platform keeps the file, and list every key the app needs rather than only the first one.
    """
    try:
        if st.secrets.load_if_toml_exists():
            available = set(st.secrets.keys())
            CRED_TRACE.append(f"secrets file found · {len(available)} key(s)")
            for key in SECRET_KEYS:
                if key in available:
                    os.environ.setdefault(key, str(st.secrets[key]))
                    CRED_TRACE.append(f"{key} · promoted")
        else:
            CRED_TRACE.append("no secrets file (expected on a laptop)")
    except Exception as e:
        CRED_TRACE.append(f"secrets unreadable ({type(e).__name__})")

    env = HERE / ".env"
    if env.exists():
        CRED_TRACE.append(".env present · loaded")
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    else:
        CRED_TRACE.append(".env absent (expected on a server)")


    # Groq serves open models. This key cannot reach llama-3.3-70b, which groq.py would
    # otherwise fall back to and collect a 404 from, so the pool is set to what it serves.
    os.environ.setdefault("GROQ_MODEL", "openai/gpt-oss-120b")
    os.environ.setdefault("GROQ_POOL",
                          "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b")


_load_credentials()

import accounts                # noqa: E402
import agents                  # noqa: E402
import db                      # noqa: E402
import landing                 # noqa: E402
import ask                     # noqa: E402
import npi                     # noqa: E402
import paste                   # noqa: E402
import schedule                # noqa: E402
import store                   # noqa: E402
import ui                      # noqa: E402
from schema import (BLOOD_TYPES, KINDS, KIND_ORDER, kind_label,   # noqa: E402
                    missing_essentials)

st.markdown(ui.CSS, unsafe_allow_html=True)

import pwa                     # noqa: E402
pwa.install()                  # home-screen icon and standalone launch on a phone


@st.cache_resource
def vault():
    return db.connect()


con = vault()


# The Checker's verdicts are written for a pipeline. A patient needs a sentence.
VERDICTS = {
    "ABOVE_POSTED":     ("Charged above the published price", "bad"),
    "QUANTITY_SUSPECT": ("Quantity looks wrong", "warn"),
    "DUPLICATE":        ("Billed more than once", "warn"),
    "NOT_POSTED":       ("No published price to compare", "warn"),
    "UNREADABLE":       ("Could not be read", "warn"),
}


def _m(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"


def _date(iso):
    """2026-10-02 -> 2 October 2026. The date is read from the data; only its shape is
    written here, so a refreshed table moves the sentence instead of contradicting it."""
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%-d %B %Y")
    except (TypeError, ValueError):
        return str(iso)


def clinician_view():
    """A clinician reviews across patients; a patient only ever sees their own."""
    return accounts.is_verified_clinician(st.session_state.get("account"))


def me():
    """The signed-in account. Every data call is scoped through this."""
    return st.session_state.get("account") or {}


def my_id():
    return me().get("id")

def reader_ready():
    """Whether a document can be read at all, and why not when it cannot."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return False, "no reading key is configured on this server"
    if "…" in key or key in {"your-key", "AIza…", "changeme"}:
        return False, "the reading key is still placeholder text"
    return True, None


def when(rec):
    return rec.get("service_date") or "no date on file"


# ---------------------------------------------------------------- screens ----

def profile_editor(p, expanded):
    """The form behind the card. Separated out so it can be opened from two places.

    Blood type is a dropdown rather than a free-text box: it is the one field here where a
    typo is a safety problem, and "o positive", "O +" and "0+" are all things people type.
    """
    with st.expander("Set up your card" if expanded else "Edit this card", expanded=expanded):
        st.caption("This is what someone sees if they pick up your phone in an emergency. "
                   "Nothing here leaves this device.")

        st.markdown(ui.section("You"), unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        full = c1.text_input("Full name", p.get("full_name", ""))
        dob = c2.text_input("Date of birth", p.get("date_of_birth", ""),
                            placeholder="1999-07-12")
        blood_now = p.get("blood_type", "")
        blood = c1.selectbox("Blood type", BLOOD_TYPES,
                             index=BLOOD_TYPES.index(blood_now) if blood_now in BLOOD_TYPES else 0,
                             format_func=lambda b: b or "— not set —")
        donor = c2.selectbox("Organ donor", ("Not stated", "Yes", "No"),
                             index=("Not stated", "Yes", "No").index(
                                 p.get("organ_donor") or "Not stated"))

        st.markdown(ui.section("What they need to know first"), unsafe_allow_html=True)
        alle = st.text_area("Allergies", p.get("allergies", ""), height=70,
                            placeholder="Penicillin (rash), peanuts — or 'none known'")
        cond = st.text_area("Ongoing conditions", p.get("conditions", ""), height=70,
                            placeholder="Asthma, type 2 diabetes")

        st.markdown(ui.section("Who to call"), unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        econ = c1.text_input("Emergency contact", p.get("emergency_name", ""))
        erel = c2.text_input("Relationship", p.get("emergency_relation", ""),
                             placeholder="sister, partner")
        ephone = st.text_input("Their phone", p.get("emergency_phone", ""))

        st.markdown(ui.section("Your doctor"), unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        gp = c1.text_input("Primary doctor", p.get("gp_name", ""))
        gpp = c2.text_input("Their phone", p.get("gp_phone", ""), key="gpphone")

        st.markdown(ui.section("Insurance"), unsafe_allow_html=True)
        st.caption("The number reception asks for before anything else happens.")
        c1, c2 = st.columns(2)
        ins = c1.text_input("Insurer", p.get("insurer", ""), placeholder="Blue Cross")
        mem = c2.text_input("Member ID", p.get("member_id", ""))

        if st.button("Save my card", type="primary", use_container_width=True):
            db.save_profile(con, my_id(), {
                "full_name": full, "date_of_birth": dob, "blood_type": blood,
                "organ_donor": donor, "allergies": alle, "conditions": cond,
                "emergency_name": econ, "emergency_relation": erel,
                "emergency_phone": ephone, "gp_name": gp, "gp_phone": gpp,
                "insurer": ins, "member_id": mem})
            st.success("Saved.")
            st.rerun()


def detail_row(label, value, sub=None):
    return (f"<div class='med'><div class='n'>{value}</div>"
            f"<div class='d'>{sub}</div></div>" if sub else
            f"<div class='med'><div class='n'>{value}</div>"
            f"<div class='d'>{label}</div></div>")


def screen_card():
    """The emergency card: what someone needs when you cannot explain yourself."""
    p = db.get_profile(con, my_id())
    gaps = missing_essentials(p)

    # An empty card used to render as "Your name / None recorded" with the editor collapsed
    # at the very bottom, below the medicines. A new account had no way of knowing the card
    # was fillable at all. The prompt and the open form now come first.
    if gaps:
        pretty = {"full_name": "your name", "blood_type": "blood type",
                  "allergies": "allergies", "emergency_name": "an emergency contact"}
        st.warning("**Your card is not finished yet** — still missing "
                   + ", ".join(pretty[g] for g in gaps)
                   + ". This is the screen someone reads if you cannot speak for yourself.")
        profile_editor(p, expanded=True)
        if not p.get("full_name"):
            return

    meds = db.list_medications(con, active_only=True, owner_id=my_id())
    name = p.get("full_name") or "Your name"
    cells = [("Blood", p.get("blood_type") or "—"),
             ("Born", p.get("date_of_birth") or "—"),
             ("Records", str(sum(db.counts_by_kind(con, my_id()).values())))]
    cellhtml = "".join(
        f"<div class='cell'><div class='k'>{k}</div><div class='v'>{v}</div></div>"
        for k, v in cells)
    donor = (" · organ donor" if (p.get("organ_donor") or "") == "Yes" else "")
    st.markdown(
        f"<div class='idcard'>"
        f"<div class='brandline'>{ui.mono_mark()} MedVault · emergency card</div>"
        f"<div class='who'>{name}</div>"
        f"<div class='sub'>{p.get('conditions') or 'No conditions recorded'}{donor}</div>"
        f"<div class='grid'>{cellhtml}</div></div>", unsafe_allow_html=True)

    # Allergies get their own red band rather than a cell, because this is the one line on
    # the screen that can kill someone if it is skimmed past.
    allergies = (p.get("allergies") or "").strip()
    st.markdown(
        f"<div class='alert'><div class='k'>Allergies</div><div class='v'>"
        f"{allergies or 'None recorded — add them, this is the line staff look for first.'}"
        f"</div></div>", unsafe_allow_html=True)

    if p.get("emergency_name"):
        st.markdown(ui.section("In an emergency, call"), unsafe_allow_html=True)
        rel = f" · {p['emergency_relation']}" if p.get("emergency_relation") else ""
        st.markdown(f"<div class='med'><div class='n'>{p['emergency_name']}{rel}</div>"
                    f"<div class='d'>{p.get('emergency_phone') or 'no number on file'}</div>"
                    f"</div>", unsafe_allow_html=True)

    if p.get("insurer") or p.get("member_id"):
        st.markdown(ui.section("Insurance"), unsafe_allow_html=True)
        st.markdown(f"<div class='med'><div class='n'>{p.get('insurer') or 'Insurer not set'}"
                    f"</div><div class='d'>Member ID "
                    f"<b>{p.get('member_id') or 'not set'}</b></div></div>",
                    unsafe_allow_html=True)

    if p.get("gp_name"):
        st.markdown(ui.section("Primary doctor"), unsafe_allow_html=True)
        st.markdown(f"<div class='med'><div class='n'>{p['gp_name']}</div>"
                    f"<div class='d'>{p.get('gp_phone') or 'no number on file'}</div></div>",
                    unsafe_allow_html=True)

    st.markdown(ui.section(f"Taking now · {len(meds)}"), unsafe_allow_html=True)
    if not meds:
        st.markdown(ui.empty("No current medicines.<br>Add a prescription and they appear here."),
                    unsafe_allow_html=True)
    for m in meds[:6]:
        bits = " · ".join(x for x in (m.get("dose"), m.get("frequency")) if x)
        st.markdown(f"<div class='med'><div class='n'>{m['name']}</div>"
                    f"<div class='d'>{bits or 'no dose recorded'}</div>"
                    + (f"<div class='why'>{m['reason']}</div>" if m.get("reason") else "")
                    + "</div>", unsafe_allow_html=True)

    if not gaps:
        profile_editor(p, expanded=False)


def screen_add():
    """Upload a document, let it be read, confirm what was read, file it."""
    ok, why = reader_ready()
    st.markdown(ui.section("Add a document"), unsafe_allow_html=True)
    st.caption("A photo of a prescription, a lab report PDF, a discharge summary — "
               "whatever you were handed. It is read once to pull out the details.")

    up = st.file_uploader("Photo or PDF", type=["jpg", "jpeg", "png", "webp", "pdf"],
                          label_visibility="collapsed")
    if not up:
        st.markdown(ui.empty("Nothing uploaded yet.<br>"
                             "On a phone this opens your camera."), unsafe_allow_html=True)
        return

    data = up.getvalue()
    is_pdf = (up.type or "").endswith("pdf") or up.name.lower().endswith(".pdf")
    st.caption(f"{up.name} · {len(data)/1024:,.0f} KB")

    if not ok:
        st.error(f"**This document cannot be read yet**\n\nThe reader is not set up — {why}. "
                 f"Your file has not been stored anywhere.")
        return

    if st.button("Read this document", type="primary", use_container_width=True):
        from extract import read_document, pdf_text
        with st.status("Reading…", expanded=False) as status:
            text, note = (None, None)
            if is_pdf:
                import io as _io
                text, note = pdf_text(_io.BytesIO(data))
            if is_pdf and text:
                status.write(f"Read the text layer · {note}")
                rec, meta = read_document(text=text)
            else:
                status.write("Looking at the page…")
                rec, meta = read_document(image=(up.type or "image/jpeg", data))
            status.update(label="Read", state="complete")

        if not meta.get("ok"):
            st.error("**That document could not be read just now**\n\nThe reading service "
                     "did not answer. Nothing was stored. Try again in a moment.")
            st.caption(f"For the maintainer: {str(meta.get('error'))[:160]}")
            return

        st.session_state["draft"] = rec
        st.session_state["draft_file"] = (up.name, up.type, data)
        st.session_state["draft_model"] = meta.get("model")

    draft = st.session_state.get("draft")
    if not draft:
        return

    st.markdown(ui.section("Check this before filing"), unsafe_allow_html=True)
    st.caption("Read off the page by a model. Correct anything it got wrong — it is your "
               "record, and a wrong dose is worse than no dose.")
    c1, c2 = st.columns(2)
    kind = c1.selectbox("Type", KIND_ORDER, index=KIND_ORDER.index(draft["kind"]),
                        format_func=kind_label)
    sdate = c2.text_input("Date on the document", draft.get("service_date") or "",
                          placeholder="not printed")
    title = st.text_input("Title", draft.get("title") or "")
    provider = st.text_input("Hospital or doctor", draft.get("provider") or "")
    summary = st.text_area("Summary", draft.get("summary") or "", height=90)

    meds = draft.get("medications") or []
    if meds:
        st.markdown(ui.section(f"Medicines found · {len(meds)}"), unsafe_allow_html=True)
        for m in meds:
            bits = " · ".join(x for x in (m.get("dose"), m.get("frequency"), m.get("duration")) if x)
            st.markdown(f"<div class='med'><div class='n'>{m['name']}</div>"
                        f"<div class='d'>{bits or 'no dose printed'}</div></div>",
                        unsafe_allow_html=True)

    if st.button("File it", type="primary", use_container_width=True):
        fname, fmime, fbytes = st.session_state["draft_file"]
        filer = me()
        clinical = accounts.is_verified_clinician(filer)
        rid = db.add_record(con, kind=kind, title=title or "Untitled record",
                            service_date=sdate or None, provider=provider or None,
                            summary=summary or None, file_name=fname, file_mime=fmime,
                            file_bytes=fbytes, read_by=st.session_state.get("draft_model"),
                            provenance="CLINICAL" if clinical else "SELF",
                            owner_id=filer.get("id"),
                            verified_by=filer.get("id") if clinical else None)
        for m in meds:
            db.add_medication(con, rid, m)
        for k in ("draft", "draft_file", "draft_model"):
            st.session_state.pop(k, None)
        st.success(f"Filed. {len(meds)} medicine(s) added." if meds else "Filed.")
        st.rerun()


def screen_records():
    st.markdown(ui.section("Everything you have filed"), unsafe_allow_html=True)
    q = st.text_input("Search", placeholder="tinnitus, amoxicillin, Lahey…",
                      label_visibility="collapsed")
    counts = db.counts_by_kind(con, None if clinician_view() else my_id())
    options = ["all"] + [k for k in KIND_ORDER if counts.get(k)]
    kind = st.selectbox("Type", options, label_visibility="collapsed",
                        format_func=lambda k: ("Everything" if k == "all"
                                               else f"{kind_label(k)} ({counts.get(k,0)})"))
    rows = db.list_records(con, kind=None if kind == "all" else kind, query=q or None,
                           owner_id=None if clinician_view() else my_id())

    if not rows:
        st.markdown(ui.empty("Nothing here yet." if not q else f"Nothing matches “{q}”."),
                    unsafe_allow_html=True)
        return

    for r in rows:
        st.markdown(
            f"<div class='rec'><div class='top'>"
            f"<span class='pill'>{kind_label(r['kind'])}</span>"
            f"{ui.provenance_badge(r)}"
            f"<span class='when'>{when(r)}</span></div>"
            f"<div class='title'>{r['title']}</div>"
            + (f"<div class='who'>{r['provider']}</div>" if r.get("provider") else "")
            + (f"<div class='sum'>{r['summary']}</div>" if r.get("summary") else "")
            + f"<div class='provwhy'>{accounts.PROVENANCE.get(r.get('provenance') or 'SELF', accounts.PROVENANCE['SELF'])[1]}</div>"
            + ("" if r.get("file_size") else
               "<div class='nofile'>No original attached</div>")
            + "</div>", unsafe_allow_html=True)
        if r.get("file_size"):
            full = db.get_record(con, r["id"])
            st.download_button("Open the original", data=full["file_bytes"],
                               file_name=full["file_name"] or "record",
                               mime=full["file_mime"] or "application/octet-stream",
                               key=f"dl{r['id']}", use_container_width=True)


def screen_today():
    """The Scheduler on screen: what is due today, and a calendar that rings without us.

    Streamlit cannot wake a phone, and a reminder that only works while this tab is open is
    not a reminder. So the thing that actually reminds is the calendar file: imported once,
    it rings from the phone's own calendar whether or not anyone opens MedVault again.
    """
    profile = db.get_profile(con, my_id())
    day_start = profile.get("day_start") or schedule.DEFAULT_DAY_START
    meds = db.list_medications(con, active_only=True, owner_id=my_id())
    day = schedule.plan(meds, day_start=day_start)

    st.markdown(ui.section(f"Today · {len(day['doses'])} dose(s)"), unsafe_allow_html=True)
    if not meds:
        st.markdown(ui.empty("Nothing to take.<br>Medicines appear here once a "
                             "prescription is filed."), unsafe_allow_html=True)
        return

    coming = schedule.next_due(day)
    if coming:
        st.markdown(f"<div class='hit ok'><span class='amt'>{coming['at']}</span>"
                    f"<div class='h'>Next: {coming['med']['name']}</div>"
                    f"<div class='b'>{coming['med'].get('dose') or 'as prescribed'}"
                    + (f" · {schedule.note(coming['parsed'])}"
                       if schedule.note(coming["parsed"]) else "")
                    + "</div></div>", unsafe_allow_html=True)

    for dose in day["doses"]:
        extra = schedule.note(dose["parsed"])
        ends = (f" · last dose {dose['ends']:%-d %b}" if dose["ends"] else "")
        st.markdown(f"<div class='med'><div class='n'>{dose['at']} · {dose['med']['name']}"
                    f"</div><div class='d'>{dose['med'].get('dose') or 'as prescribed'}"
                    + (f" · {extra}" if extra else "") + ends + "</div></div>",
                    unsafe_allow_html=True)

    # The groups that are deliberately NOT on a clock, each said out loud rather than
    # dropped. Silently omitting a medicine from a reminder list looks like "nothing to
    # take", which for the as-needed ones is fine and for the unreadable ones is not.
    if day["as_needed"]:
        st.markdown(ui.section("Only when you need it — no alarm"), unsafe_allow_html=True)
        for e in day["as_needed"]:
            gap = (f"Not more often than every {e['parsed']['every_hours']} hours."
                   if e["parsed"]["every_hours"] else "Follow the label for how often.")
            st.markdown(f"<div class='med'><div class='n'>{e['med']['name']}</div>"
                        f"<div class='d'>{e['med'].get('dose') or ''} · {gap}</div>"
                        f"<div class='why'>Prescribed as needed, so it is not scheduled. "
                        f"Taking it on a timetable is not what the prescription says.</div>"
                        f"</div>", unsafe_allow_html=True)
    if day["weekly"]:
        st.markdown(ui.section("Weekly"), unsafe_allow_html=True)
        for e in day["weekly"]:
            st.markdown(f"<div class='med'><div class='n'>{e['med']['name']}</div>"
                        f"<div class='d'>{e['parsed']['text']} — pick the day with your "
                        f"pharmacist; it is not on the daily calendar.</div></div>",
                        unsafe_allow_html=True)
    if day["unreadable"]:
        st.markdown(ui.section("Could not be timed"), unsafe_allow_html=True)
        for e in day["unreadable"]:
            st.markdown(f"<div class='hit warn'><div class='h'>{e['med']['name']}</div>"
                        f"<div class='b'>The prescription says "
                        f"“{e['parsed']['text'] or 'nothing about how often'}”, which "
                        f"does not say when. Ask the pharmacist rather than guessing — "
                        f"this is not on your calendar.</div></div>",
                        unsafe_allow_html=True)
    if day["finished"]:
        st.caption("Finished courses not shown: "
                   + ", ".join(f"{e['med']['name']} (last dose {e['ends']:%-d %b})"
                               for e in day["finished"])
                   + ". Switch them off below so your card is right.")

    st.caption("Times are a suggestion from MedVault, not part of the prescription — a "
               "prescription that says “twice daily” says how often, not when. They move "
               "with the time your day starts.")
    with st.form("daystart", border=False):
        chosen = st.time_input("My day starts at",
                               value=datetime.time.fromisoformat(day_start), step=900)
        if st.form_submit_button("Move my times", use_container_width=True):
            db.save_profile(con, my_id(), {"day_start": chosen.strftime("%H:%M")})
            st.rerun()

    if day["doses"]:
        st.download_button(
            "Add these reminders to my phone's calendar",
            data=schedule.calendar(day, account_label=me().get("display_name") or "MedVault"),
            file_name="medvault-reminders.ics", mime="text/calendar",
            use_container_width=True, type="primary")
        st.caption("Open the file on your phone and it rings from your own calendar — "
                   "MedVault does not need to be open. As-needed medicines are not in it.")


def screen_medicines():
    screen_today()
    meds = db.list_medications(con, active_only=False, owner_id=my_id())
    st.markdown(ui.section(f"Medicines · {len(meds)}"), unsafe_allow_html=True)
    if not meds:
        st.markdown(ui.empty("No medicines yet.<br>They are pulled out of prescriptions "
                             "automatically when you file one."), unsafe_allow_html=True)
        return
    for m in meds:
        bits = " · ".join(x for x in (m.get("dose"), m.get("frequency"), m.get("duration")) if x)
        src = f"{m.get('provider') or 'unknown'} · {m.get('service_date') or 'no date'}"
        st.markdown(f"<div class='med'><div class='n'>{m['name']}</div>"
                    f"<div class='d'>{bits or 'no dose recorded'}</div>"
                    + (f"<div class='why'>{m['reason']}</div>" if m.get("reason") else "")
                    + f"<div class='why'>From {src}</div></div>", unsafe_allow_html=True)


def screen_check():
    """The reason this app and a bill checker belong to the same person."""
    st.markdown(ui.section("Check a bill against your records"), unsafe_allow_html=True)
    st.caption("A price check asks whether a charge was the right amount. This asks "
               "something a price list cannot: does your own paperwork show it happened?")

    records = db.list_records(con, limit=2000, owner_id=my_id())
    if not records:
        st.markdown(ui.empty("File a few records first.<br>"
                             "With an empty vault there is nothing to check a bill against."),
                    unsafe_allow_html=True)
        return

    st.info(f"Checking against **{len(records)} record(s)** you have filed.")

    # Pasting was the only way in, which meant retyping a bill that arrived as a PDF or
    # sits on the kitchen table. A photo is how a patient actually has this document.
    how = st.radio("Where is the bill?", ["Photograph or PDF", "Paste the lines"],
                   horizontal=True, label_visibility="collapsed", key="bill_source")

    pasted, upload = "", None
    if how == "Paste the lines":
        pasted = st.text_area(
            "Paste the bill's lines", height=150,
            placeholder="2026-03-14  70450  CT HEAD/BRAIN WO CONTRAST   1   3,100.00")
        st.caption("One line per charge: a date, a description and an amount.")
    else:
        upload = st.file_uploader("Photo or PDF of the bill",
                                  type=["jpg", "jpeg", "png", "webp", "pdf"],
                                  label_visibility="collapsed", key="bill_file")
        st.caption("On a phone this opens the camera. The bill is read once to pull out "
                   "the codes, quantities and amounts. It is not stored unless you file it "
                   "as a record from the Add screen.")
        if upload:
            st.caption(f"{upload.name} · {len(upload.getvalue())/1024:,.0f} KB")

    # A few questions about the patient's situation unlock protections worth far more than
    # any rate difference on the bill - and none of them need a price file to answer.
    with st.expander("Four questions that may be worth more than the prices"):
        st.caption("Federal law gives patients rights that depend on the situation, not on "
                   "the amounts. Leave anything blank that you are not sure of — unanswered "
                   "is treated as unknown, never as no.")
        cov = st.radio("Were you insured for this care?",
                       ["Not sure", "I have insurance", "Uninsured or self-pay"],
                       key="rt_cov")
        c1, c2 = st.columns(2)
        emg = c1.selectbox("Was it emergency care?", ["Not sure", "Yes", "No"], key="rt_emg")
        npf = c2.selectbox("Is the hospital non-profit?", ["Not sure", "Yes", "No"],
                           key="rt_npf")
        inn = st.selectbox("Was the hospital itself in your network?",
                           ["Not sure", "Yes", "No"], key="rt_inn")
        gfe_raw = st.text_input("If you were given a written estimate, what did it say?",
                                placeholder="e.g. 1200.00", key="rt_gfe")

    # Pricing a bill needs to know whose published file to price it against.
    import checker
    @st.cache_resource
    def price_table():
        return checker.load_reference()

    known = sorted({h for h, _ in price_table()})
    pretty = {h: h.title() for h in known}
    hospital = st.selectbox(
        "Which hospital issued this bill?", ["— not listed —"] + known,
        format_func=lambda h: h if h.startswith("—") else pretty[h], key="bill_hosp")
    st.caption("Nine hospitals have published price files collected for this project. "
               "If yours is not one of them, leave it unset — every line is still checked "
               "against the national Medicare allowance, which covers any CPT code.")

    ready = bool(pasted.strip()) or upload is not None
    if not st.button("Check it", type="primary", use_container_width=True) or not ready:
        return

    import re as _re
    import crosscheck
    from codes import find_code

    def reject_if_not_itemised(rows):
        """A statement with no billing codes cannot be checked against anything.

        Itemized rejected these before the Checker ever saw them, which is why a latent
        defect in its duplicate rule never surfaced there: two lines with an empty code
        match each other and are reported as the same code billed twice. Guarding at the
        boundary fixes the behaviour and leaves checker.py byte-identical to the module
        that produced the Assignment 4 figures.
        """
        if rows and not any((r.get("code") or "").strip() for r in rows):
            st.error("**No billing codes found**\n\nEvery line of an itemised bill carries "
                     "a procedure code, like 74177 or J1885. None were found here — this "
                     "may be a summary statement rather than an itemised one. Ask the "
                     "hospital for the itemised version; you cannot check what you cannot "
                     "see.")
            return True
        return False

    lines = []
    if upload is not None:
        ok, why = reader_ready()
        if not ok:
            st.error(f"**This bill cannot be read here**\n\nThe reader is not set up — "
                     f"{why}. Paste the lines instead and everything else still works.")
            return
        from extract import read_bill_verified, pdf_text
        data = upload.getvalue()
        is_pdf = (upload.type or "").endswith("pdf") or upload.name.lower().endswith(".pdf")
        with st.status("Reading the bill…", expanded=False) as status:
            text = None
            if is_pdf:
                import io as _io
                text, note = pdf_text(_io.BytesIO(data))
                if text:
                    status.write(f"Read the text layer · {note}")
            if not text:
                status.write("Looking at the page…")
            lines, meta = (read_bill_verified(text=text) if text
                           else read_bill_verified(
                               image=(upload.type or "image/jpeg", data)))
            if meta.get("attempts", 1) > 1:
                status.write(f"Read again to check it added up ({meta['attempts']} passes)")
            status.update(label="Read", state="complete")

        if not meta.get("ok"):
            st.error("**That bill could not be read just now**\n\nThe reading service did "
                     "not answer. Nothing was stored. Paste the lines instead, or try again "
                     "in a moment.")
            st.caption(f"For the maintainer: {str(meta.get('error'))[:160]}")
            return
        if not lines:
            st.error("**No charges could be read from that bill**\n\nEvery line of an "
                     "itemised bill carries a code, a quantity and an amount. None were "
                     "found — this may be a summary rather than an itemised statement. Ask "
                     "the hospital for the itemised version.")
            return
        read_total = sum(l["charged"] for l in lines)
        who = f" · read by {meta['provider']}" if meta.get("provider") else ""
        if meta.get("reconciled") is True:
            st.success(f"Read **{len(lines)} charge(s)** totalling **${read_total:,.2f}**"
                       + (f" from {meta['hospital']}" if meta.get("hospital") else "")
                       + f" — and they add up to the total printed on the bill.{who}")
        else:
            # Never show a number from an unverified read without saying so. A truncated
            # read looks exactly like a short bill.
            st.warning(
                f"**Read {len(lines)} charge(s) totalling ${read_total:,.2f}, but could "
                f"not confirm that against a printed total.**\n\nCheck the list below "
                f"against the bill in your hand before trusting anything underneath it — "
                f"if a line is missing, the figures will be too low.")
        with st.expander("Check what was read",
                         expanded=meta.get("reconciled") is not True):
            for l in lines:
                st.markdown(f"<div class='rec'><div class='top'>"
                            f"<span class='pill'>{l['code'] or 'no code'}</span>"
                            f"<span class='when'>{l['service_date'] or 'no date'}</span></div>"
                            f"<div class='title'>${l['charged']:,.2f}</div>"
                            f"<div class='who'>{l['description']} · qty {l['units']}</div>"
                            f"</div>", unsafe_allow_html=True)
    else:
        lines = paste.lines(pasted)

    if reject_if_not_itemised(lines):
        return

    # ---- what the law may already give you, before any price is compared -------
    import rights, billchecks
    tri = {"Not sure": None, "Yes": True, "No": False}
    try:
        gfe_val = float((gfe_raw or "").replace("$", "").replace(",", "").strip() or 0) or None
    except ValueError:
        gfe_val = None
    ctx = rights.context(
        coverage={"I have insurance": "insured",
                  "Uninsured or self-pay": "self_pay"}.get(cov, rights.UNKNOWN),
        emergency=tri[emg], nonprofit_hospital=tri[npf], in_network_facility=tri[inn],
        gfe_amount=gfe_val)
    bill_total = round(sum(float(l.get("charged") or 0) for l in lines), 2)
    protections = rights.evaluate(lines, bill_total, ctx)

    if protections:
        st.markdown(ui.section(f"What the law may already give you · {len(protections)}"),
                    unsafe_allow_html=True)
        for f in protections:
            tone = "bad" if f["severity"] == "high" else "warn"
            st.markdown(f"<div class='hit {tone}'><div class='h'>{f['title']}</div>"
                        f"<div class='b'>{f['means']}<br><br><b>What to do:</b> {f['todo']}"
                        f"<br><span style='opacity:.7'>{f['source']}</span></div></div>",
                        unsafe_allow_html=True)

    still_open = rights.unanswered(ctx)
    if still_open:
        st.caption("Not checked, because you have not said: " + ", ".join(still_open)
                   + ". That is not the same as having no protection.")

    # ---- things wrong with the bill on its own face ----------------------------
    face = billchecks.run(lines)
    if face:
        st.markdown(ui.section(f"Wrong on the bill's own face · {len(face)}"),
                    unsafe_allow_html=True)
        for _, f in face:
            st.markdown(f"<div class='hit warn'><div class='h'>{f['title']}</div>"
                        f"<div class='b'>{f['detail']}<br><br><b>Ask:</b> {f['ask']}</div>"
                        f"</div>", unsafe_allow_html=True)

    # ---- the national benchmark, which works for any CPT code ------------------
    # The 262-row table covers nine hospitals. This covers every CPT code there is, so a
    # bill from anywhere gets an answer to "is this the right amount" rather than silence.
    import medicare
    bench = medicare.lookup_many([l.get("code") for l in lines])
    named = {c: b for c, b in bench.items() if b.get("found")}

    if named:
        st.markdown(ui.section("Against the national Medicare allowance"),
                    unsafe_allow_html=True)
        st.caption("What the federal programme allows for the same code. **A Medicare rate "
                   "is not a price cap** — a hospital may charge a commercial patient more, "
                   "and usually does. This is context for the conversation, not evidence of "
                   "an overcharge.")
        rows = []
        for l in lines:
            b = named.get((l.get("code") or "").upper())
            if not b or not b.get("medicare_rate"):
                continue
            mult = medicare.multiple_of_medicare(l.get("charged"), l.get("units"),
                                                 b["medicare_rate"])
            rows.append((mult or 0, l, b, mult))
        for _, l, b, mult in sorted(rows, key=lambda t: -t[0]):
            tone = "bad" if (mult or 0) >= 10 else "warn" if (mult or 0) >= 3 else "ok"
            times = (f"<b>{mult:g}× the Medicare allowance</b>" if mult
                     else "could not be compared")
            st.markdown(
                f"<div class='hit {tone}'><span class='amt'>{_m(l.get('charged'))}</span>"
                f"<div class='h'>{b['name']}</div><div class='b'>"
                f"<b>{l.get('code')}</b> · billed as “{(l.get('description') or '')[:40]}”"
                f"{f' · qty {l["units"]}' if (l.get('units') or 1) > 1 else ''}<br>"
                f"Medicare allows {_m(b['medicare_rate'])}"
                f"{f' per unit' if (l.get('units') or 1) > 1 else ''} — {times}."
                + f"<br><span style='opacity:.65'>Source: CMS "
                  f"{str(b.get('dataset','')).replace('CMS_','').replace('_',' ')}, "
                  f"{b.get('effective_year','')}</span></div></div>",
                unsafe_allow_html=True)

        missing = [c for c, b in bench.items() if not b.get("found")]
        if missing:
            st.caption(f"{len(missing)} code(s) are not in the national fee schedule and "
                       f"could not be benchmarked: {', '.join(sorted(missing))}. It covers "
                       f"CPT; HCPCS codes such as J- and A-codes are outside it.")

    # ---- what this particular hospital publishes -------------------------------
    if hospital != "— not listed —":
        # The table is keyed on a lowercased name; the letter must not be addressed to it.
        priced = checker.check_bill(
            {"hospital_name": pretty.get(hospital, hospital),
             "line_items": [{"code": l.get("code") or "", "description": l["description"],
                             "units": l.get("units") or 1, "charged": l["charged"]}
                            for l in lines]},
            price_table())

        c1, c2, c3 = st.columns(3)
        c1.metric("You were billed", f"${priced['billed_total']:,.2f}")
        c2.metric("They publish", f"${priced['posted_total']:,.2f}")
        c3.metric("Unexplained", f"${priced['questionable_amount']:,.2f}")
        # The date was hardcoded here. The table carries collected_date on every row, so
        # the caption reads it: a refreshed table moves this line instead of silently
        # leaving a stale date on screen.
        collected = sorted({l["collected_date"] for l in priced["lines"]
                            if l.get("collected_date")})
        when = (" · ".join(_date(d) for d in collected) if collected
                else "an undated table")
        st.caption("A gap to ask about — not money you are owed, and not a refund "
                   f"estimate. Published prices collected {when}; a hospital may have "
                   "republished since.")

        # Attached to every flag since the Checker was written and never shown until now.
        # The PRD promised it as what this screen says when a price file cannot settle a
        # line: how often CMS has already had to act against this hospital.
        #
        # Three states, not two. A hospital the enforcement file was never joined to is
        # not a hospital with a clean record, and saying "0 actions" for one would be the
        # same mistake this app refuses to make about a missing medical record.
        matched = next((l.get("enforcement_match") for l in priced["lines"]
                        if l.get("enforcement_match")), "none")
        actions = max((l.get("hospital_enforcement_actions") or 0)
                      for l in priced["lines"]) if priced["lines"] else 0
        if matched == "none":
            st.caption("This hospital could not be matched to CMS's price-transparency "
                       "enforcement file by name and state, so this project holds no "
                       "enforcement history for it. **That is not the same as a clean "
                       "record** — it usually means CMS lists the hospital under a "
                       "slightly different name.")
        elif actions:
            st.caption(f"CMS has recorded **{actions} price-transparency enforcement "
                       f"action(s)** against this hospital. That is about whether it "
                       f"published properly, not about your bill — but it is context for "
                       f"how much weight the file above deserves.")
        else:
            st.caption("CMS has recorded no price-transparency enforcement actions "
                       "against this hospital.")

        flagged_lines = [l for l in priced["lines"] if l["verdict"] != "VERIFIED"]
        if flagged_lines:
            # "Above the published price" was wrong as a heading: this section also
            # carries duplicates, suspect quantities and codes with no published price.
            st.markdown(ui.section(f"Checked against the published prices · "
                                   f"{len(flagged_lines)} flagged"),
                        unsafe_allow_html=True)
            for l in sorted(flagged_lines, key=lambda x: -(x.get("charged") or 0)):
                label, tone = VERDICTS.get(l["verdict"], ("Checked", "warn"))
                over = (f" · <b>{_m(l['amount_over'])} above</b>"
                        if l.get("amount_over") else "")
                # The Checker leaves posted_price empty on a duplicate row - the price
                # is on the first instance of that code. Saying "no published price"
                # because this particular row lacks one told the reader the hospital
                # publishes nothing for 99284 while the row above it showed $1,605.00.
                price = l.get("posted_price")
                if price is None and l.get("code"):
                    price = next((o.get("posted_price") for o in priced["lines"]
                                  if o.get("code") == l["code"] and o.get("posted_price")),
                                 None)
                posted = (f"They publish {_m(price)} for this code" if price else
                          "No published price for this code — worth asking about")
                # The receipt, on the card rather than only in the letter: which of the
                # hospital's three published numbers this was compared against, and when
                # that file was collected.
                cite = (f"<br><span style='opacity:.65'>Compared against their "
                        f"{l['basis']}, collected {_date(l['collected_date'])}</span>"
                        if l.get("basis") and l.get("collected_date") else "")
                st.markdown(
                    f"<div class='hit {tone}'><span class='amt'>{_m(l['charged'])}</span>"
                    f"<div class='h'>{label}</div><div class='b'>"
                    f"<b>{l.get('code') or '—'}</b> {l.get('description','')[:48]} · "
                    f"qty {l.get('units',1)}<br>{posted}{over}{cite}</div></div>",
                    unsafe_allow_html=True)

        st.session_state["priced"] = priced

    checked, summary = crosscheck.check_bill(lines, records)
    st.session_state["findings"] = {"priced": st.session_state.get("priced"),
                                    "rights": protections, "face": [f for _, f in face],
                                    "crosschecked": checked}

    # A bill with no dates on it produced one identical "no date to check against" card per
    # line, under a heading that said nothing was found - four cards saying the same thing
    # beneath "0 of 4". When nothing is dated, that is one fact about the bill, not N.
    undated = [r for r in checked if r["verdict"] == "UNDATED"]
    if len(undated) == len(checked) and checked:
        st.markdown(ui.section("Against your records"), unsafe_allow_html=True)
        st.markdown(
            "<div class='hit warn'><div class='h'>No dates on this bill to check against"
            "</div><div class='b'>None of these lines carries a service date, so none of "
            "them can be matched to your records. Ask the billing office for a statement "
            "with dates — it is the single thing that makes the rest of this checkable."
            "</div></div>", unsafe_allow_html=True)
    else:
        worth_showing = [r for r in checked if r["verdict"] != "UNDATED"]
        st.markdown(ui.section(f"{summary['unsupported']} of {summary['lines']} lines "
                               "have nothing behind them"), unsafe_allow_html=True)
        if undated:
            st.caption(f"{len(undated)} line(s) carry no date and could not be checked "
                       f"either.")
        # Grouped by verdict and date. "You have records from 14 Mar 2026 (Basic metabolic
        # panel, Chest X-ray) and none of them mentions it" is a fact about that day, not
        # about each line - printed per card it filled the screen with four copies of the
        # same sentence and buried the one thing that differed, which is the line itself.
        groups = {}
        for r in worth_showing:
            groups.setdefault((r["verdict"], r.get("service_date")), []).append(r)

        for (verdict, when_), rows in groups.items():
            label, tone = crosscheck.VERDICTS[verdict]
            head = f"{label}{f' · {when_}' if when_ else ''}"
            if verdict == "DATE_NO_MATCH" and rows[0].get("matches"):
                held = ", ".join(f"“{m['title']}”" for m in rows[0]["matches"][:3])
                why = (f"You have {len(rows[0]['matches'])} record(s) from that day "
                       f"({held}) and none of them covers the charge"
                       f"{'s' if len(rows) > 1 else ''} below.")
            elif verdict == "NO_RECORD":
                gap = rows[0].get("nearest_days")
                why = ("You have filed nothing from that date"
                       + (f" — your closest record is {gap} days away" if gap else "")
                       + ". That may simply be paperwork you never received.")
            else:
                why = rows[0]["ask"]

            body = "".join(
                f"<div class='b' style='margin-top:.45rem'>"
                f"<span class='amt'>${r['charged']:,.2f}</span>"
                + " · ".join(filter(None, [
                    f"<b>{r['code']}</b>" if r.get("code") else None,
                    (r.get("description") or "")[:46] or None]))
                + "</div>" for r in rows)

            st.markdown(f"<div class='hit {tone}'><div class='h'>{head}</div>"
                        f"<div class='b'>{why}</div>{body}</div>",
                        unsafe_allow_html=True)
    st.markdown(f"<div class='note'>{summary['caveat']}</div>", unsafe_allow_html=True)

    # ---- the letter --------------------------------------------------------
    priced = st.session_state.get("priced")
    if priced and priced.get("flagged_count"):
        import dispute
        prof = db.get_profile(con, my_id())
        text = dispute.letter(priced, patient_name=prof.get("full_name"),
                              rights_findings=protections,
                              record_gaps=[c for c in checked
                                           if c["verdict"] in ("NO_RECORD", "DATE_NO_MATCH")])
        st.markdown(ui.section("A letter you can send"), unsafe_allow_html=True)
        st.caption("Built from the figures above directly — not written by a model, so "
                   "nothing in it can drift from what this screen showed you.")
        with st.expander("Read it"):
            st.text(text)
        st.download_button("Download the letter", data=text,
                           file_name="medvault-dispute-letter.txt",
                           use_container_width=True)

    # ---- ask about any of it ----------------------------------------------
    st.markdown(ui.section("Ask about this bill"), unsafe_allow_html=True)
    st.caption("Answers come out of the findings above, not out of a language model — so "
               "it can only tell you things the checks actually established, and it says "
               "when it does not know.")
    question = st.text_input("Ask", key="ask_q", label_visibility="collapsed",
                             placeholder="why is 72148 flagged?  ·  what do I do next?")
    if question:
        import explain
        st.markdown(explain.answer(question, st.session_state.get("findings") or {}))




# ------------------------------------------------------------ who you are ----

EXAMPLE_QUESTIONS = [
    "What is each of my medicines for?",
    "What did my last scan find?",
    "Why am I taking two antibiotics?",
]


def _render_turn(turn):
    """One question and its answer, with the badge that says where the answer came from."""
    st.markdown(f"<div class='qa'><div class='bubble q'>{turn['q']}</div>",
                unsafe_allow_html=True)
    a = turn["a"]
    if a.get("kind") == "error":
        st.markdown("<div class='bubble a'><span class='badge bad'>Could not answer</span>"
                    "<div>The reader did not respond. Nothing was made up to fill the "
                    "gap.</div></div></div>", unsafe_allow_html=True)
        st.caption(f"Reader said: {a.get('error')}")
        return

    label, tone = ask.KIND_LABEL.get(a["kind"], ("Answer", "warn")) \
        if a["kind"] != "emergency" else ("Call for help now", "bad")
    body = "".join(f"<p>{para}</p>" for para in a["answer"].split("\n") if para.strip())
    srcs = ""
    if a.get("sources"):
        items = " · ".join(
            f"<b>{r.get('title')}</b> ({r.get('service_date') or 'undated'})"
            for r in a["sources"].values())
        srcs = f"<div class='srcs'>Read out of: {items}</div>"
    st.markdown(f"<div class='bubble a'><span class='badge {tone}'>{label}</span>"
                f"{body}{srcs}</div></div>", unsafe_allow_html=True)


def screen_ask():
    """A bot for the paperwork, with the checkable things checked before it is asked."""
    findings = ask.brief(con, my_id())
    st.markdown(ui.section(f"What your own records already show · {len(findings)}"),
                unsafe_allow_html=True)
    st.caption("These are worked out here, from your records, by arithmetic — no model is "
               "involved and nothing leaves this server to produce them.")
    if not findings:
        st.markdown(ui.empty("Nothing to flag.<br>No duplicate medicines, no finished "
                             "course still marked as current, nothing that collides with "
                             "your recorded allergies."), unsafe_allow_html=True)
    for f in findings:
        st.markdown(f"<div class='hit {f['tone']}'><div class='h'>{f['title']}</div>"
                    f"<div class='b'>{f['body']}</div></div>", unsafe_allow_html=True)

    st.markdown(ui.section("Ask about your medicines and treatment"), unsafe_allow_html=True)
    ready, why = reader_ready()
    if not ready:
        st.info(f"The question box needs a reading key, and {why}. The checks above do "
                f"not — they are already complete.")
        return

    st.caption("It answers from the records in your vault, and says so when an answer is "
               "general knowledge instead. It will not tell you to change a dose, judge "
               "whether something is safe for you, or check drug interactions — it has no "
               "interaction database and will not pretend otherwise. **Your question and "
               "the text of your records are sent to the reader to answer it.**")

    log = st.session_state.setdefault("ask_log", [])
    for turn in log:
        _render_turn(turn)

    def run(question):
        with st.spinner("Reading your records…"):
            st.session_state["ask_log"].append(
                {"q": question, "a": ask.answer(con, my_id(), question)})
        st.rerun()

    with st.form("askform", border=False, clear_on_submit=True):
        q = st.text_input("Your question", key="ask_box", label_visibility="collapsed",
                          placeholder="what is the fluticasone for?")
        if st.form_submit_button("Ask", type="primary", use_container_width=True) and q:
            run(q)

    if not log:
        st.caption("Or start with one of these:")
        for col, example in zip(st.columns(len(EXAMPLE_QUESTIONS)), EXAMPLE_QUESTIONS):
            if col.button(example, key=f"ex{example[:12]}", use_container_width=True):
                run(example)
    elif st.button("Clear this conversation", use_container_width=True):
        st.session_state["ask_log"] = []
        st.rerun()



def screen_signin():
    """The landing page.

    Somebody arriving here is usually holding a bill they do not understand, and a login
    box on grey tells them nothing about what they would be logging in to. So the page
    says what the product does, shows the sign-in panel beside it rather than instead of
    it, and puts the caveats at the bottom in the same type as everything else.
    """
    st.markdown(landing.nav(), unsafe_allow_html=True)

    hero, panel = st.columns([1.05, 1], gap="large")
    with hero:
        st.markdown(landing.hero(), unsafe_allow_html=True)
    with panel:
        # st.container(border=True) is the only wrapper Streamlit will let a stylesheet
        # find reliably; the marker inside it is what the :has() selector keys on.
        with st.container(border=True):
            st.markdown("<div class='panelmark'></div>"
                        "<div class='panelhead'>Open your vault</div>"
                        "<div class='panelsub'>Patients and clinicians both sign in "
                        "here. A clinician is checked against the national provider "
                        "registry when the account is made.</div>",
                        unsafe_allow_html=True)
            auth_panel()

    st.markdown(ui.section("What it does"), unsafe_allow_html=True)
    for col, feature in zip(st.columns(3, gap="medium"), landing.FEATURES):
        col.markdown(landing.feature(*feature), unsafe_allow_html=True)

    st.markdown(ui.section("How it works"), unsafe_allow_html=True)
    st.markdown(landing.steps(), unsafe_allow_html=True)
    st.markdown(landing.footer(), unsafe_allow_html=True)


def auth_panel():
    """Two doors. The clinician one goes through the national provider registry."""
    # Deliberately a radio rather than st.tabs. The navigation bar is styled by selecting
    # every tab-list on the page, so a second group of tabs anywhere would be dragged to the
    # bottom of the screen wearing the wrong icons - which is exactly what happened here.
    # One tab group per app, and it is the navigation.
    mode = st.radio("Are you signing in or starting out?",
                    ["I have an account", "Create one"], horizontal=True,
                    label_visibility="collapsed", key="auth_mode")

    if mode == "I have an account":
        # st.form, not loose inputs: inside one, Enter submits. A sign-in screen where the
        # return key does nothing is the kind of thing nobody reports and everybody feels.
        with st.form("signin", border=False):
            email = st.text_input("Email", key="si_email")
            pw = st.text_input("Password", type="password", key="si_pw")
            if st.form_submit_button("Sign in", type="primary", use_container_width=True):
                acct, problem = accounts.sign_in(con, email, pw)
                if problem:
                    st.error(problem)
                else:
                    st.session_state["account"] = acct
                    st.rerun()

    else:
        # Order matters here, and the first version got it wrong. It ran
        # Email -> Password -> Name, and a plain text field sitting directly below a
        # password field reads as "confirm password" - that is where every other signup
        # form in the world puts one. The first person to use it typed their password into
        # the name box, and their account is still called it.
        #
        # Identity first, credentials last, and nothing at all after the password.
        role = st.radio("This account is for", ["patient", "clinician"], horizontal=True,
                        format_func=lambda r: "A patient" if r == "patient" else "A clinician",
                        key="su_role")

        st.markdown(ui.section("Who you are"), unsafe_allow_html=True)
        name2 = st.text_input("Your full name", key="su_name",
                              placeholder="Priya Sharma",
                              help="Shown on your health card.")

        record = None
        if role == "clinician":
            st.markdown(ui.section("Verify your NPI"), unsafe_allow_html=True)
            st.caption("Checked live against the CMS national provider registry. This "
                       "confirms the number is real, active and matches a licence — it "
                       "does not, on its own, prove you are that person.")
            npi_in = st.text_input("NPI number", key="su_npi", placeholder="10 digits")
            if st.button("Check the registry", use_container_width=True):
                found, problem = npi.lookup(npi_in)
                if problem:
                    st.error(problem)
                    st.session_state.pop("npi_record", None)
                else:
                    st.session_state["npi_record"] = found
            record = st.session_state.get("npi_record")
            if record:
                st.success(f"**{record['name'] or 'Registered organisation'}**"
                           f"{' · ' + record['credential'] if record['credential'] else ''}")
                st.markdown(
                    f"<div class='rec'><div class='title'>{record['specialty'] or '—'}</div>"
                    f"<div class='who'>Licence {record['license'] or '—'} "
                    f"{record['license_state'] or ''} · {record['city']}, {record['state']}"
                    f"</div></div>", unsafe_allow_html=True)

        st.markdown(ui.section("How you will sign in"), unsafe_allow_html=True)
        email2 = st.text_input("Email", key="su_email", placeholder="you@example.com")
        pw2 = st.text_input("Password", type="password", key="su_pw",
                            help="At least 8 characters. Nothing follows this field.")

        if st.button("Create account", type="primary", use_container_width=True):
            acct, problem = accounts.create(con, email=email2, password=pw2, role=role,
                                            display_name=name2, npi_record=record)
            if problem:
                st.error(problem)
            else:
                st.session_state["account"] = acct
                st.session_state.pop("npi_record", None)
                st.rerun()


def screen_review(account):
    """A clinician confirming that a record matches what they actually issued."""
    pending = db.pending_verification(con)
    st.markdown(ui.section(f"Waiting on you · {len(pending)}"), unsafe_allow_html=True)
    st.caption("Records a patient filed themselves. Confirming one means it matches what "
               "you issued — your NPI is attached to that claim, so only confirm what you "
               "actually recognise.")

    if not pending:
        st.markdown(ui.empty("Nothing waiting.<br>Every record here has been looked at."),
                    unsafe_allow_html=True)
        return

    for r in pending:
        st.markdown(
            f"<div class='rec'><div class='top'>"
            f"<span class='pill'>{kind_label(r['kind'])}</span>"
            f"{ui.provenance_badge(r)}"
            f"<span class='when'>{when(r)}</span></div>"
            f"<div class='title'>{r['title']}</div>"
            + (f"<div class='who'>{r['provider']}</div>" if r.get("provider") else "")
            + (f"<div class='sum'>{r['summary']}</div>" if r.get("summary") else "")
            + "</div>", unsafe_allow_html=True)
        if r.get("file_size"):
            full = db.get_record(con, r["id"])
            with st.expander("Look at the original"):
                if (full.get("file_mime") or "").startswith("image/"):
                    st.image(full["file_bytes"])
                else:
                    st.download_button("Open it", data=full["file_bytes"],
                                       file_name=full["file_name"] or "record",
                                       key=f"rv{r['id']}", use_container_width=True)
        c1, c2 = st.columns(2)
        if c1.button("Confirm", key=f"ok{r['id']}", type="primary", use_container_width=True):
            db.verify_record(con, r["id"], account["id"],
                             note=f"Confirmed by NPI {account.get('npi')}")
            st.rerun()
        if c2.button("Not mine", key=f"no{r['id']}", use_container_width=True):
            db.verify_record(con, r["id"], account["id"], note="reviewed")
            db.unverify_record(con, r["id"], note="Clinician did not recognise this record")
            st.rerun()



def hosted():
    """Whether this copy is running somewhere with a disk that does not survive a reboot.

    Streamlit Community Cloud restarts an app on inactivity and on every redeploy, and
    takes the SQLite file with it. For a bill checker that is annoying; for something
    called a vault it is a promise being broken quietly. So the app says so, in the place
    where somebody is looking at the records they would lose.
    """
    return bool(os.environ.get("MEDVAULT_HOSTED")) or "HOSTNAME" in os.environ and \
        os.environ.get("HOME", "").startswith("/home/appuser")


def vault_transfer(account):
    """Take your records out, and put them back. Both halves, or it is a trap."""
    st.markdown(ui.section("Your records, as a file"), unsafe_allow_html=True)
    # The warning is about the storage, not about being hosted. With a remote database
    # behind it the records do outlive a restart, and saying otherwise would be a caveat
    # that is no longer true - which costs as much trust as a missing one.
    if hosted() and not store.configured():
        st.warning("**This deployment's storage is temporary.** The server restarts when "
                   "it is idle and the database goes with it. Download your vault before "
                   "you close the tab, and put it back with the box below. Setting "
                   "`TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` in this app's secrets "
                   "moves it to a database that survives.")
    elif store.configured():
        st.success("**Your records are kept in a database, not on this server's disk.** "
                   "They survive a restart and a redeploy. Taking a copy is still worth "
                   "doing — a vault you cannot leave with is a trap.")
    st.caption("Everything except the original scans, as JSON small enough to email "
               "yourself. A vault that only takes deposits is a trap, so this goes both "
               "ways.")

    st.download_button("Download my vault",
                       data=db.export_vault(con, my_id()),
                       file_name=f"medvault-{time.strftime('%Y-%m-%d')}.json",
                       mime="application/json", use_container_width=True)

    back = st.file_uploader("Put a vault file back", type=["json"], key="vault_in")
    if back is not None and st.button("Restore it", use_container_width=True):
        try:
            done = db.import_vault(con, my_id(), back.getvalue())
        except (ValueError, json.JSONDecodeError) as problem:
            st.error(f"That file could not be read: {problem}")
        else:
            st.success(
                f"Restored {done['records_added']} record(s)"
                + (f", skipped {done['records_skipped']} already here"
                   if done["records_skipped"] else "")
                + f", {done['medications_added']} medicine(s)."
                + (" Your card was restored too." if done["profile_restored"] else ""))
            st.caption("Restored records are labelled as filed by you. A confirmation "
                       "from a clinician on another server does not travel with the file "
                       "— the account that gave it does not exist here.")
            st.rerun()


def sign_out():
    """At the foot of a screen, not in the navigation - leaving is not a place to go."""
    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
    if st.button("Sign out", use_container_width=True, key=f"out{id(st.session_state)}"):
        st.session_state.pop("account", None)
        st.rerun()

# ------------------------------------------------------------------ shell ----

account = st.session_state.get("account")
if not account:
    screen_signin()
    st.stop()

total = sum(db.counts_by_kind(con, None if accounts.is_verified_clinician(account)
                              else account["id"]).values())
st.markdown(ui.appbar(ui.signed_in_strip(
    account, meta=f"{total} record{'' if total == 1 else 's'}")), unsafe_allow_html=True)

# Signing out is not a destination, so it is not a navigation item. It lives at the foot of
# the first screen of each role, which also keeps the bar at five icons and two - the counts
# the stylesheet reads to decide which icons to draw.
if accounts.is_verified_clinician(account):
    # A clinician's job here is reviewing, not keeping a vault, so they get that screen
    # first rather than someone else's emergency card.
    tabs = st.tabs(["Review", "Records"])
    with tabs[0]:
        screen_review(account)
        sign_out()
    with tabs[1]:
        screen_records()
else:
    tabs = st.tabs(["Card", "Add", "Records", "Medicines", "Bill", "Ask"])
    with tabs[0]:
        screen_card()
        vault_transfer(account)
        sign_out()
    with tabs[1]: screen_add()
    with tabs[2]: screen_records()
    with tabs[3]: screen_medicines()
    with tabs[4]: screen_check()
    with tabs[5]: screen_ask()

if st.query_params.get("diag"):
    st.divider()
    st.markdown("#### Agents")
    st.caption("Which agent plays which Madison role, read out of `medvault/agents.py`. "
               "Every entry point below is resolved by `tests/test_agents.py`, so this "
               "cannot drift from the code without the suite failing.")
    import agents as agent_registry
    for line in agent_registry.roster():
        st.text(line)

    st.markdown("#### Server diagnostics")
    for note in CRED_TRACE:
        st.text(note)
    ready, why = reader_ready()
    st.text(f"reader · {'ready' if ready else why}")
    st.text(f"vault  · {store.describe()}")
    st.text(f"local  · {db.DEFAULT_PATH}")
