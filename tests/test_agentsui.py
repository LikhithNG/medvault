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


def _gated_rules(css):
    """(selector, body) for every plain rule inside the motion gate, keyframes left out."""
    inside = css[css.index(GATE):]
    inside = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", inside)
    inside = inside[inside.index("{") + 1:]
    inside = re.sub(r"/\*.*?\*/", "", inside, flags=re.S)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", inside)]


# The only elements that exist while, and only while, an agent is busy - plus the
# landing-page card a visitor is hovering, which is asking to be shown.
WORKING = (".ag-on", ":hover", ".ag-bar", ".ag-link.go")


def _names(selector, wanted):
    """Whether a selector uses one of these, as a whole name. ".ag-on" is a prefix of
    ".ag-once", and the first version of this check could not tell them apart - so a
    badge set to loop forever passed it."""
    return any(re.search(re.escape(w) + r"(?![\w-])", selector) for w in wanted)


def test_a_mark_only_loops_while_its_agent_is_working():
    """The first version looped every mark forever, so a results screen said "still
    working" about agents that had finished. Anything that repeats without end must be
    scoped to a working state."""
    looping = [sel for sel, body in _gated_rules(agentsui.CSS) if "infinite" in body]
    assert looping, "nothing loops at all - the working state has lost its motion"
    for sel in looping:
        for part in sel.split(","):
            assert _names(part, WORKING), f"{part.strip()} loops while idle"


def test_a_mark_at_rest_does_not_move():
    """Every rule that animates a moving part names a state: working, or just finished."""
    for sel, body in _gated_rules(agentsui.CSS):
        if not re.search(r"\banimation\s*:", body) or ".ag-m" not in sel:
            continue
        for part in sel.split(","):
            assert _names(part, (".ag-on", ".ag-once", ":hover")), part


def test_a_badge_plays_once_rather_than_forever():
    assert "ag-once" in agentsui.badge("Scheduler")
    assert "ag-on" not in agentsui.badge("Scheduler").replace("ag-once", "")


def test_the_working_card_is_the_working_state():
    assert "ag-on" in agentsui.working("Companion", "Reading your records")


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
    assert agentsui.arrive(50) == "ag-i8"
    assert ".ag-i8{--i:8}" in agentsui.CSS and ".ag-i9{" not in agentsui.CSS


def test_nothing_relies_on_an_inline_custom_property():
    """Streamlit's markdown renderer drops custom properties from inline styles, silently.
    The stagger was written as style="--i:3" and staggered nothing for a whole release
    while the markup looked right. Read every source file that writes markup."""
    root = pathlib.Path(__file__).resolve().parent.parent
    for path in [root / "app.py", *sorted((root / "medvault").glob("*.py"))]:
        source = path.read_text()
        hits = re.findall(r"""style=[\"']\s*--[\w-]+\s*:""", source)
        assert not hits, f"{path.name} sets a custom property inline: {hits}"
    assert "style=" not in agentsui.relay(
        agentsui.finale([agentsui.step("Checker", "done")], {"Checker"}))


# ---- the relay -------------------------------------------------------------------

BILL = ("Reader", "Checker", "Advocate")


def _states(html):
    return re.findall(r'class="ag-step (\w+)', html)


def test_advancing_the_relay_leaves_the_old_one_alone():
    before = [agentsui.step(n) for n in BILL]
    after = agentsui.advance(before, "Checker", "work")
    assert [s["state"] for s in before] == ["wait", "wait", "wait"]
    assert [s["state"] for s in after] == ["wait", "work", "wait"]


def test_only_the_agent_that_just_moved_replays_its_finish():
    """Streamlit redraws the whole relay on each update. Without this the Reader's tick
    would pop again every time the Checker or the Advocate moved."""
    steps = [agentsui.step(n) for n in BILL]
    steps = agentsui.advance(steps, "Reader", "done", "Read in 3.1 s")
    assert 'class="ag-step done ag-once ag-t0"' in agentsui.relay(steps)
    steps = agentsui.advance(steps, "Checker", "work")
    html = agentsui.relay(steps)
    assert 'class="ag-step done"' in html and "done ag-once" not in html
    assert 'class="ag-step work ag-on"' in html


def test_the_final_frame_replays_fast_agents_in_the_order_they_worked():
    steps = [agentsui.step("Reader", "skip", "You pasted it"),
             agentsui.step("Checker", "done", "2 flagged · 3 ms"),
             agentsui.step("Advocate", "done", "Wrote it in 1 ms")]
    html = agentsui.relay(agentsui.finale(steps, {"Checker", "Advocate"}))
    turns = re.findall(r'class="ag-step done ag-once ag-t(\d)"', html)
    assert turns == ["0", "1"]
    assert ".ag-t1{--ag-at:0.55s}" in agentsui.CSS
    assert "skip ag-once" not in html


def test_an_agent_seen_finishing_is_not_made_to_do_it_twice():
    steps = [agentsui.step("Reader", "done", "Read in 4.2 s"),
             agentsui.step("Checker", "done", "Priced in 2 ms")]
    html = agentsui.relay(agentsui.finale(steps, {"Checker"}))
    assert _states(html) == ["done", "done"]
    assert html.count("ag-once") == 1


def test_the_relay_says_it_is_busy_only_while_someone_works():
    idle = agentsui.relay([agentsui.step(n) for n in BILL])
    busy = agentsui.relay(agentsui.advance([agentsui.step(n) for n in BILL], "Reader", "work"))
    assert "ag-relay busy" in busy and "ag-bar" in busy
    assert "busy" not in idle and "ag-bar" not in idle


def test_a_finished_step_carries_its_tick_even_with_motion_off():
    """With reduced motion nothing pops, so the tick has to be in the markup, not drawn by
    an animation."""
    steps = agentsui.advance([agentsui.step(n) for n in BILL], "Reader", "done")
    assert agentsui.relay(steps).count('class="ag-ok"') == 1


def test_relay_text_is_escaped():
    """Part of the sentence under the relay can come off a bill a model read."""
    html = agentsui.relay([agentsui.step("Reader", "done", "<b>x</b>")], "<script>1</script>")
    assert "<script>" not in html and "<b>x</b>" not in html


def test_a_relay_refuses_states_and_agents_it_does_not_know():
    for bad in (lambda: agentsui.step("Reader", "thinking"),
                lambda: agentsui.advance([agentsui.step("Reader")], "Scheduler", "work")):
        try:
            bad()
        except (ValueError, KeyError):
            continue
        raise AssertionError("accepted something it should not have")


def test_durations_read_at_a_glance():
    assert agentsui.took(0.0004) == "<1 ms"
    assert agentsui.took(0.0123) == "12 ms"
    assert agentsui.took(3.14159) == "3.1 s"


def test_a_heading_puts_the_agent_beside_the_section():
    html = agentsui.heading("<div class='sect'>Today</div>", "Scheduler", "day starts 08:00")
    assert html.startswith('<div class="ag-head">') and "day starts 08:00" in html


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
