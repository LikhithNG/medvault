#!/usr/bin/env python3
"""Results over time, on the Records screen: each test's values from every record."""
import altair as alt
import pandas as pd
import streamlit as st

import trends
import ui
from session import visible_owners

MAX_TESTS = 30          # the most-measured first; a vault with more is scrolled, not drawn
# The Deep Iris tokens (theme_iris.py): the accent passes contrast on the card as a mark,
# and the axes wear the muted text token and the hairline, so the line is what is read.
ACCENT, MUTED, HAIRLINE, CARD = "#403CD5", "#5E5E86", "#ECECF3", "#FFFFFF"


def _chart(group):
    """One test's values as a line with a marker per result. Not pinned to zero: a line is
    read by its slope, and an A1c of 5.9 then 6.1 drawn from zero is a flat line."""
    unit = group["latest"].get("unit") or ""
    frame = pd.DataFrame({"Date": pd.to_datetime([p["date"] for p in group["points"]]),
                          "Result": [trends.number(p["value"]) for p in group["points"]]})
    base = alt.Chart(frame).encode(
        x=alt.X("Date:T", title=None, axis=alt.Axis(format="%b %Y", tickCount=4, grid=False,
                                                    labelColor=MUTED, domainColor=HAIRLINE, tickColor=HAIRLINE)),
        y=alt.Y("Result:Q", title=unit or None, scale=alt.Scale(zero=False, nice=True),
                axis=alt.Axis(tickCount=4, labelColor=MUTED, titleColor=MUTED, gridColor=HAIRLINE,
                              domain=False, ticks=False)),
        tooltip=[alt.Tooltip("Date:T", format="%-d %b %Y"),
                 alt.Tooltip("Result:Q", title=f"Result{f' ({unit})' if unit else ''}")])
    line = base.mark_line(color=ACCENT, strokeWidth=2)
    points = base.mark_point(color=ACCENT, filled=True, size=80, opacity=1, stroke=CARD, strokeWidth=2)
    return (line + points).properties(height=180).configure_view(strokeWidth=0)


def _table(points):
    return [{"Date": p["date"] or "no date", "Result": f"{p['value']} {p.get('unit') or ''}".strip(),
             "Range": p.get("reference_range") or "", "Flag": p.get("flag") or "",
             "From": p["record_title"] + (f" (and {p['sources'] - 1} more)" if p["sources"] > 1 else "")}
            for p in points]


def results_over_time(con):
    """Every test measured more than once, oldest value first, with a chart when the values
    are numbers in one unit. Nothing here judges a value: the flags are the lab's own."""
    groups = [g for g in trends.history(con, visible_owners()) if len(g["points"]) >= 2]
    if not groups:
        return
    st.markdown(ui.section(f"Results over time · {len(groups)} test{'' if len(groups) == 1 else 's'}"),
                unsafe_allow_html=True)
    st.caption("Each test's values from every record, oldest first. The same result filed twice "
               "is shown once. MedVault does not judge whether a result is normal.")
    for group in groups[:MAX_TESTS]:
        latest = group["latest"]
        unit = f" {latest['unit']}" if latest.get("unit") else ""
        with st.expander(f"{group['name']} · {len(group['points'])} results · latest {latest['value']}{unit}"):
            if group["chartable"]:
                st.altair_chart(_chart(group), use_container_width=True)
            st.dataframe(_table(group["points"]), hide_index=True, use_container_width=True)
