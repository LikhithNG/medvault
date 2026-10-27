#!/usr/bin/env python3
"""The mark, and the stylesheet that carries it.

These are not aesthetic tests — nobody can assert that a shield looks right. They cover the
three ways this particular drawing can break silently:

  * geometry drifting outside its box, which clips the icon rather than erroring,
  * a '#' reaching a CSS data URI unescaped, which truncates the rest of the rule,
  * two copies of the mark on one page sharing a mask id, where the second one wins and
    the first renders as a solid square.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import logo   # noqa: E402
import ui     # noqa: E402


def test_shield_stays_inside_its_own_box():
    # Arrange / Act
    points = logo.shield_points()

    # Assert — anything outside 0..48 is drawn outside the icon and silently clipped
    assert points, "the shield sampled to nothing"
    assert all(0 <= x <= logo.BOX and 0 <= y <= logo.BOX for x, y in points)


def test_shield_is_wide_enough_to_be_a_shield():
    points = logo.shield_points()
    width = max(x for x, _ in points) - min(x for x, _ in points)
    height = max(y for _, y in points) - min(y for _, y in points)
    assert width > logo.BOX * 0.6
    assert height > width          # taller than it is wide, or it is not a shield


def test_path_string_and_sampled_points_start_at_the_same_place():
    """The SVG and the PNG icons are only the same drawing if they share this list."""
    first = logo.shield_points()[0]
    assert logo.SHIELD.startswith("M24 3.4")
    assert first == (24.0, 3.4)


def test_data_uri_escapes_the_hash_in_a_colour():
    # Arrange — a gradient mark contains #3B8CFF and #0A4E9E
    svg = logo.mark(fill="gradient")
    assert "#" in svg

    # Act
    uri = logo.data_uri(svg)

    # Assert — an unescaped '#' ends the URI and silently truncates the CSS rule
    assert "#" not in uri
    assert uri.startswith("data:image/svg+xml,")
    assert '"' not in uri


def test_two_marks_on_one_page_do_not_share_a_mask_id():
    a, b = logo.mark(uid="a"), logo.mark(uid="b")
    assert 'id="mvma"' in a and 'id="mvmb"' in b
    assert 'mask="url(#mvma)"' in a and 'mask="url(#mvmb)"' in b


def test_tile_carries_both_its_gradient_and_its_mask():
    tile = logo.tile(uid="t")
    assert 'url(#mvgt)' in tile and 'url(#mvmt)' in tile


def test_wordmark_keeps_the_name_as_real_text():
    """An outlined wordmark would not be selectable or read aloud."""
    assert ">Med<" in logo.wordmark() and ">Vault<" in logo.wordmark()


def test_stylesheet_has_no_unreplaced_placeholders():
    """CSS fails silently: a leftover __ICONS__ is just an invalid rule nobody sees."""
    assert "__" not in ui.CSS
    assert ui.CSS.count("<style>") == 1 and ui.CSS.count("</style>") == 1


def test_every_navigation_position_gets_an_icon():
    for count in (5, 2):
        for i in range(1, count + 1):
            assert f"button:nth-child({i})::before" in ui.CSS


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
