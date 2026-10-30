#!/usr/bin/env python3
"""Drawing a checked bill: what the law may give you, the prices, your records, the letter.

Every function here draws from a finished run and computes nothing that changes it, so a
run drawn on a later click is identical to the one drawn when the button was pressed.
"""
import streamlit as st

import agentsui
import ui
from session import long_date, money


# The Checker's verdicts are written for a pipeline. A patient needs a sentence.
VERDICTS = {
    "ABOVE_POSTED":     ("Charged above the published price", "bad"),
    "QUANTITY_SUSPECT": ("Quantity looks wrong", "warn"),
    "DUPLICATE":        ("Billed more than once", "warn"),
    "NOT_POSTED":       ("No published price to compare", "warn"),
    "UNREADABLE":       ("Could not be read", "warn"),
}


def render_bill(run):
    """A checked bill, drawn from the run - the same whether it was checked this run or
    the one before."""
    if run["read"]:
        render_bill_read(run["read"], run["lines"])
    render_rights(run["protections"], run["still_open"])
    render_credits(run.get("credits") or [])
    render_face(run["face"])
    render_medicare(run.get("charges", run["lines"]), run["bench"], run["checker_took"])
    if run["priced"]:
        render_published(run["priced"])
    render_against_records(run["checked"], run["summary"])
    if run["letter"]:
        render_letter(run["letter"], run["letter_took"])
    render_bill_question(run)


def render_credits(credits):
    """Credits, and the charges they reversed, said out loud rather than dropped."""
    if not credits:
        return
    net = sum(c["charged"] for c in credits if isinstance(c.get("charged"), (int, float)))
    st.markdown(ui.hint(
        f"{len(credits)} line(s) set aside before checking: credits, and any charge a "
        f"credit reverses in full (net {money(net)}).",
        "A charge reversed on the same bill is not priced, compared or counted as a "
        "repeat - it was taken off. A credit that matches no charge is set aside too."),
        unsafe_allow_html=True)


def render_bill_read(read, lines):
    # The step log used to sit in a collapsed status box. The one line in it worth keeping
    # is the one that says the bill was read twice, because that is the reconciliation
    # working - so it survives as a caption.
    if read.get("attempts", 1) > 1:
        st.caption(f"Read {read['attempts']} times to check the lines added up to the "
                   "total printed on the bill.")
    read_total = sum(l["charged"] for l in lines)
    who = f" · read by {read['provider']}" if read.get("provider") else ""
    if read.get("reconciled") is True:
        st.success(f"Read **{len(lines)} charge(s)** totalling **${read_total:,.2f}**"
                   + (f" from {read['hospital']}" if read.get("hospital") else "")
                   + f" — and they add up to the total printed on the bill.{who}")
    else:
        # Never show a number from an unverified read without saying so. A truncated read
        # looks exactly like a short bill.
        st.warning(
            f"**Read {len(lines)} charge(s) totalling ${read_total:,.2f}, but could not "
            f"confirm that against a printed total.**\n\nCheck the list below against the "
            f"bill in your hand before trusting anything underneath it — if a line is "
            f"missing, the figures will be too low.")
    with st.expander("Check what was read", expanded=read.get("reconciled") is not True):
        for l in lines:
            st.markdown(f"<div class='rec'><div class='top'>"
                        f"<span class='pill'>{ui.safe(l['code'] or 'no code')}</span>"
                        f"<span class='when'>{ui.safe(l['service_date'] or 'no date')}"
                        f"</span></div><div class='title'>${l['charged']:,.2f}</div>"
                        f"<div class='who'>{ui.safe(l['description'])} · qty "
                        f"{ui.safe(l['units'])}"
                        + (f" · page {ui.safe(l['page'])}" if l.get("page") else "")
                        + "</div>"
                        f"</div>", unsafe_allow_html=True)


def render_rights(protections, still_open):
    """What the law may already give you, before any price is compared."""
    if protections:
        st.markdown(ui.section(f"What the law may already give you · {len(protections)}"),
                    unsafe_allow_html=True)
        for i, f in enumerate(protections):
            tone = "bad" if f["severity"] == "high" else "warn"
            st.markdown(f"<div class='hit {tone} ag-in {agentsui.arrive(i)}'>"
                        f"<div class='h'>{f['title']}</div>"
                        f"<div class='b'>{f['means']}<br><br><b>What to do:</b> {f['todo']}"
                        f"<br><span style='opacity:.7'>{f['source']}</span></div></div>",
                        unsafe_allow_html=True)
    if still_open:
        st.caption("Not checked, because you have not said: " + ", ".join(still_open)
                   + ". That is not the same as having no protection.")


