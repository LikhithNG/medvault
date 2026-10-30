#!/usr/bin/env python3
"""The clinician's screen: their patients, and the records waiting on them."""
import time

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
    st.markdown(ui.hint("What each patient's own records say is outstanding.",
                        "Not a symptom check and not a referral — every item names the "
                        "record it came from, so it can be checked rather than trusted."),
                unsafe_allow_html=True)
    # Each patient can see when their doctors last signed in with their records. The
    # screen redraws on every click, so this asks the vault at most once per visit gap -
    # and again after one, so a tab left open over a weekend is not Friday's sign-in.
    noted = st.session_state.setdefault("views_noted", {})
    now = time.time()
    for patient in mine:
        if now - noted.get(patient["id"], 0) >= careteam.VISIT_GAP_S:
            careteam.note_view(con, account["id"], patient["id"], now=now)
            noted[patient["id"]] = now
        items = liaison.update(con, patient["id"])
        worst = next((i["tone"] for i in items), "ok")
        name = patient.get("display_name") or patient["email"]
        label = f"{name} · {len(items)} outstanding" if items else f"{name} · nothing outstanding"
        with st.expander(label, expanded=(worst == "bad")):
            if not items:
                st.caption("Nothing in this patient's records is outstanding.")
            else:
                # The items speak to the patient ("You listed Penicillin on your card");
                # unframed, they read to a clinician as if the clinician had listed it.
                st.caption(f"Worded for {name} — this is the list {name} sees.")
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
    # Which patient filed each record. The list used to show a title and a provider and
    # nothing about whose it was - with two patients on a care team, a clinician could not
    # tell whose prescription they were about to put their NPI on.
    whose = {p["id"]: p.get("display_name") or p["email"]
             for p in careteam.patients(con, account["id"])}
    st.markdown(ui.section(f"Waiting on you · {len(pending)}"), unsafe_allow_html=True)
    st.markdown(ui.hint("Only confirm records you actually issued — your NPI is attached "
                        "to the confirmation.",
                        "These are records a patient filed themselves. Confirming one says "
                        "it matches what you issued."), unsafe_allow_html=True)

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
            f"<span class='when'>{ui.esc(when(r))}</span></div>"
            f"<div class='title'>{ui.safe(r['title'])}</div>"
            f"<div class='patient'>Filed by <b>{ui.safe(whose.get(r['owner_id'], 'a patient'))}"
            f"</b></div>"
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
        # "Not mine" tells the patient a clinician did not recognise their record, and there
        # is no undo for it on this screen - so it asks first, like removing a doctor does.
        if st.session_state.get("confirm_notmine") == r["id"]:
            st.markdown("<div class='ask'>Mark this as not one you issued?</div>",
                        unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button("Yes, not mine", key=f"noy{r['id']}", use_container_width=True):
                db.verify_record(con, r["id"], account["id"], note="reviewed")
                db.unverify_record(con, r["id"],
                                   note="Clinician did not recognise this record")
                st.session_state.pop("confirm_notmine", None)
                ui.flash(f"Marked “{r['title']}” as not one you issued.")
                st.rerun()
            if c2.button("Go back", key=f"non{r['id']}", use_container_width=True):
                st.session_state.pop("confirm_notmine", None)
                st.rerun()
            continue
        c1, c2 = st.columns(2)
        if c1.button("Confirm", key=f"ok{r['id']}", type="primary", use_container_width=True):
            db.verify_record(con, r["id"], account["id"],
                             note=f"Confirmed by NPI {account.get('npi')}")
            ui.flash(f"Confirmed “{r['title']}”. It now shows as verified by you.")
            st.rerun()
        if c2.button("Not mine", key=f"no{r['id']}", use_container_width=True):
            st.session_state["confirm_notmine"] = r["id"]
            st.rerun()
