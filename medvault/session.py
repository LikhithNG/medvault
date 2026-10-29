#!/usr/bin/env python3
"""Who is signed in, whose records they may see, and the connection to the vault.

Every screen scopes its data through these, so they live in one place. The connection is
looked up each time it is needed rather than held at import: Streamlit keeps imported
modules alive between runs, and a module-level connection would outlive the vault it was
opened on - which is exactly what the tests do when they swap in a throwaway one.
"""
import datetime
import os

import streamlit as st

import accounts
import careteam
import db
import quota


# No spinner. Each screen now asks for the connection itself, and a cached call with a
# spinner leaves an invisible placeholder on the page every time it is made - which moved
# every element after it, so the same screen drew a different element tree on the next
# run than it did on this one.
@st.cache_resource(show_spinner=False)
def vault():
    return db.connect()


def money(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"


def long_date(iso):
    """2026-10-02 -> 2 October 2026. The date is read from the data; only its shape is
    written here, so a refreshed table moves the sentence instead of contradicting it."""
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%-d %B %Y")
    except (TypeError, ValueError):
        return str(iso)


def clinician_view():
    """A clinician reviews their care team's patients; a patient only ever sees their own."""
    return accounts.is_verified_clinician(st.session_state.get("account"))


def visible_owners():
    """Whose records this account may see. Always a list - never "everyone".

    A patient sees their own. A clinician sees the patients who put them on their care
    team, and nobody else: this used to be None for a clinician, which the storage layer
    read as every record on the server.
    """
    con = vault()
    if clinician_view():
        return [p["id"] for p in careteam.patients(con, my_id())]
    return [my_id()]


def me():
    """The signed-in account. Every data call is scoped through this."""
    return st.session_state.get("account") or {}


def my_id():
    return me().get("id")


def ai_allowance():
    """Today's AI reads for whoever is signed in, saying so on screen when it matters:
    a count when only a few are left, a warning when none are.

    Looked up once per run and shared by the three screens that show it - every tab runs
    on every click, and each lookup is a round trip to the remote database. app.py drops
    it at the top of each run. It decides what is drawn, never whether a read happens:
    that is quota.take, at the moment of the read.
    """
    standing = st.session_state.get("ai_standing")
    if standing is None:
        standing = quota.allowance(vault(), me())
        st.session_state["ai_standing"] = standing
    line = quota.note(standing)
    if line:
        (st.warning if standing.refused else st.caption)(line)
    return standing


def reader_ready():
    """Whether a document can be read at all, and why not when it cannot."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return False, "no reading key is configured on this server"
    if "…" in key or key in {"your-key", "AIza…", "changeme"}:
        return False, "the reading key is still placeholder text"
    return True, None


def when(rec):
    return rec.get("service_date") or "no date on file"