def render_face(face):
    """Things wrong with the bill on its own face."""
    if not face:
        return
    st.markdown(ui.section(f"Wrong on the bill's own face · {len(face)}"),
                unsafe_allow_html=True)
    for i, f in enumerate(face):
        st.markdown(f"<div class='hit warn ag-in {agentsui.arrive(i)}'><div class='h'>"
                    f"{ui.safe(f['title'])}</div><div class='b'>{ui.safe(f['detail'])}"
                    f"<br><br><b>Ask:</b> {ui.safe(f['ask'])}</div></div>",
                    unsafe_allow_html=True)


def render_medicare(lines, bench, checker_took):
    """The national benchmark, which works for any CPT code.

    The 262-row table covers nine hospitals. This covers every CPT code there is, so a
    bill from anywhere gets an answer to "is this the right amount" rather than silence.
    """
    import medicare
    named = {c: b for c, b in bench.items() if b.get("found")}
    if not named:
        return
    st.markdown(agentsui.heading(ui.section("Against the national Medicare allowance"),
                                 "Checker", checker_took), unsafe_allow_html=True)
    st.markdown(ui.hint("What Medicare allows for the same code. <b>Not a price cap</b> — "
                        "context for the conversation, not proof of an overcharge.",
                        "A hospital may charge a commercial patient more than Medicare "
                        "allows, and usually does."), unsafe_allow_html=True)
    rows = []
    for l in lines:
        b = named.get((l.get("code") or "").upper())
        if not b or not b.get("medicare_rate"):
            continue
        mult = medicare.multiple_of_medicare(l.get("charged"), l.get("units"),
                                             b["medicare_rate"])
        rows.append((mult or 0, l, b, mult))
    for i, (_, l, b, mult) in enumerate(sorted(rows, key=lambda t: -t[0])):
        tone = "bad" if (mult or 0) >= 10 else "warn" if (mult or 0) >= 3 else "ok"
        times = (f"<b>{mult:g}× the Medicare allowance</b>" if mult
                 else "could not be compared")
        st.markdown(
            f"<div class='hit {tone} ag-in {agentsui.arrive(i)}'>"
            f"<span class='amt'>{money(l.get('charged'))}</span>"
            f"<div class='h'>{ui.safe(b['name'])}</div><div class='b'>"
            f"<b>{ui.safe(l.get('code'))}</b> · billed as "
            f"“{ui.safe((l.get('description') or '')[:40])}”"
            f"{f' · qty {l["units"]}' if (l.get('units') or 1) > 1 else ''}<br>"
            f"Medicare allows {money(b['medicare_rate'])}"
            f"{f' per unit' if (l.get('units') or 1) > 1 else ''} — {times}."
            + f"<br><span style='opacity:.65'>Source: CMS "
              f"{str(b.get('dataset','')).replace('CMS_','').replace('_',' ')}, "
              f"{b.get('effective_year','')}</span></div></div>",
            unsafe_allow_html=True)

    missing = [c for c, b in bench.items() if not b.get("found")]
    if missing:
        st.caption(f"{len(missing)} code(s) are not in the national fee schedule and "
                   f"could not be benchmarked: {', '.join(sorted(missing))}. It covers "
                   f"CPT; HCPCS codes such as J- and A-codes are outside it.")


