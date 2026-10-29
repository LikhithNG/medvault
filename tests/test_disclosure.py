#!/usr/bin/env python3
"""What the app tells people about where their paperwork goes, held to the providers' terms.

The README said an uploaded document "is not retained there". On the tier this demo runs
on, it was not true: Google's terms for the unpaid Gemini API say what is sent may be used
to improve Google's products and read by human reviewers, and ask in so many words that
nothing sensitive, confidential or personal is sent. A health app was asking for exactly
that, and saying the opposite. These keep the claim true, and keep it on screen at every
point where something is about to leave.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
sys.path.insert(0, str(ROOT / "tests"))

import providers                                   # noqa: E402
from test_bill_screen import _app, offline_vault  # noqa: E402
from test_quota import READY, _env, _no_network   # noqa: E402

README = (ROOT / "README.md").read_text()


def test_no_document_in_the_repository_says_a_page_is_not_kept():
    """The README was fixed and CAVEATS.md still said it - so every document is read."""
    for doc in ROOT.glob("*.md"):
        assert "not retained" not in doc.read_text(), doc.name


def test_the_readme_says_what_the_free_tier_allows_and_links_the_terms():
    section = README[README.index("## Where your data lives"):]
    section = section[:section.index("\n## ", 4)]
    assert "free tier" in section and "reviewers" in section
    assert providers.GEMINI_TERMS in section and providers.GROQ_TERMS in section


def test_the_readme_says_where_a_hosted_vault_actually_lives():
    section = README[README.index("## Where your data lives"):]
    assert "Turso" in section[:section.index("\n## ", 4)]


def test_the_reason_names_both_providers_and_links_their_terms():
    for needed in ("Google Gemini", "free tier", "reviewers", "Groq",
                   providers.GEMINI_TERMS, providers.GROQ_TERMS):
        assert needed in providers.WHY, needed


def test_the_landing_page_says_where_an_ai_read_goes():
    import landing
    foot = landing.footer()
    assert "free tier" in foot and "sample" in foot
    assert "Groq" in foot, "a bill with a text layer goes to Groq first"


def test_the_sign_in_panel_says_it_is_a_demo_before_an_account_is_made():
    from streamlit.testing.v1 import AppTest
    with offline_vault():
        import streamlit as st
        st.cache_resource.clear()
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        assert not at.exception, [e.value for e in at.exception]
        assert any(providers.SAMPLES_ONLY in m.value for m in at.markdown)


def _tab(at, name):
    labels = [t.label for t in at.tabs]
    return at.tabs[labels.index(name)]


def test_every_screen_that_sends_something_out_says_so_before_it_does():
    """Add, Bill (a photo or PDF) and Ask send paperwork to a model. Each says so first."""
    with offline_vault() as (_, alice, _), _env(**READY), _no_network():
        at = _app(alice)
        assert not at.exception, [e.value for e in at.exception]
        for name in ("Add", "Bill", "Ask"):
            shown = " ".join(m.value for m in _tab(at, name).markdown)
            assert providers.SAMPLES_ONLY in shown, f"the {name} screen does not say it"
        # and not on the screens that send nothing
        for name in ("Card", "Records", "Medicines"):
            shown = " ".join(m.value for m in _tab(at, name).markdown)
            assert providers.SAMPLES_ONLY not in shown, f"the {name} screen says it"


def test_the_bill_screen_no_longer_says_the_bill_is_not_stored():
    """MedVault does not keep it. Whether the reader's provider does is its terms' call."""
    source = (ROOT / "medvault" / "screen_bill.py").read_text()
    assert "The bill is not stored." not in source


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
