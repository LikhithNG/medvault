#!/usr/bin/env python3
"""The Card screen: the emergency card, the care team, the vault as a file, signing out."""
import json
import os
import time

import streamlit as st

import careteam
import db
import store
import ui
from schema import BLOOD_TYPES, missing_essentials
from session import my_id, vault


def profile_editor(p, expanded):
    """The form behind the card. Separated out so it can be opened from two places.

    Blood type is a dropdown rather than a free-text box: it is the one field here where a
    typo is a safety problem, and "o positive", "O +" and "0+" are all things people type.
    """
    con = vault()
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


def screen_card():
    """The emergency card: what someone needs when you cannot explain yourself."""
    con = vault()
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


def hosted():
    """Whether this copy is running somewhere with a disk that does not survive a reboot.

    Streamlit Community Cloud restarts an app on inactivity and on every redeploy, and
    takes the SQLite file with it. For a bill checker that is annoying; for something
    called a vault it is a promise being broken quietly. So the app says so, in the place
    where somebody is looking at the records they would lose.
    """
    return bool(os.environ.get("MEDVAULT_HOSTED")) or "HOSTNAME" in os.environ and \
        os.environ.get("HOME", "").startswith("/home/appuser")


def care_team_panel():
    """The patient's side of the care team: who can see their records, and the off switch.

    Before this existed, any clinician account could read every patient's records. The
    Liaison reports a patient's outstanding items to their doctors, and building it on
    that would have broadcast to every clinician on the server - so it is built on this
    instead, and this is the patient's to change.
    """
    con = vault()
    st.markdown(ui.section("Your care team"), unsafe_allow_html=True)
    st.caption("The clinicians you choose can see your records and the list of what they "
               "say is outstanding. Nobody else can. Remove someone and it takes effect "
               "immediately.")
    for doc in careteam.team(con, my_id()):
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"<div class='med'><div class='n'>{doc.get('display_name') or doc['email']}"
                    f"</div><div class='d'>{doc.get('npi_specialty') or 'Clinician'} · "
                    f"NPI {doc.get('npi')} verified</div></div>", unsafe_allow_html=True)
        if c2.button("Remove", key=f"ct{doc['id']}", use_container_width=True):
            careteam.remove(con, my_id(), doc["id"])
            st.rerun()
    with st.form("addcare", border=False, clear_on_submit=True):
        email = st.text_input("Your doctor's MedVault email", placeholder="doctor@clinic.org")
        if st.form_submit_button("Add to my care team", use_container_width=True) and email:
            added, problem = careteam.add(con, my_id(), email)
            if problem:
                st.error(problem)
            else:
                st.success(f"Added {added.get('display_name') or added['email']}.")
                st.rerun()


def vault_transfer(account):
    """Take your records out, and put them back. Both halves, or it is a trap."""
    con = vault()
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
        # Everything, not only the account. Signing out used to leave the last bill check,
        # the Ask conversation and a half-filed document in the session, and the next
        # person to sign in on the same phone could see them.
        st.session_state.clear()
        st.session_state["arrived"] = True                 # see ui.to_top()
        st.rerun()
