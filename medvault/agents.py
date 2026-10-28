#!/usr/bin/env python3
"""Which agent is which, and which Madison role each one plays.

The Assignment 2 architecture named three agents — Reader, Checker, Advocate — and mapped
them onto Madison's Intelligence, Research and Performance roles. That mapping lived on a
Figma board and nowhere in the code, so the word "Madison" appeared exactly zero times in
this project while three of its agents sat in it working.

This is the mapping, in the repo, as data. It is not a comment: tests/test_agents.py
resolves every module and entry point listed here, so renaming dispute.letter without
updating this file fails the suite rather than quietly making the architecture diagram
wrong.

Two more followed. The Scheduler takes Madison's **Content** role - the fifth and last
unused - because it composes something out of the records: a day's plan and a calendar.
The Liaison takes **Performance**, which it shares with the Advocate, and the sharing is
honest rather than forced: both carry findings out to a third party - one to a billing
office, one to a care team. Inventing a sixth role to keep every row unique would have
been tidier and less true.

A fourth agent exists that Assignment 2 did not plan for. MedVault grew a records vault
and a bot that answers questions about it, which is Madison's **Experience** role — the
one role of the five that the original design never used. It is listed here as what it is
rather than left off because it was not in the plan.

DOES NOT DO is a column on purpose. It was a column on the Assignment 2 board too, and it
is the half of an agent's description that stops it being asked to do the thing it must
not. The Checker never asks a model what a charge should cost; the Advocate never writes
a sentence a model produced; the Reader never decides what anything is worth.
"""

AGENTS = (
    {
        "name": "Reader",
        "madison": "Intelligence",
        "module": "extract",
        "entry": "read_document",
        "also": ("read_bill", "read_bill_verified"),
        "does": "Turn an uploaded photograph or PDF into structured line items and records.",
        "does_not": ("decide what anything should cost", "assign a verdict",
                     "produce any figure that reaches a patient"),
        "input": "an image or a text layer",
        "output": "line_items[] · kind, date, provider, title, summary, medications[]",
        "generative": True,
    },
    {
        "name": "Checker",
        "madison": "Research",
        "module": "checker",
        "entry": "check_bill",
        "also": ("check_line", "load_reference"),
        "does": "Compare each line against that hospital's own published price, on a "
                "stated basis, and assign a verdict with a receipt.",
        "does_not": ("call a model, ever", "estimate a price that is not published",
                     "report NOT_POSTED as an overcharge"),
        "input": "line_items[] + the reference table",
        "output": "verdict · amount_over · basis · source_url · collected_date",
        "generative": False,
    },
    {
        "name": "Advocate",
        "madison": "Performance",
        "module": "dispute",
        "entry": "letter",
        "also": (),
        "does": "Rank the findings by dollars at stake and build the letter, quoting the "
                "hospital's own figure and file for every line.",
        "does_not": ("write a sentence a model produced",
                     "quote a line without a complete receipt",
                     "claim money is owed back"),
        "input": "a reviewed bill + rights findings + record gaps",
        "output": "a sendable letter, ranked, every figure sourced",
        "generative": False,
    },
    {
        "name": "Companion",
        "madison": "Experience",
        "module": "ask",
        "entry": "answer",
        "also": ("brief", "triage", "context_pack"),
        "does": "Answer a patient's questions about their own records, and run the checks "
                "that need no model before any question is asked.",
        "does_not": ("advise on a dose", "judge whether something is safe",
                     "check drug interactions", "answer an emergency"),
        "input": "a question + that patient's own records",
        "output": "kind · answer · the records it cites",
        "generative": True,
    },
)

AGENTS = AGENTS + (
    {
        "name": "Scheduler",
        "madison": "Content",
        "module": "schedule",
        "entry": "plan",
        "also": ("parse", "times_for", "calendar", "next_due", "course_end"),
        "does": "Turn a prescription's frequency into today's doses and a calendar file "
                "that rings from the patient's own phone.",
        "does_not": ("schedule an as-needed medicine", "invent clinical timing",
                     "guess a frequency it cannot read",
                     "keep ringing after a course ends"),
        "input": "the patient's active medicines + the time their day starts",
        "output": "doses[] · as_needed[] · unreadable[] · a .ics calendar",
        "generative": False,
    },
    {
        "name": "Liaison",
        "madison": "Performance",
        "module": "liaison",
        "entry": "update",
        "also": ("follow_ups", "message"),
        "does": "Collect what a patient's own records say is outstanding - an overdue "
                "follow-up, an allergy collision, an untimeable dose - for the care team "
                "the patient chose.",
        "does_not": ("decide anybody needs care", "read a symptom or score a risk",
                     "report to a clinician the patient did not choose",
                     "send anything on the patient's behalf"),
        "input": "one patient's records + their care team",
        "output": "items[] each naming its source record · a message the patient sends",
        "generative": False,
    },
)

BY_NAME = {a["name"]: a for a in AGENTS}
MADISON_ROLES = tuple(a["madison"] for a in AGENTS)


def resolve(agent):
    """The actual callable this agent's entry point names. Raises if it has moved."""
    module = __import__(agent["module"])
    return getattr(module, agent["entry"])


def roster():
    """One line per agent, for the diagnostics screen."""
    return [f"{a['name']:<10} {a['madison']:<13} {a['module']}.{a['entry']}"
            f"{'  (model)' if a['generative'] else '  (deterministic)'}"
            for a in AGENTS]
