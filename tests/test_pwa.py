#!/usr/bin/env python3
"""The head tags that make this installable, and the document they have to land in.

The bug: window.parent was far enough locally and not far enough deployed. On Streamlit
Community Cloud the app runs inside an iframe on a wrapper page, so window.parent reached
only the app's document — and a browser installs from the TOP document, which still
carried Streamlit's manifest, Streamlit's icon and a white theme colour. Every tag was
present, in a document nobody installs from. Found by inspecting the deployment: the
inner frame had theme-color #0F6FDE and the outer had #FFFFFF.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import pwa   # noqa: E402

JS = pwa._js()


def test_it_writes_into_the_top_document_not_only_the_parent():
    assert "window.top" in JS
    assert "docs.push" in JS, "the top document is never added to the list"


def test_it_survives_a_top_document_it_cannot_reach():
    """A cross-origin top must leave the app document correct rather than throw."""
    assert "catch" in JS and "try" in JS


def test_urls_are_made_absolute_against_the_app_not_the_wrapper():
    """app/static/manifest.json relative to the wrapper is a path the wrapper answers
    with HTML; relative to the app it is the file."""
    assert "new URL(" in JS and "base" in JS
    assert "APP.location.href" in JS


def test_every_tag_that_carries_a_url_is_resolved():
    carriers = [attrs for tag, attrs in pwa.HEAD if "href" in attrs]
    assert carriers, "no href tags at all"
    for attrs in carriers:
        assert attrs["href"].startswith("app/static/"), attrs


def test_the_manifest_and_the_apple_icon_are_both_declared():
    rels = {attrs.get("rel") for tag, attrs in pwa.HEAD if tag == "link"}
    assert {"manifest", "apple-touch-icon"} <= rels


def test_the_theme_colour_is_medvault_blue():
    theme = next(a["content"] for t, a in pwa.HEAD
                 if t == "meta" and a.get("name") == "theme-color")
    assert theme == "#0F6FDE"


def test_each_tag_replaces_rather_than_appends():
    """Streamlit writes its own viewport and theme-color. A second one further down the
    head does not win."""
    assert "old.remove()" in JS


def test_the_static_files_the_tags_point_at_exist():
    static = pathlib.Path(__file__).resolve().parent.parent / "static"
    for tag, attrs in pwa.HEAD:
        href = attrs.get("href")
        if href:
            name = href.split("/")[-1]
            assert (static / name).exists(), f"{name} is referenced and not shipped"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
