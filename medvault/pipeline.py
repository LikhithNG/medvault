#!/usr/bin/env python3
"""The bill pipeline, without a screen.

Once a bill's lines are known - read off a photo by the Reader, or pasted - the rest is
one hand-off: the Checker prices every line, three checks that belong to no agent look at
the law, the bill's own face and the patient's records, and the Advocate writes a letter
if anything was flagged. That sequence used to be written inside the Bill screen, between
calls that drew the relay, so the only way to run it was to render a Streamlit page.

Here it is a function. It takes plain data and returns plain data, and it reports
progress as events - which agent, what state, how long - so a screen can draw a relay
from them, a test can assert on them, and a script can ignore them. It imports nothing
from Streamlit and nothing that draws.

Every agent runs inside runtime.span, so each run is timed, held against its budget in
agents.py and, given a connection, recorded.
"""
import runtime


def _emit(on_step, agent, state, **detail):
    if on_step is not None:
        on_step({"agent": agent, "state": state, **detail})


def _with_pages(priced, lines):
    """The Checker's lines, each given back the page its bill line was printed on.

    The Checker returns one line per line it was given, in order, and builds each from a
    fixed set of fields - checker.py is kept byte-identical to the module the Assignment 4
    figures came from - so the page is carried across here rather than through it.
    """
    return {**priced, "lines": [{**checked, "page": line["page"]} if line.get("page")
                                else checked
                                for checked, line in zip(priced["lines"], lines)]}


def check_lines(lines, *, hospital, ctx, records, patient_name, price_table,
                on_step=None, trace=None):
    """Price, check and, if warranted, write about these bill lines.

    `hospital` is the display name of the hospital whose published file to price against,
    or None. `price_table` is checker.load_reference()'s result. `ctx` comes from
    rights.context(). `records` are the patient's own, already scoped to them.

    Events passed to `on_step` are dicts with "agent" and "state" ("work", "done" or
    "skip"), plus "seconds" when an agent finishes and "flagged"/"priced" for the Checker.
    """
    import billchecks
    import checker
    import crosscheck
    import dispute
    import medicare
    import rights

    runs = {}

    # Credits, and the charges they reverse in full, are set aside before anything is
    # priced, checked for repeats or added up: a reversal used to be a second charge.
    lines, credits = billchecks.net_of_credits(lines)

    # ---- the Checker: every line against Medicare, and against the hospital's own file
    _emit(on_step, "Checker", "work", lines=len(lines), hospital=hospital)
    with runtime.span("Checker", trace=trace, done=lambda r: runs.update(Checker=r)):
        bench = medicare.lookup_many([l.get("code") for l in lines])
        priced = None
        if hospital:
            # The table is keyed on a lowercased name; the letter must not be addressed to it.
            priced = checker.check_bill(
                {"hospital_name": hospital,
                 "line_items": [{"code": l.get("code") or "", "description": l["description"],
                                 "units": l.get("units") or 1, "charged": l["charged"],
                                 "service_date": l.get("service_date")}
                                for l in lines]},
                price_table)
            priced = _with_pages(priced, lines)
    flagged = (priced.get("flagged_count") or 0) if priced else 0
    _emit(on_step, "Checker", "done", seconds=runs["Checker"].seconds, flagged=flagged,
          priced=priced is not None)

    # ---- the checks that are not an agent's: the law, the bill's own face, your records
    bill_total = round(sum(float(l.get("charged") or 0) for l in lines), 2)
    protections = rights.evaluate(lines, bill_total, ctx)
    # A repeated code is found from the bill alone, for every bill. When a hospital was
    # chosen the Checker reports it too, beside that hospital's price - so it is said there,
    # once, and not again here.
    face = [f for _, f in billchecks.run(lines)
            if not (priced and f["rule"] == "duplicate")]
    checked, summary = crosscheck.check_bill(lines, records)

    # ---- the Advocate, when there is something to put in a letter
    letter = None
    if flagged:
        _emit(on_step, "Advocate", "work")
        with runtime.span("Advocate", trace=trace, done=lambda r: runs.update(Advocate=r)):
            letter = dispute.letter(
                priced, patient_name=patient_name, rights_findings=protections,
                record_gaps=[c for c in checked
                             if c["verdict"] in ("NO_RECORD", "DATE_NO_MATCH")])
        _emit(on_step, "Advocate", "done", seconds=runs["Advocate"].seconds)
    else:
        _emit(on_step, "Advocate", "skip", priced=priced is not None)

    return {"bench": bench, "priced": priced, "flagged": flagged,
            "charges": lines, "credits": credits,
            "checker_seconds": runs["Checker"].seconds,
            "protections": protections, "still_open": rights.unanswered(ctx),
            "face": face, "checked": checked, "summary": summary, "letter": letter,
            "letter_seconds": runs["Advocate"].seconds if "Advocate" in runs else None}
