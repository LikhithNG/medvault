#!/usr/bin/env python3
"""The clinician's screen: their patients, and the records waiting on them."""
import streamlit as st

import agentsui
import careteam
import db
import liaison
import ui
from schema import kind_label
from session import vault, visible_owners, when


def your_patients(account):
    """The Liaison's other end: what each patient who chose this clinician has outstanding.

    Only patients who added this clinician to their care team appear. The item text is
    the same text the patient sees, so the two of them are never looking at different
    lists about the same records.
    """
    con = vault()
    mine = careteam.patients(con, account["id"])
    st.markdown(agentsui.heading(ui.section(f"Your patients · {len(mine)}"), "Liaison"),
                unsafe_allow_html=True)
    if not mine:
        st.markdown(ui.empty("No patient has added you to their care team yet.<br>They do "
                             "it from their Card screen with your MedVault email."),
                    unsafe_allow_html=True)
        return
    st.caption("What each patient's own records say is outstanding. Not a symptom check "
               "and not a referral — every item names the record it came from, so it can "
               "be checked rather than trusted.")
    for patient in mine:
        items = liaison.update(con, patient["id"])
        worst = next((i["tone"] for i in items), "ok")
        label = (f"{patient.get('display_name') or patient['email']} · "
                 f"{len(items)} outstanding" if items else
                 f"{patient.get('display_name') or patient['email']} · nothing outstanding")
        with st.expander(label, expanded=(worst == "bad")):
            if not items:
                st.caption("Nothing in this patient's records is outstanding.")
            for i, item in enumerate(items):
                st.markdown(f"<div class='hit {item['tone']} ag-in {agentsui.arrive(i)}'>"
                            f"<div class='h'>{ui.safe(item['title'])}"
                            f"</div><div class='b'>{ui.safe(item['body'])}</div></div>",
                            unsafe_allow_html=True)


def screen_review(account):
    """A clinician confirming that a record matches what they actually issued."""
    con = vault()
    your_patients(account)
    pending = db.pending_verification(con, owner_ids=visible_owners())
    st.markdown(ui.section(f"Waiting on you · {len(pending)}"), unsafe_allow_html=True)
    st.caption("Records a patient filed themselves. Confirming one means it matches what "
               "you issued — your NPI is attached to that claim, so only confirm what you "
               "actually recognise.")

    if not pending:
        st.markdown(ui.empty("Nothing waiting.<br>Every record here has been looked at."),
                    unsafe_allow_html=True)
        return

    for r in pending:
        # Checked before anything about the record is drawn - its title, its summary and
        # its original scan included - not only before the buttons. The query is already
        # scoped to the care team; this is the second lock, for a patient who removes
        # their clinician between one screen and the next.
        if not careteam.may_see(con, account["id"], r["owner_id"]):
            continue
        st.markdown(
            f"<div class='rec'><div class='top'>"
            f"<span class='pill'>{kind_label(r['kind'])}</span>"
            f"{ui.provenance_badge(r)}"
            f"<span class='when'>{when(r)}</span></div>"
            f"<div class='title'>{ui.safe(r['title'])}</div>"
            + (f"<div class='who'>{ui.safe(r['provider'])}</div>" if r.get("provider") else "")
            + (f"<div class='sum'>{ui.safe(r['summary'])}</div>" if r.get("summary") else "")
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
