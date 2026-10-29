#!/usr/bin/env python3
"""What the AI services that read for MedVault may do with what they are sent.

The README said an uploaded document "is not retained there". On the tier this demo runs
on, that was not true. Google's terms for the unpaid Gemini API say that what is sent is
used to improve Google's products, that human reviewers may read it, and, in so many words,
that nothing sensitive, confidential or personal should be sent. Groq, which reads a bill's
text layer first, does not keep requests by default, but may log them for up to 30 days to
investigate abuse unless Zero Data Retention is switched on in its console.

Checked against both providers' published terms on 29 October 2026 (the links below). The
paid Gemini tier, which needs a Cloud project with billing switched on, does not use what is
sent to improve Google's products; it still logs it for a limited time to detect abuse.

Every screen that sends paperwork out says so before it does, in the words below. They are
in one place so that no screen can say one thing while the next says another.
"""

GEMINI_TERMS = "https://ai.google.dev/gemini-api/terms"
GROQ_TERMS = "https://console.groq.com/docs/your-data"

# The line that has to be read. tests/test_disclosure.py looks for it on every screen that
# sends something out, and on none of the others.
SAMPLES_ONLY = "This is a demo: use sample paperwork, not your real records."

# The reason behind it, one tap away.
WHY = (f"The AI reader is Google Gemini on its free tier. Under <a href='{GEMINI_TERMS}' "
       "target='_blank' rel='noopener'>Google's terms for that tier</a>, what is sent may "
       "be used to improve Google's products, and reviewers at Google may read it. A bill "
       f"with a text layer goes to Groq first, which <a href='{GROQ_TERMS}' target='_blank' "
       "rel='noopener'>does not keep it by default</a>. A real version of MedVault would "
       "need Gemini's paid tier, where Google does not use what is sent to improve its "
       "products.")


def notice(sent):
    """The (visible line, reason) a screen shows before `sent` goes to an AI reader."""
    return f"<b>{SAMPLES_ONLY}</b> {sent}", WHY
