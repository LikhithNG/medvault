#!/usr/bin/env python3
"""What federal law may already entitle the patient to, before any price is compared.

The idea is borrowed from DAVANO Innovation Lab's `itemize`, whose README puts it better
than I would: a patient's rights are usually worth more than any coding error. A rate
difference of a few hundred dollars is real; being owed a written estimate, or qualifying
for a charity-care policy that caps the whole bill, is a different order of magnitude - and
none of it needs a price file to work out. It needs three or four questions.

Two disciplines are carried over with it, and they matter more than the rules themselves:

1. **An unanswered question is "not determined", never "no right."** A tool that fills the
   gaps with plausible negatives will eventually tell somebody they have no protection that
   they in fact have. Every rule here returns nothing when it does not know.

2. **Every finding names the rule it comes from**, so the reader can check it rather than
   take this file's word for it.

This is information, not legal advice. Each finding is phrased as something to ask about.
"""

# 45 CFR 149.620: a self-pay patient billed this much above their Good Faith Estimate can
# use the federal patient-provider dispute resolution process.
GFE_DISPUTE_THRESHOLD = 400.0

UNKNOWN = "unknown"


def context(coverage=UNKNOWN, emergency=None, in_network_facility=None,
            nonprofit_hospital=None, gfe_amount=None):
    """What the patient has told us about their situation. Unanswered stays None."""
    return {"coverage": coverage, "emergency": emergency,
            "in_network_facility": in_network_facility,
            "nonprofit_hospital": nonprofit_hospital, "gfe_amount": gfe_amount}


def _finding(rule, severity, title, means, todo, source):
    return {"rule": rule, "severity": severity, "title": title,
            "means": means, "todo": todo, "source": source}


def good_faith_estimate(total, ctx):
    """A self-pay patient is owed a written estimate before scheduled care."""
    if ctx.get("coverage") != "self_pay":
        return []

    gfe = ctx.get("gfe_amount")
    if gfe is None:
        return [_finding(
            "gfe_missing", "high",
            "You were entitled to a written estimate before this care",
            "Providers must give uninsured and self-pay patients a Good Faith Estimate of "
            "expected charges in advance of scheduled care. If you never received one, "
            f"that is itself worth raising — this bill is {_money(total)}.",
            "Ask the billing office, in writing, for the Good Faith Estimate you were "
            "issued. If none exists, say so in the same letter.",
            "No Surprises Act · 45 CFR 149.610")]

    over = round(total - gfe, 2)
    if over >= GFE_DISPUTE_THRESHOLD:
        return [_finding(
            "gfe_exceeded", "high",
            f"This bill is {_money(over)} above your estimate",
            f"You were estimated {_money(gfe)} and billed {_money(total)}. A self-pay "
            f"patient billed {_money(GFE_DISPUTE_THRESHOLD)} or more above their Good "
            "Faith Estimate can use the federal patient-provider dispute resolution "
            "process rather than negotiating alone.",
            "Start dispute resolution within 120 days of the bill. Keep the estimate and "
            "the bill together — you will be asked for both.",
            "No Surprises Act · 45 CFR 149.620")]

    if over > 0:
        return [_finding(
            "gfe_over_small", "info",
            f"This bill is {_money(over)} above your estimate",
            f"Above the estimate, but under the {_money(GFE_DISPUTE_THRESHOLD)} threshold "
            "that opens federal dispute resolution. Still worth asking about.",
            "Ask the billing office to explain the difference in writing.",
            "No Surprises Act · 45 CFR 149.620")]
    return []


def charity_care(total, ctx):
    """A non-profit hospital must have a financial assistance policy, and must cap what it
    charges people who qualify."""
    if ctx.get("nonprofit_hospital") is not True:
        return []
    return [_finding(
        "charity_care", "high",
        "This hospital must have a financial assistance policy",
        "Non-profit hospitals are required to maintain a written financial assistance "
        "policy, to publicise it, and to charge people who qualify no more than the "
        "amounts generally billed to insured patients. Eligibility is often far above the "
        "poverty line, and hospitals are not required to tell you that you qualify.",
        "Ask for the hospital's Financial Assistance Policy and its application form by "
        "name. Ask what income level qualifies before you agree to any payment plan.",
        "Internal Revenue Code 501(r)(4)–(5)")]


def surprise_billing(total, ctx):
    """Balance billing is prohibited outright in two situations."""
    out = []
    if ctx.get("emergency") is True:
        out.append(_finding(
            "nsa_emergency", "high",
            "Emergency care is protected from balance billing",
            "For emergency services you generally cannot be billed more than your "
            "in-network cost sharing, even if the hospital or the treating clinician was "
            "out of network. Anything above that may be prohibited rather than negotiable.",
            "Ask the billing office to confirm, in writing, that this bill is limited to "
            "in-network cost sharing under the No Surprises Act.",
            "No Surprises Act · 45 CFR 149.110"))

    if ctx.get("in_network_facility") is True and ctx.get("coverage") == "insured":
        out.append(_finding(
            "nsa_in_network_facility", "high",
            "An out-of-network clinician at an in-network hospital is protected too",
            "If the facility was in network, a clinician who was not — an anaesthetist, a "
            "radiologist, an assistant surgeon — generally cannot balance-bill you beyond "
            "your in-network cost sharing.",
            "Ask which clinicians on this bill were out of network, and on what basis each "
            "one is billing you above in-network cost sharing.",
            "No Surprises Act · 45 CFR 149.120"))
    return out


def ambulance_gap(lines, ctx):
    """Ground ambulance is a deliberate federal carve-out, and saying so is the useful part."""
    hit = [l for l in lines if _mentions(l, ("ambulance", "a0425", "a0427", "a0429",
                                             "ground transport"))]
    if not hit:
        return []
    return [_finding(
        "ambulance_carveout", "info",
        "Ground ambulance is not covered by the federal protection",
        "The No Surprises Act deliberately left ground ambulance out. Roughly 22 states "
        "fill that gap with their own law and the rest do not. Which applies to you "
        "depends on your state and on whether your plan is state-regulated — this tool "
        "does not know either, and is not going to guess.",
        "Ask your state department of insurance whether your state limits ground-ambulance "
        "balance billing, and whether your plan is self-funded, which usually puts it out "
        "of state reach.",
        "No Surprises Act · ground ambulance excluded from 45 CFR 149.110")]


def evaluate(lines, total, ctx):
    """Every rule, against one bill. Returns findings, highest severity first."""
    found = []
    found += good_faith_estimate(total, ctx)
    found += charity_care(total, ctx)
    found += surprise_billing(total, ctx)
    found += ambulance_gap(lines, ctx)

    rank = {"high": 0, "info": 1}
    found.sort(key=lambda f: rank.get(f["severity"], 9))
    return found


def unanswered(ctx):
    """Which questions are still open. Shown to the reader, because an unanswered question
    is the difference between "no protection" and "we did not ask"."""
    labels = {"coverage": "whether you are insured or self-pay",
              "emergency": "whether this was emergency care",
              "nonprofit_hospital": "whether the hospital is non-profit",
              "in_network_facility": "whether the facility was in network"}
    out = []
    for key, label in labels.items():
        v = ctx.get(key)
        if v is None or v == UNKNOWN:
            out.append(label)
    return out


def _money(v):
    return f"${v:,.2f}"


def _mentions(line, needles):
    text = " ".join(str(line.get(k) or "") for k in ("description", "desc", "code")).lower()
    return any(n in text for n in needles)