def render_published(priced):
    """What this particular hospital publishes."""
    c1, c2, c3 = st.columns(3)
    c1.metric("You were billed", f"${priced['billed_total']:,.2f}")
    c2.metric("They publish", f"${priced['posted_total']:,.2f}")
    c3.metric("Unexplained", f"${priced['questionable_amount']:,.2f}")
    # The date was hardcoded here. The table carries collected_date on every row, so the
    # caption reads it: a refreshed table moves this line instead of silently leaving a
    # stale date on screen.
    collected = sorted({l["collected_date"] for l in priced["lines"]
                        if l.get("collected_date")})
    when = (" · ".join(long_date(d) for d in collected) if collected
            else "an undated table")
    st.caption("A gap to ask about — not money you are owed, and not a refund "
               f"estimate. Published prices collected {when}; a hospital may have "
               "republished since.")

    # Attached to every flag since the Checker was written. The PRD promised it as what
    # this screen says when a price file cannot settle a line: what CMS's own
    # price-transparency file records about this hospital (see enforcement_note).
    #
    # Three states, not two. A hospital the file was never joined to is not a hospital
    # with a clean record, and saying "no entries" for one would be the same mistake this
    # app refuses to make about a missing medical record.
    kind, head, why = enforcement_note(priced["lines"])
    if kind == "hint":
        st.markdown(ui.hint(head, why), unsafe_allow_html=True)
    else:
        st.caption(head)

    flagged_lines = [l for l in priced["lines"] if l["verdict"] != "VERIFIED"]
    if not flagged_lines:
        return
    # "Above the published price" was wrong as a heading: this section also carries
    # duplicates, suspect quantities and codes with no published price.
    st.markdown(ui.section(f"Checked against the published prices · "
                           f"{len(flagged_lines)} flagged"), unsafe_allow_html=True)
    for i, l in enumerate(sorted(flagged_lines, key=lambda x: -(x.get("charged") or 0))):
        label, tone = VERDICTS.get(l["verdict"], ("Checked", "warn"))
        over = (f" · <b>{money(l['amount_over'])} above</b>"
                if l.get("amount_over") else "")
        # The Checker leaves posted_price empty on a duplicate row - the price is on the
        # first instance of that code. Saying "no published price" because this
        # particular row lacks one told the reader the hospital publishes nothing for
        # 99284 while the row above it showed $1,605.00.
        price = l.get("posted_price")
        if price is None and l.get("code"):
            price = next((o.get("posted_price") for o in priced["lines"]
                          if o.get("code") == l["code"] and o.get("posted_price")),
                         None)
        posted = (f"They publish {money(price)} for this code" if price else
                  "No published price for this code — worth asking about")
        # The receipt, on the card rather than only in the letter: which of the hospital's
        # three published numbers this was compared against, and when that file was
        # collected.
        cite = (f"<br><span style='opacity:.65'>Compared against their "
                f"{l['basis']}, collected {long_date(l['collected_date'])}</span>"
                if l.get("basis") and l.get("collected_date") else "")
        st.markdown(
            f"<div class='hit {tone} ag-in {agentsui.arrive(i)}'>"
            f"<span class='amt'>{money(l['charged'])}</span>"
            f"<div class='h'>{label}</div><div class='b'>"
            f"<b>{ui.safe(l.get('code') or '—')}</b> "
            f"{ui.safe(l.get('description', '')[:48])} · "
            f"qty {l.get('units',1)}<br>{posted}{over}{cite}</div></div>",
            unsafe_allow_html=True)


def _backed_by(row):
    """The record a matched line was found in, for printing on that line."""
    found = row.get("matches") if row.get("verdict") == "MATCHED" else None
    return f"<i>backed by “{ui.safe(found[0]['title'])}”</i>" if found else None


def enforcement_note(lines):
    """What CMS's price-transparency file holds for this hospital, said as what it is.

    The count is every entry the file has - warnings, demands for a corrective plan and
    fines, but also closure notices and findings that the hospital met the rule. It was
    shown as "enforcement actions against this hospital", which the demo hospital's own
    entries (latest: a Closure Notice) did not support. Returns (kind, head, why).
    """
    matched = next((l.get("enforcement_match") for l in lines if l.get("enforcement_match")),
                   "none")
    if matched == "none":
        return ("hint", "No CMS price-transparency record found for this hospital — <b>that "
                "is not a clean record</b>.",
                "It could not be matched to CMS's price-transparency file by name and state. "
                "That usually means CMS lists the hospital under a slightly different name.")
    n = max((l.get("hospital_enforcement_actions") or 0) for l in lines) if lines else 0
    if not n:
        return ("caption", "CMS's price-transparency file has no entries for this hospital.",
                None)
    latest = next((l for l in lines if l.get("hospital_latest_cms_action")), {})
    when = latest.get("hospital_latest_action_date")
    said = (f", the latest a {ui.safe(latest['hospital_latest_cms_action'])}"
            + (f" on {long_date(when)}" if when else "")) if latest else ""
    return ("hint", f"CMS's price-transparency file has <b>{n} {'entry' if n == 1 else 'entries'}"
            f"</b> for this hospital{said}.",
            "CMS records each review of whether a hospital published its prices: warnings, "
            "demands for a corrective plan, fines, and closures once it is resolved. It is "
            "about the price file, not your bill.")


