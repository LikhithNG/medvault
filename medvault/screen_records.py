#!/usr/bin/env python3
"""Adding a document, and the list of everything filed."""
import time

import streamlit as st

import accounts
import agentsui
import db
import ui
from schema import KIND_ORDER, kind_label
from session import me, reader_ready, vault, visible_owners, when


def screen_add():
    """Upload a document, let it be read, confirm what was read, file it."""
    con = vault()
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
        # The Reader at work, saying which step it is on, then replaced by what it read.
        slot = st.empty()
        def reading(step):
            slot.markdown(agentsui.working("Reader", "Reading your document", step),
                          unsafe_allow_html=True)
        reading("Opening it…")
        started = time.perf_counter()
        text, note = (None, None)
        if is_pdf:
            import io as _io
            text, note = pdf_text(_io.BytesIO(data))
        if is_pdf and text:
            reading(f"Read the text layer · {note}")
            rec, meta = read_document(text=text)
        else:
            reading("Looking at the page — a photograph takes a few seconds")
            rec, meta = read_document(image=(up.type or "image/jpeg", data))
        slot.empty()
        st.session_state["draft_took"] = agentsui.took(time.perf_counter() - started)

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

    took = st.session_state.get("draft_took")
    st.markdown(agentsui.heading(ui.section("Check this before filing"), "Reader",
                                 f"read in {took}" if took else ""),
                unsafe_allow_html=True)
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
        for k in ("draft", "draft_file", "draft_model", "draft_took"):
            st.session_state.pop(k, None)
        st.success(f"Filed. {len(meds)} medicine(s) added." if meds else "Filed.")
        st.rerun()


def screen_records():
    con = vault()
    st.markdown(ui.section("Everything you have filed"), unsafe_allow_html=True)
    q = st.text_input("Search", placeholder="tinnitus, amoxicillin, Lahey…",
                      label_visibility="collapsed")
    counts = db.counts_by_kind(con, owner_ids=visible_owners())
    options = ["all"] + [k for k in KIND_ORDER if counts.get(k)]
    kind = st.selectbox("Type", options, label_visibility="collapsed",
                        format_func=lambda k: ("Everything" if k == "all"
                                               else f"{kind_label(k)} ({counts.get(k,0)})"))
    rows = db.list_records(con, kind=None if kind == "all" else kind, query=q or None,
                           owner_ids=visible_owners())

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
            f"<div class='title'>{ui.safe(r['title'])}</div>"
            + (f"<div class='who'>{ui.safe(r['provider'])}</div>" if r.get("provider") else "")
            + (f"<div class='sum'>{ui.safe(r['summary'])}</div>" if r.get("summary") else "")
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
