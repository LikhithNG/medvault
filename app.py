#!/usr/bin/env python3
"""MedVault — every piece of your medical paperwork, on the phone in your pocket.

Built phone-first. The question behind every screen is "could someone hold this up at a
hospital desk and have it be useful", which is a harder test than "does it look like an app".
"""
import os
import pathlib
import sys

import streamlit as st

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "medvault"))

st.set_page_config(page_title="MedVault", page_icon="🩺", layout="centered",
                   initial_sidebar_state="collapsed")

SECRET_KEYS = ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_POOL", "MEDVAULT_DB")
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


_load_credentials()

import accounts                # noqa: E402
import db                      # noqa: E402
import npi                     # noqa: E402
import ui                      # noqa: E402
from schema import KINDS, KIND_ORDER, kind_label      # noqa: E402

st.markdown(ui.CSS, unsafe_allow_html=True)


@st.cache_resource
def vault():
    return db.connect()


con = vault()


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

def screen_card():
    """The emergency card: what someone needs when you cannot explain yourself."""
    p = db.get_profile(con)
    meds = db.list_medications(con, active_only=True)
    name = p.get("full_name") or "Your name"
    cells = [("Blood", p.get("blood_type") or "—"),
             ("Born", p.get("date_of_birth") or "—"),
             ("Records", str(sum(db.counts_by_kind(con).values())))]
    cellhtml = "".join(
        f"<div class='cell'><div class='k'>{k}</div><div class='v'>{v}</div></div>"
        for k, v in cells)
    st.markdown(
        f"<div class='idcard'><div class='who'>{name}</div>"
        f"<div class='sub'>{p.get('conditions') or 'No conditions recorded'}</div>"
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
        st.markdown(f"<div class='med'><div class='n'>{p['emergency_name']}</div>"
                    f"<div class='d'>{p.get('emergency_phone') or 'no number on file'}</div>"
                    f"</div>", unsafe_allow_html=True)

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

    with st.expander("Edit this card"):
        c1, c2 = st.columns(2)
        full = c1.text_input("Full name", p.get("full_name", ""))
        dob = c2.text_input("Date of birth", p.get("date_of_birth", ""), placeholder="1999-07-12")
        blood = c1.text_input("Blood type", p.get("blood_type", ""), placeholder="O+")
        econ = c2.text_input("Emergency contact", p.get("emergency_name", ""))
        ephone = c2.text_input("Their phone", p.get("emergency_phone", ""))
        alle = st.text_area("Allergies", p.get("allergies", ""),
                            placeholder="Penicillin (rash), peanuts", height=70)
        cond = st.text_area("Ongoing conditions", p.get("conditions", ""),
                            placeholder="Asthma, type 2 diabetes", height=70)
        if st.button("Save card", type="primary", use_container_width=True):
            db.save_profile(con, {"full_name": full, "date_of_birth": dob, "blood_type": blood,
                                  "allergies": alle, "conditions": cond,
                                  "emergency_name": econ, "emergency_phone": ephone})
            st.success("Saved.")
            st.rerun()


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
        me = st.session_state.get("account") or {}
        clinical = accounts.is_verified_clinician(me)
        rid = db.add_record(con, kind=kind, title=title or "Untitled record",
                            service_date=sdate or None, provider=provider or None,
                            summary=summary or None, file_name=fname, file_mime=fmime,
                            file_bytes=fbytes, read_by=st.session_state.get("draft_model"),
                            provenance="CLINICAL" if clinical else "SELF",
                            owner_id=me.get("id"),
                            verified_by=me.get("id") if clinical else None)
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
    counts = db.counts_by_kind(con)
    options = ["all"] + [k for k in KIND_ORDER if counts.get(k)]
    kind = st.selectbox("Type", options, label_visibility="collapsed",
                        format_func=lambda k: ("Everything" if k == "all"
                                               else f"{kind_label(k)} ({counts.get(k,0)})"))
    rows = db.list_records(con, kind=None if kind == "all" else kind, query=q or None)

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


def screen_medicines():
    meds = db.list_medications(con, active_only=False)
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

    records = db.list_records(con, limit=2000)
    if not records:
        st.markdown(ui.empty("File a few records first.<br>"
                             "With an empty vault there is nothing to check a bill against."),
                    unsafe_allow_html=True)
        return

    st.info(f"Checking against **{len(records)} record(s)** you have filed.")
    pasted = st.text_area(
        "Paste the bill's lines", height=150,
        placeholder="2026-03-14  70450  CT HEAD/BRAIN WO CONTRAST   1   3,100.00")
    st.caption("One line per charge: a date, a description and an amount.")

    if not st.button("Check it", type="primary", use_container_width=True) or not pasted.strip():
        return

    import re as _re
    import crosscheck
    lines = []
    for raw in pasted.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        d = _re.search(r"\d{4}-\d{2}-\d{2}", raw)
        amt = _re.findall(r"([\d,]+\.\d{2})", raw)
        lines.append({"description": raw, "service_date": d.group(0) if d else None,
                      "charged": float(amt[-1].replace(",", "")) if amt else None})

    checked, summary = crosscheck.check_bill(lines, records)
    st.markdown(ui.section(f"{summary['unsupported']} of {summary['lines']} lines "
                           "have nothing behind them"), unsafe_allow_html=True)
    for r in checked:
        label, tone = crosscheck.VERDICTS[r["verdict"]]
        amt = (f"<span class='amt'>${r['charged']:,.2f}</span>"
               if r.get("charged") else "")
        st.markdown(f"<div class='hit {tone}'>{amt}<div class='h'>{label}</div>"
                    f"<div class='b'>{r['ask']}</div></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='note'>{summary['caveat']}</div>", unsafe_allow_html=True)




# ------------------------------------------------------------ who you are ----

def screen_signin():
    """Two doors. The clinician one goes through the national provider registry."""
    st.markdown(ui.brand("your records<br>stay on this device"), unsafe_allow_html=True)
    st.markdown(ui.section("Sign in"), unsafe_allow_html=True)

    # Deliberately a radio rather than st.tabs. The navigation bar is styled by selecting
    # every tab-list on the page, so a second group of tabs anywhere would be dragged to the
    # bottom of the screen wearing the wrong icons - which is exactly what happened here.
    # One tab group per app, and it is the navigation.
    mode = st.radio("", ["I have an account", "Create one"], horizontal=True,
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
        role = st.radio("This account is for", ["patient", "clinician"], horizontal=True,
                        format_func=lambda r: "A patient" if r == "patient" else "A clinician",
                        key="su_role")
        email2 = st.text_input("Email", key="su_email")
        pw2 = st.text_input("Password", type="password", key="su_pw",
                            help="At least 8 characters.")
        name2 = st.text_input("Name", key="su_name")

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

total = sum(db.counts_by_kind(con).values())
st.markdown(ui.brand(f"{total} record{'' if total == 1 else 's'}<br>on this device"),
            unsafe_allow_html=True)
st.markdown(ui.signed_in_strip(account), unsafe_allow_html=True)

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
    tabs = st.tabs(["Card", "Add", "Records", "Medicines", "Bill"])
    with tabs[0]:
        screen_card()
        sign_out()
    with tabs[1]: screen_add()
    with tabs[2]: screen_records()
    with tabs[3]: screen_medicines()
    with tabs[4]: screen_check()

if st.query_params.get("diag"):
    st.divider()
    st.markdown("#### Server diagnostics")
    for note in CRED_TRACE:
        st.text(note)
    ready, why = reader_ready()
    st.text(f"reader · {'ready' if ready else why}")
    st.text(f"vault  · {db.DEFAULT_PATH}")
