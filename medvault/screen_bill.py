#!/usr/bin/env python3
"""The Bill screen: the form, and the run that hands a bill from agent to agent.

The drawing of the findings lives in bill_render.py, so this file is about what happens
when somebody presses "Check this bill", and that one is about what they see after.
"""
import time

import streamlit as st

import agentsui
import db
import paste
import providers
import quota
import runtime
import ui
from bill_render import render_bill, render_bill_read
from session import ai_allowance, me, my_id, reader_ready, vault


# The three agents a bill passes through, in the order it reaches them.
BILL_RELAY = ("Reader", "Checker", "Advocate")


RELAY_INTRO = ("Three agents take it from here: the Reader reads a photo of the bill, the "
               "Checker prices every line, and the Advocate writes a letter if anything is "
               "flagged.")


# A step that finished this long before the run did was on screen long enough to be seen
# finishing. Anything faster shows its work once more in the final frame, in turn.
SEEN_SECONDS = 0.4


@st.cache_resource
def price_table():
    """Pricing a bill needs to know whose published file to price it against."""
    import checker
    return checker.load_reference()


def bill_form():
    """Everything the patient tells the Bill screen. Returns a dict; draws the widgets."""
    import rights
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
        st.markdown(ui.hint(*providers.notice("The bill is sent to an AI reader. Pasted "
                                              "lines are not."),
                            label="Where it goes"), unsafe_allow_html=True)
        ai_allowance()
        upload = st.file_uploader("Photo or PDF of the bill",
                                  type=["jpg", "jpeg", "png", "webp", "pdf"],
                                  label_visibility="collapsed", key="bill_file")
        st.markdown(ui.hint("On a phone this opens the camera. MedVault does not keep the "
                            "bill.",
                            "It is read once to pull out the codes, quantities and amounts. "
                            "To keep a copy, file it as a record on the Add screen."),
                    unsafe_allow_html=True)
        if upload:
            st.caption(f"{upload.name} · {len(upload.getvalue())/1024:,.0f} KB")

    # A few questions about the patient's situation unlock protections worth far more than
    # any rate difference on the bill - and none of them need a price file to answer.
    with st.expander("Optional: 4 quick questions that can unlock legal protections"):
        st.caption("Some protections depend on your situation, not on the amounts. Skip "
                   "anything you are not sure of — a blank counts as unknown, never as no.")
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

    known = sorted({h for h, _ in price_table()})
    pretty = {h: h.title() for h in known}
    hospital = st.selectbox(
        "Which hospital issued this bill?", ["— not listed —"] + known,
        format_func=lambda h: h if h.startswith("—") else pretty[h], key="bill_hosp")
    st.markdown(ui.hint("Not listed? Leave it unset — every line is still checked against "
                        "Medicare.",
                        "Nine hospitals' published price files were collected for this "
                        "project. The national Medicare allowance covers any CPT code, so a "
                        "bill from anywhere still gets a benchmark."),
                unsafe_allow_html=True)

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
    listed = hospital != "— not listed —"
    return {"pasting": how == "Paste the lines", "pasted": pasted, "upload": upload,
            "ctx": ctx,
            "hospital": hospital if listed else None,
            "hospital_name": pretty.get(hospital) if listed else None,
            "answers": (cov, emg, npf, inn, gfe_raw)}


def bill_key(form, records):
    """Everything a checked bill was computed from. A different key is a different bill.

    The form is not all of it. The cross-check reads the records, the letter is signed
    with the name on the card, and both belong to one account - so all three are in the
    key. Without them, filing the very record a line was missing redrew the old "nothing
    behind it" finding, and a letter saying so, next to a count that had gone up by one.
    """
    con = vault()
    import hashlib
    upload = form["upload"]
    content = (hashlib.sha256(upload.getvalue()).hexdigest() if upload is not None
               else form["pasted"])
    held = tuple((r["id"], r.get("added_at"), r.get("service_date"), r.get("title"),
                  r.get("summary")) for r in records)
    signed = db.get_profile(con, my_id()).get("full_name")
    return hashlib.sha256(repr((my_id(), upload is not None, content, form["hospital"],
                                form["answers"], held, signed)).encode()).hexdigest()


