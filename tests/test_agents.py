#!/usr/bin/env python3
"""The agent mapping has to be true, not merely written down.

Assignment 2 named three agents and mapped them onto Madison roles. That mapping lived on
a Figma board and nowhere in the code — the word "Madison" appeared zero times in this
project while three of its agents sat in it working. agents.py is the mapping as data;
these tests are what stop it rotting into a comment that used to be right.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import agents   # noqa: E402


def test_every_agent_entry_point_actually_exists():
    """Rename dispute.letter and this fails, rather than the architecture quietly
    becoming wrong."""
    for agent in agents.AGENTS:
        fn = agents.resolve(agent)
        assert callable(fn), f"{agent['name']} -> {agent['module']}.{agent['entry']}"


def test_every_secondary_entry_point_exists_too():
    for agent in agents.AGENTS:
        module = __import__(agent["module"])
        for name in agent["also"]:
            assert callable(getattr(module, name, None)), f"{agent['module']}.{name}"


def test_the_three_agents_assignment_2_named_are_all_here():
    for name, role in (("Reader", "Intelligence"), ("Checker", "Research"),
                       ("Advocate", "Performance")):
        assert name in agents.BY_NAME
        assert agents.BY_NAME[name]["madison"] == role


def test_the_fourth_agent_is_declared_rather_than_left_off():
    """MedVault grew a records bot the original design did not plan for. Experience is
    the one Madison role of the five that design never used."""
    assert agents.BY_NAME["Companion"]["madison"] == "Experience"


def test_every_madison_role_is_used():
    """Five roles: Intelligence, Content, Research, Experience, Performance. All five are
    held by at least one agent."""
    assert set(agents.MADISON_ROLES) == {"Intelligence", "Content", "Research",
                                         "Experience", "Performance"}


def test_a_shared_role_is_shared_for_a_stated_reason():
    """This used to require every agent to hold a different role. The Liaison and the
    Advocate both carry findings to a third party, so they share Performance - and a test
    that forced a sixth, invented role would have been asserting tidiness, not truth."""
    from collections import Counter
    shared = {role for role, n in Counter(agents.MADISON_ROLES).items() if n > 1}
    assert shared <= {"Performance"}, f"unexplained shared role: {shared}"


def test_the_new_agents_are_deterministic():
    """A reminder at 2 a.m. and a note to a doctor are not places for a model."""
    assert agents.BY_NAME["Scheduler"]["generative"] is False
    assert agents.BY_NAME["Liaison"]["generative"] is False


def test_the_checker_and_the_advocate_are_not_generative():
    """The whole argument of this project is that no figure a patient acts on comes out
    of a model. If either of these is ever marked generative, that argument is gone."""
    assert agents.BY_NAME["Checker"]["generative"] is False
    assert agents.BY_NAME["Advocate"]["generative"] is False


def test_every_agent_says_what_it_does_not_do():
    """The column that stops an agent being asked to do the thing it must not."""
    for agent in agents.AGENTS:
        assert agent["does_not"], f"{agent['name']} has no DOES NOT"
        assert agent["does"] and agent["input"] and agent["output"]


def test_the_checker_never_imports_a_model_client():
    """Stronger than a promise in a docstring: read the file."""
    source = (pathlib.Path(__file__).resolve().parent.parent
              / "medvault" / "checker.py").read_text()
    for client in ("import gemini", "import groq", "from gemini", "from groq"):
        assert client not in source, f"checker.py reaches for {client}"


def test_the_advocate_never_imports_a_model_client():
    source = (pathlib.Path(__file__).resolve().parent.parent
              / "medvault" / "dispute.py").read_text()
    for client in ("import gemini", "import groq", "from gemini", "from groq"):
        assert client not in source, f"dispute.py reaches for {client}"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
