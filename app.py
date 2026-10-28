#!/usr/bin/env python3
"""MedVault — every piece of your medical paperwork, on the phone in your pocket.

Built phone-first. The question behind every screen is "could someone hold this up at a
hospital desk and have it be useful", which is a harder test than "does it look like an app".

This file is the shell: it loads the credentials before anything else can read them,
draws the stylesheet, and puts each screen behind its tab. The screens are in
medvault/screen_*.py, and who is signed in is in medvault/session.py. Streamlit reruns
this file on every click but does not reload the modules it imports; medvault/freshness.py
is what makes a deploy that changes them take effect without a reboot.
"""
import os
import pathlib
import sys

import streamlit as st

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE / "medvault") not in sys.path:      # once, not once per click
    sys.path.insert(0, str(HERE / "medvault"))

st.set_page_config(page_title="MedVault — your records, and the bill that follows",
                   page_icon=str(HERE / "static" / "icon-192.png"),
                   layout="centered", initial_sidebar_state="collapsed")

# Every setting that may come from a hosting platform's secrets rather than from .env.
# Streamlit puts secrets in st.secrets and NOT in os.environ, so anything missing from
# this tuple is silently ignored when deployed - which has now happened twice. It cost
# Itemized a working reader (GEMINI_API_KEY was omitted) and cost MedVault a working
# database (both TURSO keys were omitted, so a vault with a real database behind it went
# on quietly writing to a disk that gets wiped). tests/test_secrets.py reads the source
# for environment lookups and fails when one is not listed here.
SECRET_KEYS = ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_POOL", "GEMINI_TIMEOUT",
               "GEMINI_DEADLINE",
               "GROQ_API_KEY", "GROQ_MODEL", "GROQ_POOL", "GROQ_TIMEOUT",
               "POOL_RETIRE_SECONDS", "MEDVAULT_MAX_EDGE",
               "MEDVAULT_DB", "MEDVAULT_HOSTED", "MEDVAULT_MEDICARE_CACHE",
               "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "TURSO_TIMEOUT")
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


    # Groq serves open models. This key cannot reach llama-3.3-70b, which groq.py would
    # otherwise fall back to and collect a 404 from, so the pool is set to what it serves.
    os.environ.setdefault("GROQ_MODEL", "openai/gpt-oss-120b")
    os.environ.setdefault("GROQ_POOL",
                          "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b")


_load_credentials()

# Before any medvault import: if a push changed the code under medvault/, drop the old
# modules so the imports below load the new ones, and drop the cached connection the old
# db.py opened. Without this, the newest app.py ran against modules from pushes ago and
# took the site down - see medvault/freshness.py.
import freshness               # noqa: E402
if freshness.ensure(HERE / "medvault"):
    st.cache_resource.clear()
    st.cache_data.clear()

import accounts                # noqa: E402
import db                      # noqa: E402
import store                   # noqa: E402
import ui                      # noqa: E402

st.markdown(ui.CSS, unsafe_allow_html=True)
import agentsui                # noqa: E402
st.markdown(agentsui.CSS, unsafe_allow_html=True)

import pwa                     # noqa: E402
pwa.install()                  # home-screen icon and standalone launch on a phone

from screen_ask import screen_ask                                            # noqa: E402
from screen_bill import screen_check                                         # noqa: E402
from screen_card import care_team_panel, screen_card, sign_out, vault_transfer  # noqa: E402
from screen_medicines import screen_medicines                                # noqa: E402
from screen_records import screen_add, screen_records                        # noqa: E402
from screen_review import screen_review                                      # noqa: E402
from screen_signin import screen_signin                                      # noqa: E402
from session import reader_ready, vault, visible_owners                     # noqa: E402

con = vault()


# ------------------------------------------------------------------ shell ----

# The header's "Sign out" link. Following it reloads the page, which already leaves the
# session behind; this makes sure, and takes the request out of the address bar.
if st.query_params.get("signout"):
    st.session_state.clear()
    st.query_params.clear()
    ui.flash("Signed out.", icon="👋")
ui.show_flash()

account = st.session_state.get("account")
if not account:
    screen_signin()
    if st.session_state.pop("arrived", False):
        ui.to_top()
    st.stop()

# The header count is scoped like everything else. It used to be the whole server for a
# clinician - a count, not records, but still a number about patients who never chose
# them, and the line a source-scanning test missed because it spelled the check
# differently from the rest.
total = sum(db.counts_by_kind(con, owner_ids=visible_owners()).values())
st.markdown(ui.appbar(ui.signed_in_strip(
    account, meta=f"{total} record{'' if total == 1 else 's'}")), unsafe_allow_html=True)

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
    tabs = st.tabs(["Card", "Add", "Records", "Medicines", "Bill", "Ask"])
    with tabs[0]:
        screen_card()
        care_team_panel()
        vault_transfer(account)
        sign_out()
    with tabs[1]: screen_add()
    with tabs[2]: screen_records()
    with tabs[3]: screen_medicines()
    with tabs[4]: screen_check()
    with tabs[5]: screen_ask()

if st.session_state.pop("arrived", False):
    ui.to_top()

if st.query_params.get("diag"):
    st.divider()
    st.markdown("#### Agents")
    st.caption("Which agent plays which Madison role, read out of `medvault/agents.py`. "
               "Every entry point below is resolved by `tests/test_agents.py`, so this "
               "cannot drift from the code without the suite failing.")
    import agents as agent_registry
    import runtime
    for line in agent_registry.roster():
        st.text(line)

    # How the agents have actually behaved, from runtime.span's trace. Timing and outcome
    # only - the trace holds nothing about whose run it was or what it read.
    st.markdown("#### Agent runs")
    report = runtime.summary(con)
    if not report:
        st.caption("No agent runs recorded yet on this server.")
    for row in report:
        st.text(f"{row['agent']:<10} {row['runs']:>5} runs · {row['ok_rate']:.0%} ok · "
                f"p50 {row['p50']:.2f}s · p95 {row['p95']:.2f}s of {row['budget_s']}s · "
                f"{row['over_budget']} over budget"
                + (f" · last failure: {row['last_failure']}" if row['last_failure'] else "")
                + (f" · {', '.join(row['models'])}" if row['models'] else ""))

    st.markdown("#### What leaves this server")
    for agent in agent_registry.AGENTS:
        st.text(f"{agent['name']:<10} " + ("; ".join(agent["egress"]) or "nothing"))

    st.markdown("#### Server diagnostics")
    for note in CRED_TRACE:
        st.text(note)
    ready, why = reader_ready()
    st.text(f"reader · {'ready' if ready else why}")
    st.text(f"vault  · {store.describe()}")
    st.text(f"local  · {db.DEFAULT_PATH}")