def idle_relay(form):
    """The three agents before anything has happened, so nobody is surprised by them."""
    reader = (agentsui.step("Reader", "skip", "You paste it") if form["pasting"]
              else agentsui.step("Reader", "wait", "Reads the photo"))
    return [reader, agentsui.step("Checker", "wait", "Prices each line"),
            agentsui.step("Advocate", "wait", "Writes the letter")]


def read_bill_upload(upload, steps, show):
    """The Reader's turn. Returns (lines, read, problem, steps)."""
    import hashlib
    ok, why = reader_ready()
    if not ok:
        return None, None, ("This bill cannot be read here",
                            f"The reader is not set up — {why}. Paste the lines instead "
                            f"and everything else still works.", None), \
            agentsui.advance(steps, "Reader", "fail", "Not set up")

    data = upload.getvalue()
    sig = hashlib.sha256(data).hexdigest()
    # Changing the hospital or an answer after a check used to mean reading the photo
    # again - a second model call for a bill that had not changed.
    held = st.session_state.get("bill_read")
    if held and held["sig"] == sig:
        return held["lines"], held["read"], None, \
            agentsui.advance(steps, "Reader", "done", "Read already")

    # Taken here, after the bill already read is reused: changing the hospital on a bill
    # read before the limit was reached costs nothing, so it is not refused. And taken
    # before the model is asked, so a read that fails still counts.
    if not quota.take(vault(), me()):
        why = quota.note(quota.allowance(vault(), me())) or "No AI reads are left today."
        return None, None, ("This bill cannot be read by AI right now",
                            f"{why} Paste the lines instead — that never uses AI.", None), \
            agentsui.advance(steps, "Reader", "fail", "Daily limit")

    from extract import pdf_pages, pdf_text, read_bill_verified, with_pages
    is_pdf = (upload.type or "").endswith("pdf") or upload.name.lower().endswith(".pdf")
    steps = agentsui.advance(steps, "Reader", "work", "Reading…")
    show(steps, "Reader · opening it…")
    started = time.perf_counter()
    text = None
    pages = None
    if is_pdf:
        import io as _io
        text, note = pdf_text(_io.BytesIO(data))
        if text:
            pages = pdf_pages(_io.BytesIO(data))
            show(steps, f"Reader · read the text layer · {note}")
    if not text:
        show(steps, "Reader · looking at the page, then checking the lines add up to its "
                    "total")
    with runtime.span("Reader", trace=vault()) as span:
        lines, meta = (read_bill_verified(text=text, deadline=span.left()) if text
                       else read_bill_verified(image=(upload.type or "image/jpeg", data),
                                               deadline=span.left()))
        span.saw(meta)
        if meta.get("ok") and not lines:
            span.fail("no charges")
    spent = agentsui.took(time.perf_counter() - started)

    if not meta.get("ok"):
        return None, None, ("That bill could not be read just now",
                            "The reading service did not answer. Nothing was stored. Paste "
                            "the lines instead, or try again in a moment.",
                            str(meta.get("error"))[:160]), \
            agentsui.advance(steps, "Reader", "fail", "Did not answer")
    if not lines:
        return None, None, ("No charges could be read from that bill",
                            "Every line of an itemised bill carries a code, a quantity and "
                            "an amount. None were found — this may be a summary rather than "
                            "an itemised statement. Ask the hospital for the itemised "
                            "version.", None), \
            agentsui.advance(steps, "Reader", "fail", "No charges found")

    lines = with_pages(lines, pages)
    read = {"took": spent, "attempts": meta.get("attempts", 1),
            "reconciled": meta.get("reconciled"), "provider": meta.get("provider"),
            "hospital": meta.get("hospital")}
    st.session_state["bill_read"] = {"sig": sig, "lines": lines, "read": read}
    return lines, read, None, agentsui.advance(steps, "Reader", "done", f"Read in {spent}")