def render_against_records(checked, summary):
    import crosscheck
    # A bill with no dates on it produced one identical "no date to check against" card per
    # line, under a heading that said nothing was found - four cards saying the same thing
    # beneath "0 of 4". When nothing is dated, that is one fact about the bill, not N.
    undated = [r for r in checked if r["verdict"] == "UNDATED"]
    if len(undated) == len(checked) and checked:
        st.markdown(ui.section("Against your records"), unsafe_allow_html=True)
        st.markdown(
            "<div class='hit warn'><div class='h'>No dates on this bill to check against"
            "</div><div class='b'>None of these lines carries a service date, so none of "
            "them can be matched to your records. Ask the billing office for a statement "
            "with dates — it is the single thing that makes the rest of this checkable."
            "</div></div>", unsafe_allow_html=True)
    else:
        worth_showing = [r for r in checked if r["verdict"] != "UNDATED"]
        st.markdown(ui.section(f"{summary['unsupported']} of {summary['lines']} lines "
                               "have nothing behind them"), unsafe_allow_html=True)
        if undated:
            st.caption(f"{len(undated)} line(s) carry no date and could not be checked "
                       f"either.")
        # Grouped by verdict and date. "You have records from 14 Mar 2026 (Basic metabolic
        # panel, Chest X-ray) and none of them mentions it" is a fact about that day, not
        # about each line - printed per card it filled the screen with four copies of the
        # same sentence and buried the one thing that differed, which is the line itself.
        groups = {}
        for r in worth_showing:
            groups.setdefault((r["verdict"], r.get("service_date")), []).append(r)

        for i, ((verdict, when_), rows) in enumerate(groups.items()):
            label, tone = crosscheck.VERDICTS[verdict]
            head = f"{label}{f' · {when_}' if when_ else ''}"
            if verdict == "DATE_NO_MATCH" and rows[0].get("matches"):
                found = rows[0]["matches"]
                held = ", ".join(f"“{ui.safe(m['title'])}”" for m in found[:3]) + (
                    f" and {len(found) - 3} more" if len(found) > 3 else "")
                why = (f"You have {len(found)} record(s) from that day "
                       f"({held}) and none of them covers the charge"
                       f"{'s' if len(rows) > 1 else ''} below.")
            elif verdict == "NO_RECORD":
                gap = rows[0].get("nearest_days")
                why = ("You have filed nothing from that date"
                       + (f" — your closest record is {gap} days away" if gap else "")
                       + ". That may simply be paperwork you never received.")
            elif verdict == "MATCHED":
                # Which record backs a line is a fact about the line, not the day. Said once
                # for the group, the first line's record was printed over all of them - a
                # metabolic panel shown as "supported by your chest X-ray".
                why = "Each line is backed by a record you filed, named beside it."
            else:
                why = ui.safe(rows[0]["ask"])

            body = "".join(
                f"<div class='b' style='margin-top:.45rem'>"
                f"<span class='amt'>${r['charged']:,.2f}</span>"
                + " · ".join(filter(None, [
                    f"<b>{ui.safe(r['code'])}</b>" if r.get("code") else None,
                    ui.safe((r.get("description") or "")[:46]) or None,
                    _backed_by(r)]))
                + "</div>" for r in rows)

            st.markdown(f"<div class='hit {tone} ag-in {agentsui.arrive(i)}'>"
                        f"<div class='h'>{head}</div>"
                        f"<div class='b'>{why}</div>{body}</div>",
                        unsafe_allow_html=True)
    st.markdown(f"<div class='note'>{summary['caveat']}</div>", unsafe_allow_html=True)


def render_letter(text, letter_took):
    st.markdown(agentsui.heading(ui.section("A letter you can send"), "Advocate",
                                 letter_took), unsafe_allow_html=True)
    st.caption("Built from the figures above directly — not written by a model, so "
               "nothing in it can drift from what this screen showed you.")
    with st.expander("Read it"):
        st.text(text)
    st.download_button("Download the letter", data=text,
                       file_name="medvault-dispute-letter.txt",
                       use_container_width=True)


def render_bill_question(run):
    st.markdown(ui.section("Ask about this bill"), unsafe_allow_html=True)
    st.markdown(ui.hint("Answers come from the findings above, not from an AI model.",
                        "So it can only tell you what the checks actually established, and "
                        "it says when it does not know."), unsafe_allow_html=True)
    question = st.text_input("Ask", key="ask_q", label_visibility="collapsed",
                             placeholder="why is 72148 flagged?  ·  what do I do next?")
    if question.strip():
        import explain
        reply = explain.answer(question, {"priced": run["priced"],
                                          "rights": run["protections"],
                                          "face": run["face"],
                                          "crosschecked": run["checked"]})
        # Streamlit reads a pair of dollar signs as maths, so "$9,374.04 for 1 unit.
        # This hospital publishes $6,009.00" came out as italic run-together letters.
        # Nobody had seen it, because until this screen kept its findings the answer
        # never got as far as being drawn.
        st.markdown((reply or "").replace("$", "\\$"))
