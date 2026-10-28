#!/usr/bin/env python3
"""The stylesheet's promises, and the one piece of text-handling the screens share."""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import ui     # noqa: E402


def test_a_model_answer_cannot_put_markup_on_the_page():
    out = ui.safe('Take it with food <img src=x onerror="alert(1)"> & water')
    assert "<img" not in out and "&lt;img" in out and "&amp;" in out


def test_the_bold_the_fixed_answers_use_survives():
    """The emergency answer bolds "call 911". Escaping it would print the tags."""
    assert ui.safe("<b>call 911</b>") == "<b>call 911</b>"


def test_nothing_to_escape_is_an_empty_string():
    assert ui.safe(None) == ""


def test_one_typeface_reaches_streamlit_own_elements():
    """Streamlit set Source Sans on captions, cards and headings through generated class
    names, so the page used two typefaces. The rule that fixes it must leave the icon font
    and the letter's fixed-width text alone, or the arrows and the letter break."""
    rule = re.search(r"\.stApp :is\([^)]*\)([^{]*)\{\s*font-family:var\(--sans\)", ui.CSS)
    assert rule, "the one-typeface rule is gone"
    assert 'stIconMaterial' in rule.group(1)
    # The wrapper alone is not enough: Streamlit puts the fixed-width font on a div
    # inside it, and the first version of this rule reached that div and set the letter
    # in proportional type, so its columns of figures stopped lining up.
    assert ':not([data-testid="stText"] *)' in rule.group(1)


def test_download_buttons_look_like_the_other_buttons():
    """The calendar file was the one square, flat-blue button in the app."""
    assert ":is(.stButton,.stDownloadButton)>button[kind=\"primary\"]" in ui.CSS


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
