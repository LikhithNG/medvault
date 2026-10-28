#!/usr/bin/env python3
"""The agents' marks and motion.

The test that matters is the first one. Moving things trigger nausea and migraine for
people with vestibular disorders, and a medical records app is exactly where those people
are - so every animation must sit inside the switch that turns it off, and this reads both
stylesheets to make sure nothing escaped.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import agents     # noqa: E402
import agentsui   # noqa: E402
import ui         # noqa: E402

GATE = "@media (prefers-reduced-motion: no-preference)"


def _outside_the_gate(css):
    """The stylesheet with every reduced-motion block cut out, brace-matched."""
    out, i = [], 0
    while True:
        start = css.find(GATE, i)
        if start < 0:
            out.append(css[i:])
            return "".join(out)
        out.append(css[i:start])
        depth, j = 0, css.index("{", start)
        while True:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1


def test_no_animation_escapes_the_reduced_motion_switch():
    for name, css in (("agentsui.CSS", agentsui.CSS), ("ui.CSS", ui.CSS)):
        rest = _outside_the_gate(css)
        assert not re.search(r"\banimation\s*:", rest), f"{name} animates outside the gate"
        assert "@keyframes" not in rest, f"{name} defines keyframes outside the gate"


def test_the_gate_actually_holds_the_animations():
    """A test that cut everything out would pass trivially."""
    assert GATE in agentsui.CSS
    assert agentsui.CSS.count("@keyframes") >= 8


def test_no_animation_runs_forever_that_does_not_need_to():
    """The next-dose glow draws attention three times and stops. An alarm that never stops
    pulsing teaches people to ignore it."""
    assert re.search(r"\.ag-next\{animation:ag-glow [^;}]* 3\}", agentsui.CSS)


def test_every_agent_has_a_mark_and_a_sentence():
    names = set(agents.BY_NAME)
    assert set(agentsui.GLYPH) == names
    assert set(agentsui.SHORT) == names


def test_every_mark_has_a_moving_part():
    """The motion is the job. A mark with nothing classed to move would sit still."""
    movers = ("ag-scan", "ag-tick", "ag-lift", "ag-dot", "ag-hand", "ag-pulse")
    for name, glyph in agentsui.GLYPH.items():
        assert any(m in glyph for m in movers), f"{name} has nothing that moves"


def test_a_badge_says_whether_a_model_was_involved():
    for name, agent in agents.BY_NAME.items():
        html = agentsui.badge(name)
        assert agent["madison"] in html
        assert ("model" in html.split('"')[1]) == agent["generative"], name


def test_the_working_card_is_announced_to_screen_readers():
    html = agentsui.working("Reader", "Reading your document", "Looking at the page")
    assert 'role="status"' in html and 'aria-live="polite"' in html


def test_the_marks_are_hidden_from_screen_readers():
    """The agent's name is already text beside the mark; reading out an SVG is noise."""
    assert 'aria-hidden="true"' in agentsui._glyph("Checker")


def test_the_roster_lists_all_six_once_each():
    html = agentsui.roster()
    for name in agents.BY_NAME:
        assert html.count(f'<div class="ag-n">{name}</div>') == 1, name


def test_a_stagger_never_makes_somebody_wait():
    """A long list must not take seconds to finish arriving."""
    assert agentsui.arrive(50) == ' style="--i:8"'


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