def unreadable_as_itemised(lines):
    """Why these lines cannot be checked, or None when they can.

    A statement with no billing codes cannot be checked against anything. Itemized
    rejected these before the Checker ever saw them, which is why a latent defect in its
    duplicate rule never surfaced there: two lines with an empty code match each other and
    are reported as the same code billed twice. Guarding at the boundary fixes the
    behaviour and leaves checker.py byte-identical to the module that produced the
    Assignment 4 figures.
    """
    if not lines:
        return ("No charges found", "Nothing in what you pasted looks like a charge. Put "
                "one charge on each line: a date, a code, a description and an amount.",
                None)
    if not any((l.get("code") or "").strip() for l in lines):
        return ("No billing codes found", "Every line of an itemised bill carries a "
                "procedure code, like 74177 or J1885. None were found here — this may be a "
                "summary statement rather than an itemised one. Ask the hospital for the "
                "itemised version; you cannot check what you cannot see.", None)
    return None


def check_bill_run(form, key, records, slot):
    """Hand the bill along the relay, showing each agent as it works. Returns the run.

    The Reader runs here, because it needs the upload and this session's cache of what it
    read. Everything after it is pipeline.check_lines, which knows nothing about screens:
    this function only turns its events into the relay above the button.
    """
    con = vault()
    import pipeline

    def show(steps, now):
        slot.markdown(agentsui.relay(steps, now), unsafe_allow_html=True)

    state = {"steps": [agentsui.step(n) for n in BILL_RELAY]}
    finished = {}

    def stop(steps, problem, lines=None, read=None):
        steps = [agentsui.step(s["name"], "skip" if s["state"] == "wait" else s["state"],
                               s["note"] if s["state"] != "wait" else "Stopped")
                 for s in steps]
        show(steps, problem[0])
        return {"key": key, "steps": steps, "now": problem[0], "problem": problem,
                "lines": lines, "read": read}

    # ---- the Reader, unless the patient typed the lines themselves
    if form["upload"] is None:
        state["steps"] = agentsui.advance(state["steps"], "Reader", "skip", "You pasted it")
        lines, read = paste.lines(form["pasted"]), None
    else:
        lines, read, problem, state["steps"] = read_bill_upload(form["upload"],
                                                                state["steps"], show)
        if problem:
            return stop(state["steps"], problem)
        finished["Reader"] = time.perf_counter()

    problem = unreadable_as_itemised(lines)
    if problem:
        # What was read stays on screen: a Reader that missed the codes on an itemised
        # bill looks exactly like a summary statement, and only the lines show which.
        return stop(state["steps"], problem, lines, read)

    hospital = form["hospital_name"]

    def on_step(e):
        """pipeline.check_lines' events, drawn as the relay."""
        name, kind = e["agent"], e["state"]
        if kind == "work" and name == "Checker":
            note, now = "Pricing…", (f"Checker · pricing {e['lines']} line(s) against the "
                                     f"national Medicare allowance"
                                     + (f" and {hospital}'s published prices"
                                        if hospital else ""))
        elif kind == "work":
            note, now = "Writing…", ("Advocate · ranking the flagged lines by the money at "
                                     "stake and writing the letter")
        elif kind == "done" and name == "Checker":
            took = agentsui.took(e["seconds"])
            note = f"{e['flagged']} flagged · {took}" if e["priced"] else f"Priced in {took}"
            now = None
        elif kind == "done":
            note, now = f"Letter · {agentsui.took(e['seconds'])}", None
        else:
            note, now = ("Nothing flagged" if e.get("priced") else "Needs the hospital"), None
        state["steps"] = agentsui.advance(state["steps"], name, kind, note)
        if kind == "done":
            finished[name] = time.perf_counter()
        if now:
            show(state["steps"], now)

    result = pipeline.check_lines(
        lines, hospital=hospital, ctx=form["ctx"], records=records,
        patient_name=db.get_profile(con, my_id()).get("full_name"),
        price_table=price_table(), on_step=on_step, trace=con)

    # Agents that finished faster than a frame could show them get to show their work
    # once in the final frame, in the order they did it. One that was visibly seen
    # finishing - a Reader that took four seconds - is not made to do it twice.
    end = time.perf_counter()
    steps = agentsui.finale(state["steps"],
                            {n for n, t in finished.items() if end - t < SEEN_SECONDS})
    priced, letter = result["priced"], result["letter"]
    now = (f"Done. {len(result['charges'])} line(s) checked against Medicare and your "
           f"records"
           + (f"; {result['flagged']} flagged against {hospital}'s published prices"
              if priced else
              ". Choose the hospital above to compare against its own published prices")
           + ("; the letter is below." if letter else "."))
    show(steps, now)
    return {"key": key, "steps": steps, "now": now, "problem": None, "lines": lines,
            "charges": result["charges"], "credits": result["credits"],
            "read": read, "protections": result["protections"],
            "still_open": result["still_open"], "face": result["face"],
            "bench": result["bench"], "priced": priced,
            "checker_took": agentsui.took(result["checker_seconds"]),
            "checked": result["checked"], "summary": result["summary"], "letter": letter,
            "letter_took": (agentsui.took(result["letter_seconds"])
                            if result["letter_seconds"] is not None else None)}


