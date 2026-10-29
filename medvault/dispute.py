#!/usr/bin/env python3
"""The Advocate - Madison **Performance**: the letter a patient can put in
front of a billing office.

Written from the Checker's figures directly, not by a model. Every number in it came out
of deterministic code reading a published price file, so there is nothing here that can
drift from what the screen showed - which is the whole reason it is a template and not a
generated paragraph.
"""
import datetime

import receipts

VERDICT_LINE = {
    "ABOVE_POSTED": ("{code} — {desc}\n"
                     "    Billed {charged}. Your published price for this code is {posted}.\n"
                     "    Difference: {over}."),
    "QUANTITY_SUSPECT": ("{code} — {desc}\n"
                         "    Billed {charged} for {units} units. This is normally provided "
                         "once per visit.\n"
                         "    Your published price is {posted} per unit."),
    "DUPLICATE": ("{code} — {desc}\n"
                  "    Billed {charged}. This code is billed more than once on the same day."),
    "NOT_POSTED": ("{code} — {desc}\n"
                   "    Billed {charged}. This code is not in your published standard-charge "
                   "file, so I cannot check it."),
}


def money(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"


def letter(reviewed, patient_name=None, rights_findings=None, account=None,
           record_gaps=None):
    """A dispute letter. Returns plain text."""
    hospital = reviewed.get("hospital_name") or "the billing office"
    today = datetime.date.today().strftime("%d %B %Y")
    flagged = [l for l in reviewed["lines"] if l["verdict"] != "VERIFIED"]

    out = [f"{today}", "", "To the billing office,", f"{hospital}", ""]
    if account:
        out += [f"Account: {account}", ""]
    out += [
        "I am writing about the itemised statement below. I have compared it against the",
        "standard-charge file your hospital publishes under 45 CFR 180, and I have",
        "questions about the following lines.",
        "",
        f"Billed on this statement:        {money(reviewed['billed_total'])}",
        f"Your published prices total:     {money(reviewed['posted_total'])}",
        f"Difference I am asking about:    {money(reviewed['questionable_amount'])}",
        "",
        "Lines in question",
        "-----------------",
    ]

    # Ranked by dollars at stake rather than by the order the bill happened to list them.
    # A billing office reads the first entry and skims the rest, so the $4,000 line cannot
    # be third because it was printed third.
    def at_stake(line):
        return line.get("amount_over") or line.get("charged") or 0

    quotable, withheld = receipts.quotable(sorted(flagged, key=at_stake, reverse=True))

    for l in quotable:
        tmpl = VERDICT_LINE.get(l["verdict"])
        if not tmpl:
            continue
        out.append(tmpl.format(
            code=l.get("code") or "—", desc=(l.get("description") or "")[:56],
            charged=money(l.get("charged")), posted=money(l.get("posted_price")),
            over=money(l.get("amount_over")), units=l.get("units", 1)))
        if l.get("source_url"):
            out.append(f"    Source: your {l['basis']} for this code, published at")
            out.append(f"    {l['source_url']} (collected {l['collected_date']}).")
        out.append("")

    # A line that asserts a dollar comparison without a complete receipt is not quoted.
    # Said out loud rather than dropped: an earlier version of this letter silently lost a
    # flagged line, and a letter that quietly shrinks is worse than one that explains.
    if withheld:
        out += [f"({len(withheld)} further line(s) looked wrong but are not listed here, "
                f"because I could not trace a published figure for them to a source I can "
                f"cite. I am not asserting anything about those.)", ""]

    if record_gaps:
        out += ["Charges I have no record of",
                "---------------------------",
                "I keep my own copies of the paperwork from my care. The lines below do",
                "not correspond to anything I hold. That may simply be paperwork I was",
                "never given, which is why I am asking rather than disputing.", ""]
        for g in record_gaps:
            who = " ".join(filter(None, [g.get("code"), (g.get("description") or "")[:40]]))
            out.append(f"{who or 'Line'} — {money(g.get('charged'))}"
                       + (f", {g['service_date']}" if g.get("service_date") else ""))
        out.append("")

    if rights_findings:
        out += ["Separately", "----------"]
        for f in rights_findings:
            out += [f"{f['title']}", f"    {f['todo']}", f"    ({f['source']})", ""]

    out += [
        "Please send me a written explanation of each line above, and a corrected",
        "statement if any of them is wrong. I am not disputing that I received care —",
        "I am asking how these amounts were arrived at.",
        "",
        "Please confirm in writing that collection activity is paused while this is",
        "under review.",
        "",
        "Thank you,",
        patient_name or "",
    ]
    return "\n".join(out)
