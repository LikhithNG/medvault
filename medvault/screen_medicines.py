#!/usr/bin/env python3
"""The Medicines screen, where the Scheduler works and the dose log is kept."""
import datetime

import streamlit as st

import agentsui
import db
import doselog
import doses
import notify
import schedule
import ui
from session import local_now, me, my_id, vault

DOSE_PILL = {"taken": "Taken", "skipped": "Skipped", "due": "Due now", "missed": "Not marked"}


def _mark(con, med, date, at, status):
    left = doselog.record_dose(con, med["id"], date.isoformat(), at, status, owner_id=my_id())
    said = f"{med['name']} at {at}: {status}."
    if status == "taken" and left is not None:
        said += f" {doses.count_text(left, doses.unit(med))} left."
    ui.flash(said, icon="💊" if status == "taken" else "⏭️")
    st.rerun()


def _dose_row(con, row, i, date):
    """One of today's doses, what happened to it, and the taps that record it."""
    esc, med, status = ui.esc, row["med"], row["status"]
    extra = schedule.note(row["parsed"])
    ends = f" · last dose {row['ends']:%-d %b}" if row["ends"] else ""
    pill = f"<span class='pill dose {status}'>{DOSE_PILL[status]}</span>" if status in DOSE_PILL else ""
    st.markdown(f"<div class='med ag-in {agentsui.arrive(i)}{' missed' if status == 'missed' else ''}'>"
                f"<div class='n'>{row['at']} · {esc(med['name'])}{pill}</div>"
                f"<div class='d'>{esc(med.get('dose') or 'as prescribed')}"
                + (f" · {extra}" if extra else "") + ends + "</div></div>", unsafe_allow_html=True)
    # The date is in the key: a page drawn at 23:58 and tapped at 00:02 reruns as tomorrow,
    # and an undated key would have marked tomorrow's dose instead of the one on screen.
    key = f"{med['id']}-{date.isoformat()}-{row['at']}"
    if status in ("taken", "skipped"):
        if st.button("Undo", key=f"undo{key}", use_container_width=True):
            doselog.undo_dose(con, med["id"], date.isoformat(), row["at"], owner_id=my_id())
            ui.flash(f"{med['name']} at {row['at']}: mark taken off.", icon="↩️")
            st.rerun()
        return
    took, skip = st.columns(2)
    if took.button("Taken", key=f"took{key}", type="primary", use_container_width=True):
        _mark(con, med, date, row["at"], "taken")
    if skip.button("Skip", key=f"skip{key}", use_container_width=True):
        _mark(con, med, date, row["at"], "skipped")


def _notifications(con, profile, rows, meds, now):
    """The browser's notifications for today, and the switch that keeps names off a lock screen."""
    bar = st.container()
    hidden = profile.get("notify_private") == "1"
    private = st.toggle("Hide medicine names in notifications", value=hidden, key="notify_private",
                        help="A lock screen is read by whoever picks the phone up.")
    if private != hidden:
        db.save_profile(con, my_id(), {"notify_private": "1" if private else ""})
    with bar:
        notify.render(notify.plan(rows, meds, now, private=private))


def _unmarked(rows):
    """Doses long past with nothing recorded, said plainly. Not an alarm: often the dose was
    taken and nobody tapped. This is the fact the Guardian will pass to the family."""
    late = doses.missed(rows)
    if not late:
        return
    which = ", ".join(f"{r['med']['name']} at {r['at']}" for r in late)
    st.markdown(f"<div class='hit warn'><div class='h'>Not marked yet: {ui.esc(which)}</div>"
                f"<div class='b'>Did you take {'it' if len(late) == 1 else 'them'}? Tap Taken or "
                f"Skip below so your record shows what really happened.</div></div>",
                unsafe_allow_html=True)


