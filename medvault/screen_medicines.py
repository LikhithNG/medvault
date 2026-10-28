#!/usr/bin/env python3
"""The Medicines screen, where the Scheduler works."""
import datetime

import streamlit as st

import agentsui
import db
import schedule
import ui
from session import me, my_id, vault


def screen_today():
    """The Scheduler on screen: what is due today, and a calendar that rings without us.

    Streamlit cannot wake a phone, and a reminder that only works while this tab is open is
    not a reminder. So the thing that actually reminds is the calendar file: imported once,
    it rings from the phone's own calendar whether or not anyone opens MedVault again.
    """
    con = vault()
    profile = db.get_profile(con, my_id())
    day_start = profile.get("day_start") or schedule.DEFAULT_DAY_START
    meds = db.list_medications(con, active_only=True, owner_id=my_id())
    day = schedule.plan(meds, day_start=day_start)

    # The note is the one input the Scheduler plans from, so the badge changes - and the
    # clock turns once - exactly when the day is re-planned, and not on every rerun.
    st.markdown(agentsui.heading(ui.section(f"Today · {len(day['doses'])} dose(s)"),
                                 "Scheduler", f"day starts {day_start}"),
                unsafe_allow_html=True)
    if not meds:
        st.markdown(ui.empty("Nothing to take.<br>Use <b>Add</b> to photograph a "
                             "prescription and its medicines appear here."),
                    unsafe_allow_html=True)
        return

    coming = schedule.next_due(day)
    if coming:
        st.markdown(f"<div class='hit ok ag-next ag-in'><span class='amt'>{coming['at']}</span>"
                    f"<div class='h'>Next: {coming['med']['name']}</div>"
                    f"<div class='b'>{coming['med'].get('dose') or 'as prescribed'}"
                    + (f" · {schedule.note(coming['parsed'])}"
                       if schedule.note(coming["parsed"]) else "")
                    + "</div></div>", unsafe_allow_html=True)

    for i, dose in enumerate(day["doses"], start=1):
        extra = schedule.note(dose["parsed"])
        ends = (f" · last dose {dose['ends']:%-d %b}" if dose["ends"] else "")
        st.markdown(f"<div class='med ag-in {agentsui.arrive(i)}'>"
                    f"<div class='n'>{dose['at']} · {dose['med']['name']}"
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
        # This used to say "switch them off below", and there was no switch. There is now:
        # each medicine in the list at the foot of this screen has one.
        st.caption("Finished courses not shown: "
                   + ", ".join(f"{e['med']['name']} (last dose {e['ends']:%-d %b})"
                               for e in day["finished"])
                   + ". Mark them finished in the list below so your card stays right.")

    st.markdown(ui.hint("Times are MedVault's suggestion, not part of the prescription.",
                        "A prescription that says “twice daily” says how often, not when. "
                        "The times move with the time your day starts."),
                unsafe_allow_html=True)
    with st.form("daystart", border=False):
        chosen = st.time_input("My day starts at",
                               value=datetime.time.fromisoformat(day_start), step=900)
        if st.form_submit_button("Move my times", use_container_width=True):
            db.save_profile(con, my_id(), {"day_start": chosen.strftime("%H:%M")})
            ui.flash(f"Today's doses now start at {chosen.strftime('%H:%M')}. Download the "
                     f"calendar again to move the reminders on your phone.", icon="⏰")
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
    con = vault()
    screen_today()
    meds = db.list_medications(con, active_only=False, owner_id=my_id())
    st.markdown(ui.section(f"Medicines · {len(meds)}"), unsafe_allow_html=True)
    if not meds:
        st.markdown(ui.empty("No medicines yet.<br>They are pulled out of a prescription "
                             "when you file it on <b>Add</b>."), unsafe_allow_html=True)
        return
    st.markdown(ui.hint("Mark a medicine finished and it leaves your card, today's plan "
                        "and the calendar file."), unsafe_allow_html=True)
    for m in meds:
        bits = " · ".join(x for x in (m.get("dose"), m.get("frequency"), m.get("duration")) if x)
        src = f"{m.get('provider') or 'unknown'} · {m.get('service_date') or 'no date'}"
        stopped = not m.get("active", 1)
        st.markdown(f"<div class='med{' stopped' if stopped else ''}'><div class='n'>"
                    f"{ui.safe(m['name'])}"
                    + ("<span class='pill off'>Finished</span>" if stopped else "")
                    + f"</div><div class='d'>{ui.safe(bits) or 'no dose recorded'}</div>"
                    + (f"<div class='why'>{ui.safe(m['reason'])}</div>" if m.get("reason") else "")
                    + f"<div class='why'>From {ui.safe(src)}</div></div>",
                    unsafe_allow_html=True)
        # The medicine came out of this patient's own records (owner_id above), so the id
        # is one of theirs.
        if st.button("I'm taking this again" if stopped else "Mark as finished",
                     key=f"medact{m['id']}", use_container_width=True):
            db.set_medication_active(con, m["id"], stopped)
            ui.flash(f"{m['name']} " + ("is back on your card." if stopped else
                                        "marked as finished. It is off your card and "
                                        "today's plan."))
            st.rerun()
