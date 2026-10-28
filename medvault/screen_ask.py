#!/usr/bin/env python3
"""The Ask screen: the Liaison's list, and the Companion's answers."""
import time

import streamlit as st

import agentsui
import ask
import careteam
import liaison
import ui
from session import me, my_id, reader_ready, vault


EXAMPLE_QUESTIONS = [
    "What is each of my medicines for?",
    "What did my last scan find?",
    "Why am I taking two antibiotics?",
]


def _render_turn(turn):
    """One question and its answer, with the badge that says where the answer came from."""
    st.markdown(f"<div class='qa'><div class='bubble q ag-in'>{ui.safe(turn['q'])}</div>",
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
    body = "".join(f"<p>{ui.safe(para)}</p>" for para in a["answer"].split("\n")
                   if para.strip())
    srcs = ""
    if a.get("sources"):
        items = " · ".join(
            f"<b>{ui.safe(r.get('title'))}</b> ({ui.safe(r.get('service_date') or 'undated')})"
            for r in a["sources"].values())
        srcs = f"<div class='srcs'>Read out of: {items}</div>"
    # Who answered, and how long it took - the Companion's mark plays once as the answer
    # lands. An answer the model never gave (an emergency, a refused dose question) is
    # still the Companion's, so it is stamped the same way.
    who = agentsui.stamp("Companion", f"answered in {turn['took']}") if turn.get("took") else ""
    st.markdown(f"<div class='bubble a ag-in ag-i2'><span class='badge {tone}'>"
                f"{label}</span>{body}{srcs}{who}</div></div>", unsafe_allow_html=True)


def screen_ask():
    """A bot for the paperwork, with the checkable things checked before it is asked."""
    con = vault()
    # One list, the Liaison's. It is the Companion's checks plus overdue follow-ups and
    # untimeable doses - showing both would put the same finding on screen twice, which
    # is the mistake this project has made three times already.
    findings = liaison.update(con, my_id())
    st.markdown(agentsui.heading(
        ui.section(f"What your own records say is outstanding · {len(findings)}"),
        "Liaison"), unsafe_allow_html=True)
    st.caption("Worked out here, from your records, by arithmetic — no model is involved, "
               "nothing leaves this server, and nothing here is a judgement about your "
               "health. It is what your own paperwork says and has not been followed up.")
    if not findings:
        st.markdown(ui.empty("Nothing outstanding.<br>No overdue follow-up, no duplicate "
                             "medicine, no finished course still marked current, nothing "
                             "that collides with your recorded allergies."),
                    unsafe_allow_html=True)
    for i, f in enumerate(findings):
        st.markdown(f"<div class='hit {f['tone']} ag-in {agentsui.arrive(i)}'>"
                    f"<div class='h'>{ui.safe(f['title'])}</div>"
                    f"<div class='b'>{ui.safe(f['body'])}</div></div>", unsafe_allow_html=True)

    doctors = careteam.team(con, my_id())
    if findings:
        if doctors:
            st.caption("Your care team sees this list too: "
                       + ", ".join(d.get("display_name") or d["email"] for d in doctors)
                       + ". It is not sent to them — they see it when they sign in. To "
                         "make sure they read it, send them the message below yourself.")
        else:
            st.caption("No care team yet, so no clinician sees this. Add your doctor on "
                       "the Card screen, or send them the message below yourself.")
        st.download_button("Download this as a message to my doctor",
                           data=liaison.message(me(), findings),
                           file_name="medvault-update-for-my-doctor.txt",
                           use_container_width=True)

    st.markdown(agentsui.heading(ui.section("Ask about your medicines and treatment"),
                                 "Companion"), unsafe_allow_html=True)
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
        slot = st.empty()
        slot.markdown(agentsui.working("Companion", "Reading your records",
                                       "Checking first whether this is a question a model "
                                       "should not answer at all"),
                      unsafe_allow_html=True)
        started = time.perf_counter()
        reply = ask.answer(con, my_id(), question)
        st.session_state["ask_log"].append(
            {"q": question, "a": reply,
             "took": agentsui.took(time.perf_counter() - started)})
        slot.empty()
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