def screen_today():
    """The Scheduler on screen: what is due today, and a calendar that rings without us.

    Streamlit cannot wake a phone, and a reminder that only works while this tab is open is
    not a reminder. So the thing that actually reminds is the calendar file: imported once,
    it rings from the phone's own calendar whether or not anyone opens MedVault again.
    """
    con = vault()
    profile = db.get_profile(con, my_id())
    day_start = schedule.valid_day_start(profile.get("day_start"))
    meds = db.list_medications(con, active_only=True, owner_id=my_id())
    # The viewer's own clock: the hosted server's is UTC, which put "next" five hours out
    # in Boston and would have called a dose missed before its time had come.
    now = local_now()
    day = schedule.plan(meds, today=now.date(), day_start=day_start)

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

    esc = ui.esc       # medicine names and doses were read off a page, or typed
    rows = doses.board(day, doselog.dose_log(con, my_id(), since=day["date"].isoformat()), now)
    _unmarked(rows)
    _notifications(con, profile, rows, meds, now)
    coming = schedule.next_due(day, now)
    if coming:
        st.markdown(f"<div class='hit ok ag-next ag-in'><span class='amt'>{coming['at']}</span>"
                    f"<div class='h'>Next: {esc(coming['med']['name'])}</div>"
                    f"<div class='b'>{esc(coming['med'].get('dose') or 'as prescribed')}"
                    + (f" · {schedule.note(coming['parsed'])}"
                       if schedule.note(coming["parsed"]) else "")
                    + "</div></div>", unsafe_allow_html=True)

    for i, row in enumerate(rows, start=1):
        _dose_row(con, row, i, day["date"])

    # The groups that are deliberately NOT on a clock, each said out loud rather than
    # dropped. Silently omitting a medicine from a reminder list looks like "nothing to
    # take", which for the as-needed ones is fine and for the unreadable ones is not.
    if day["as_needed"]:
        st.markdown(ui.section("Only when you need it — no alarm"), unsafe_allow_html=True)
        for e in day["as_needed"]:
            gap = (f"Not more often than every {e['parsed']['every_hours']} hours."
                   if e["parsed"]["every_hours"] else "Follow the label for how often.")
            st.markdown(f"<div class='med'><div class='n'>{esc(e['med']['name'])}</div>"
                        f"<div class='d'>{esc(e['med'].get('dose') or '')} · {gap}</div>"
                        f"<div class='why'>Prescribed as needed, so it is not scheduled. "
                        f"Taking it on a timetable is not what the prescription says.</div>"
                        f"</div>", unsafe_allow_html=True)
    if day["weekly"]:
        st.markdown(ui.section("Not every day"), unsafe_allow_html=True)
        for e in day["weekly"]:
            st.markdown(f"<div class='med'><div class='n'>{esc(e['med']['name'])}</div>"
                        f"<div class='d'>{esc(e['parsed']['text'])} — pick the day with your "
                        f"pharmacist; it is not on the daily calendar.</div></div>",
                        unsafe_allow_html=True)
    if day["unreadable"]:
        st.markdown(ui.section("Could not be timed"), unsafe_allow_html=True)
        for e in day["unreadable"]:
            st.markdown(f"<div class='hit warn'><div class='h'>{esc(e['med']['name'])}</div>"
                        f"<div class='b'>The prescription says "
                        f"“{esc(e['parsed']['text'] or 'nothing about how often')}”, which "
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
        st.markdown(ui.hint("Notifications above work while MedVault is open; the calendar always.",
                            "A web page cannot wake a phone. Notifications come from your browser "
                            "while MedVault is open, or installed and running in the background. "
                            "The calendar file rings from your phone's own calendar, with "
                            "MedVault closed."), unsafe_allow_html=True)

    history = doselog.dose_log(con, my_id())
    if history:
        st.download_button("Download my dose history (CSV)", data=doses.history_csv(history),
                           file_name="medvault-doses.csv", mime="text/csv", use_container_width=True)
        st.caption("Every dose marked taken or skipped, for your doctor or pharmacist. It names "
                   "your medicines: share it only with people you mean to.")


def _stock_line(m, today):
    """What the box holds and how long it lasts, or nothing when nobody is counting."""
    state, count = doses.stock_state(m, today), None
    if state["left"] is not None:
        count = doses.count_text(state["left"], state["unit"])
    if state["level"] == "out":
        line = "<div class='stock out'>Out of stock. Refill before the next dose.</div>"
    elif state["level"] == "unknown":
        why = ("Set how many one dose uses to see when it runs out." if not doses.per_dose(m)
               else "No run-out date: it is not taken on a daily schedule.")
        line = f"<div class='stock'>{count} in the box. {why}</div>"
    elif state["enough"]:
        line = f"<div class='stock'>{count} left: enough to finish the course.</div>"
    elif state["level"] == "low":
        days = (state["runs_out"] - today).days
        line = (f"<div class='stock low'>Running low: {count} left, about {days} day"
                f"{'' if days == 1 else 's'} · refill by {state['runs_out']:%a %-d %b}</div>")
    elif state["level"] == "ok":
        line = f"<div class='stock'>{count} left · lasts until about {state['runs_out']:%-d %b}</div>"
    else:
        line = ""
    expiry = doses.expiry_state(m, today)
    if expiry:
        on = datetime.date.fromisoformat(m["expires"]).strftime("%-d %b %Y")
        line += (f"<div class='stock out'>Expired on {on}. Ask your pharmacist before taking it.</div>"
                 if expiry == "expired" else f"<div class='stock low'>Expires {on}.</div>")
    return line


def _within(value):
    """A stored or label-read number as a field can show it: Streamlit raises on a value past
    a field's maximum, and "500 ml" or an old import must not take the screen down."""
    return None if value is None else min(float(value), float(doselog.STOCK_MAX))


def _stock_settings(con, m):
    """The count, the dose size, the refill size and the expiry date, behind one expander."""
    with st.expander("Stock and expiry"):
        with st.form(f"stockform{m['id']}", border=False):
            # An empty field is "not counted" or "not known"; a number is a number. No tick
            # box beside it: one that had to be ticked as well saved nothing when it wasn't.
            left = st.number_input("In the box now", min_value=0.0, max_value=float(doselog.STOCK_MAX),
                                   value=_within(m.get("stock")), step=1.0, placeholder="Not counted",
                                   key=f"left{m['id']}", help="Leave empty to stop counting.")
            # No default guess: "500 mg" says nothing about how many leave the box, so the
            # field stays empty until the patient says.
            each = st.number_input("One dose uses", min_value=0.0, max_value=float(doselog.STOCK_MAX),
                                   value=_within(doses.per_dose(m)), step=0.5, placeholder="Not known",
                                   key=f"each{m['id']}",
                                   help="How many tablets, capsules or puffs leave the box each time.")
            refill = st.number_input("A refill holds", min_value=0.0, max_value=float(doselog.STOCK_MAX),
                                     value=_within(m.get("refill_size")), step=1.0, placeholder="Not known",
                                     key=f"refill{m['id']}")
            expires = st.text_input("Expires (YYYY-MM-DD)", value=m.get("expires") or "", key=f"exp{m['id']}")
            if st.form_submit_button("Save stock", use_container_width=True):
                try:
                    doselog.set_stock(con, m["id"], my_id(), stock=left,
                                      per_dose=each or None, refill_size=refill or None,
                                      expires=expires.strip() or None)
                except ValueError as problem:
                    st.error(str(problem))
                else:
                    ui.flash(f"{m['name']}: stock saved.", icon="📦")
                    st.rerun()
    if m.get("refill_size") and m.get("stock") is not None:
        if st.button(f"Refilled: add {m['refill_size']:g}", key=f"refilled{m['id']}", use_container_width=True):
            new = doselog.refill(con, m["id"], my_id())
            ui.flash(f"{m['name']}: {doses.count_text(new, doses.unit(m))} in the box now.", icon="📦")
            st.rerun()


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
    today = local_now().date()
    for m in meds:
        bits = " · ".join(str(x) for x in (m.get("dose"), m.get("frequency"), m.get("duration"))
                          if x)
        src = f"{m.get('provider') or 'unknown'} · {m.get('service_date') or 'no date'}"
        stopped = not m.get("active", 1)
        st.markdown(f"<div class='med{' stopped' if stopped else ''}'><div class='n'>"
                    f"{ui.safe(m['name'])}"
                    + ("<span class='pill off'>Finished</span>" if stopped else "")
                    + f"</div><div class='d'>{ui.safe(bits) or 'no dose recorded'}</div>"
                    + (f"<div class='why'>{ui.safe(m['reason'])}</div>" if m.get("reason") else "")
                    + f"<div class='why'>From {ui.safe(src)}</div>"
                    + ("" if stopped else _stock_line(m, today)) + "</div>",
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
        if not stopped:
            _stock_settings(con, m)
