#!/usr/bin/env python3
"""The landing page, and the two doors into an account."""
import streamlit as st

import accounts
import agentsui
import landing
import npi
import providers
import ui
from session import vault


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
                        "<div class='panelhead' id='open-your-vault'>Open your vault</div>"
                        "<div class='panelsub'>Patients and clinicians both sign in "
                        "here. A clinician is checked against the national provider "
                        f"registry when the account is made.</div>"
                        f"<div class='panelsub'><b>{providers.SAMPLES_ONLY}</b></div>",
                        unsafe_allow_html=True)
            auth_panel()

    st.markdown(ui.section("What it does"), unsafe_allow_html=True)
    for col, feature in zip(st.columns(3, gap="medium"), landing.FEATURES):
        col.markdown(landing.feature(*feature), unsafe_allow_html=True)

    st.markdown(ui.section("Six agents, one job each"), unsafe_allow_html=True)
    st.caption("Green: no AI model, just arithmetic over a published file. Amber: an AI "
               "model reads or answers, inside limits that are written down.")
    st.markdown(agentsui.roster(), unsafe_allow_html=True)

    st.markdown(ui.section("How it works"), unsafe_allow_html=True)
    st.markdown(landing.steps(), unsafe_allow_html=True)
    st.markdown(landing.footer(), unsafe_allow_html=True)


def auth_panel():
    """Two doors. The clinician one goes through the national provider registry."""
    con = vault()
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
                    st.session_state["arrived"] = True     # see ui.to_top()
                    first = (acct.get("display_name") or "").split(" ")[0]
                    ui.flash(f"Welcome back{', ' + first if first else ''}.", icon="👋")
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
            st.markdown(ui.hint("Checked live against the national provider registry "
                                "(CMS).",
                                "This confirms the number is real, active and matches a "
                                "licence. It does not, on its own, prove you are that "
                                "person."), unsafe_allow_html=True)
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
                # The registry's own words, from an outside service: data, not markup.
                e = ui.esc
                st.markdown(
                    f"<div class='rec'><div class='title'>{e(record['specialty'] or '—')}</div>"
                    f"<div class='who'>Licence {e(record['license'] or '—')} "
                    f"{e(record['license_state'] or '')} · {e(record['city'])}, "
                    f"{e(record['state'])}</div></div>", unsafe_allow_html=True)

        st.markdown(ui.section("How you will sign in"), unsafe_allow_html=True)
        email2 = st.text_input("Email", key="su_email", placeholder="you@example.com")
        pw2 = st.text_input("Password", type="password", key="su_pw",
                            help="At least 8 characters. Nothing follows this field.")
        # The rule was only in the tooltip, so the first anybody saw of it was the error.
        st.caption("At least 8 characters.")

        if st.button("Create account", type="primary", use_container_width=True):
            acct, problem = accounts.create(con, email=email2, password=pw2, role=role,
                                            display_name=name2, npi_record=record)
            if problem:
                st.error(problem)
            else:
                st.session_state["account"] = acct
                st.session_state.pop("npi_record", None)
                st.session_state["arrived"] = True         # see ui.to_top()
                ui.flash("Account created. Start with your emergency card - it is the "
                         "screen someone reads if you cannot speak for yourself.", icon="🎉")
                st.rerun()
