#!/usr/bin/env python3
"""Answers questions about a bill, using only what the checks actually established.

This is deliberately not a language model, and that is the design rather than a shortcut.

A generative bot asked "why is this charge wrong?" will produce a fluent paragraph whether
or not it knows, and on a medical bill a fluent wrong paragraph is what sends somebody into
a billing office quoting a figure that falls apart under one question. Everything this
module says is read out of the findings the deterministic checks produced: it can be wrong
only if the Checker was wrong, and it can never invent a number.

The cost is that it answers a bounded set of questions. When it does not understand one it
says so and lists what it can answer, which is a better failure than a confident guess.
"""
import re

from checker import load_reference  # noqa: F401  (kept for callers that want the table)


def _m(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"


# What a verdict means, in a sentence a patient can use. Deliberately the same wording the
# cards use, so an answer never contradicts the screen it was asked about.
VERDICT_MEANING = {
    "ABOVE_POSTED": ("This line costs more than the price the hospital publishes for that "
                     "code in its own standard-charge file."),
    "QUANTITY_SUSPECT": ("This is billed many times over for something a single visit does "
                         "not usually repeat. The rate may be right and the count wrong."),
    "DUPLICATE": ("This code appears more than once on the statement. Sometimes that is "
                  "legitimate — two bags of saline in one visit is ordinary — so it is a "
                  "question rather than an established error."),
    "NOT_POSTED": ("The hospital does not publish a price for this code, so there is "
                   "nothing to compare it against. That is worth asking about on its own."),
    "VERIFIED": "This line matches the price the hospital publishes. Nothing to raise.",
    "UNREADABLE": "This line could not be read clearly enough to check.",
}


def _lines(state):
    priced = state.get("priced") or {}
    return priced.get("lines") or []


def _find_code(question):
    m = re.search(r"\b([A-Z]\d{4}|\d{5}|\d{4}[A-Z])\b", question.upper())
    return m.group(1) if m else None


# ---- the answers -----------------------------------------------------------

def _about_a_code(q, state):
    code = _find_code(q)
    if not code:
        return None
    line = next((l for l in _lines(state) if (l.get("code") or "").upper() == code), None)
    if not line:
        return (f"**{code} is not on the bill you checked.** The codes on it are "
                + ", ".join(sorted({l["code"] for l in _lines(state) if l.get("code")}))
                + "." if _lines(state) else
                f"**{code} is not on the bill you checked.**")

    out = [f"**{code} — {line.get('description') or 'no description printed'}**", ""]
    out.append(f"Billed {_m(line.get('charged'))} for {line.get('units', 1)} unit(s).")
    if line.get("posted_price"):
        out.append(f"This hospital publishes {_m(line['posted_price'])} for it.")
    if line.get("amount_over"):
        out.append(f"That is **{_m(line['amount_over'])} above** the published price.")
    out += ["", VERDICT_MEANING.get(line["verdict"], "")]
    if line.get("source_url"):
        out += ["", f"Source: the standard-charge file this hospital publishes."]
    return "\n".join(out)


def _why_flagged(q, state):
    if not re.search(r"\bwhy\b|flag|wrong|problem|issue", q, re.I):
        return None
    flagged = [l for l in _lines(state) if l["verdict"] != "VERIFIED"]
    if not _lines(state):
        return "**Nothing has been checked yet.** Run a bill through the Bill tab first."
    if not flagged:
        return ("**Nothing on this bill was flagged against the published prices.** Every "
                "line matched what the hospital publishes.")
    out = [f"**{len(flagged)} line(s) were flagged.** Each one, and why:", ""]
    for l in sorted(flagged, key=lambda x: -(x.get("charged") or 0)):
        out.append(f"- **{l.get('code') or '—'}** · {_m(l.get('charged'))} — "
                   f"{VERDICT_MEANING.get(l['verdict'], l['verdict'])}")
    return "\n".join(out)


def _duplicates(q, state):
    if not re.search(r"duplicat|twice|two times|repeat|same code", q, re.I):
        return None
    dups = [l for l in _lines(state) if l["verdict"] == "DUPLICATE"]
    if not _lines(state):
        return "**Nothing has been checked yet.** Run a bill through the Bill tab first."
    if not dups:
        return ("**No duplicate codes were found on this bill.** The check looks for the "
                "same billing code appearing more than once on the same statement.")
    out = ["**Codes appearing more than once:**", ""]
    for l in dups:
        out.append(f"- **{l.get('code')}** · {_m(l.get('charged'))} · "
                   f"{l.get('description', '')[:40]}")
    out += ["", VERDICT_MEANING["DUPLICATE"]]
    return "\n".join(out)


def _totals(q, state):
    if not re.search(r"total|how much|owe|unexplained|difference|gap", q, re.I):
        return None
    p = state.get("priced")
    if not p:
        return ("**No priced bill yet.** Pick your hospital on the Bill tab and check a "
                "bill, and the three figures appear.")
    return "\n".join([
        f"**You were billed {_m(p['billed_total'])}.**", "",
        f"- The hospital publishes {_m(p['posted_total'])} for the lines it prices.",
        f"- The difference being asked about is {_m(p['questionable_amount'])}.", "",
        "That difference is **a gap to ask about — not money you are owed, and not a "
        "refund estimate.** It is what the published prices do not account for. Whether "
        "any of it comes back depends on the hospital's answer.",
    ])


def _rights(q, state):
    if not re.search(r"right|law|entitle|estimate|charity|assistance|surprise|insur", q, re.I):
        return None
    found = state.get("rights") or []
    if not found:
        return ("**No rights were checked, or none applied.** They depend on your "
                "situation — open *Four questions* on the Bill tab. Anything left as "
                "*Not sure* is skipped, which is not the same as having no protection.")
    out = [f"**{len(found)} thing(s) the law may already give you:**", ""]
    for f in found:
        out += [f"**{f['title']}**", f["means"], f"*What to do:* {f['todo']}",
                f"*Source: {f['source']}*", ""]
    return "\n".join(out)


def _records(q, state):
    if not re.search(r"record|history|happen|receive|did i|my paperwork", q, re.I):
        return None
    checked = state.get("crosschecked") or []
    if not checked:
        return "**No bill has been checked against your records yet.**"
    unsupported = [c for c in checked if c["verdict"] in ("NO_RECORD", "DATE_NO_MATCH")]
    out = [f"**{len(unsupported)} of {len(checked)} line(s) have nothing in your vault "
           f"behind them.**", ""]
    for c in unsupported:
        out.append(f"- {_m(c.get('charged'))} — {c['ask']}")
    out += ["", "Your vault holds what you have uploaded, which is rarely everything. A "
            "line with no matching record is **a question to ask, not proof that the "
            "service never happened.**"]
    return "\n".join(out)


def _fraud(q, state):
    if not re.search(r"fraud|illegal|crime|sue|lawyer|report them|scam", q, re.I):
        return None
    return ("**Nothing here is evidence of fraud, and this tool will not say that it is.**\n\n"
            "A charge above a published price is usually a billing or coding error, a "
            "chargemaster that has not been updated, or a price that is simply high and "
            "legal. Hospital pricing being confusing is not the same as anybody breaking "
            "the law.\n\nWhat these findings are good for is a specific, sourced set of "
            "questions. Start with the billing office in writing. If that goes nowhere, "
            "your state department of insurance or a patient advocate is the next step — "
            "not a lawyer, and not an accusation.")


def _next_steps(q, state):
    if not re.search(r"next|what do i do|what should i|how do i start|who do i", q, re.I):
        return None
    out = ["**What to do, in order:**", "",
           "1. **Ask for the itemised statement** if you only have a summary. You cannot "
           "check what you cannot see.",
           "2. **Send the letter** from the bottom of the Bill tab. It names each line and "
           "what you are asking about, and asks them to pause collection while they answer.",
           "3. **Ask in writing and keep the reply.** A phone call leaves no record.",
           "4. **Ask about financial assistance** before agreeing to any payment plan — "
           "signing one can end your eligibility."]
    if (state.get("rights") or []):
        out += ["", "You also have the specific entitlements listed above. Those are "
                "usually worth more than the price differences."]
    return "\n".join(out)


ANSWERERS = (_fraud, _about_a_code, _duplicates, _totals, _rights, _records,
             _next_steps, _why_flagged)

CAN_ANSWER = [
    "why a line was flagged, and what the verdict means",
    "any code on the bill — what was billed and what the hospital publishes",
    "whether anything was billed twice",
    "the totals, and what “unexplained” actually means",
    "what the law may already give you",
    "whether your own records support a line",
    "what to do next, and who to contact",
]


def answer(question, state):
    """Answer a question from the findings. Returns markdown.

    `state` carries whatever the Bill tab produced: priced, rights, face, crosschecked.
    """
    q = (question or "").strip()
    if not q:
        return None
    for fn in ANSWERERS:
        out = fn(q, state)
        if out:
            return out
    return ("**I only answer from what the checks actually found, so I would rather say I "
            "do not understand that than guess.**\n\nI can tell you about:\n\n"
            + "\n".join(f"- {c}" for c in CAN_ANSWER))