def screen_check():
    """The reason this app and a bill checker belong to the same person."""
    con = vault()
    st.markdown(ui.section("Check a bill against your records"), unsafe_allow_html=True)
    st.caption("A price check asks whether a charge was the right amount. This asks "
               "something a price list cannot: does your own paperwork show it happened?")

    records = db.list_records(con, limit=2000, owner_id=my_id())
    # An empty vault used to stop the whole screen with "file a few records first". Only
    # the cross-check needs records; the prices do not, and somebody holding a bill on
    # their first visit was turned away from the part that needed nothing from them.
    if records:
        st.info(f"Checking against **{len(records)} record(s)** you have filed.")
    else:
        st.info("**No records filed yet.** Every line is still priced; it just cannot be "
                "matched to your paperwork until you file some on **Add**.")
    form = bill_form()
    ready = bool(form["pasted"].strip()) or form["upload"] is not None

    # The relay sits directly above the button, so the agents are on screen - waiting,
    # then working - in the one place somebody who has just pressed it is looking.
    slot = st.empty()
    clicked = st.button("Check this bill", type="primary", use_container_width=True)

    # The findings used to exist only on the run in which the button was pressed. Asking
    # a question underneath them, or downloading the letter, is another run - and it wiped
    # the screen, so the question box under a checked bill could never answer anything.
    # The finished run is kept now, keyed on everything it was worked out from.
    key = bill_key(form, records)
    run = st.session_state.get("bill_run")
    if clicked and ready:
        run = check_bill_run(form, key, records, slot)
        st.session_state["bill_run"] = run
    elif run and run["key"] == key:
        slot.markdown(agentsui.relay(run["steps"], run["now"]), unsafe_allow_html=True)
    else:
        slot.markdown(agentsui.relay(idle_relay(form), RELAY_INTRO), unsafe_allow_html=True)
        return

    if run["problem"]:
        if run.get("read"):
            render_bill_read(run["read"], run["lines"])
        title, body, detail = run["problem"]
        st.error(f"**{title}**\n\n{body}")
        if detail:
            st.markdown(ui.hint("", ui.safe(detail), label="Technical detail"),
                        unsafe_allow_html=True)
        return
    render_bill(run)
