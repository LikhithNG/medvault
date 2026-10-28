#!/usr/bin/env python3
"""Where the code lives, and the two traps that came with moving it there.

app.py grew to 1,700 lines with every screen in it. The screens now live in
medvault/screen_*.py and app.py is the shell. Moving them exposed two traps of
Streamlit's module model: an imported module is not re-run on each click, so a
connection held at module level outlives the vault it was opened on; and a cached call
with a spinner leaves an invisible placeholder on the page, which shifted every element
after it, so a screen drew a different element tree on the next run than on this one,
and signing out stopped working under test.
"""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "app.py", *sorted((ROOT / "medvault").glob("*.py"))]
CEILING = 800


def test_no_source_file_outgrows_the_ceiling():
    long = {p.name: n for p in SOURCES if (n := len(p.read_text().splitlines())) > CEILING}
    assert not long, f"over {CEILING} lines - split by screen or by job: {long}"


def test_app_py_stays_the_shell():
    """It loads credentials, draws the stylesheet and puts screens behind tabs. A screen
    defined here would be back to one file holding everything."""
    tree = ast.parse((ROOT / "app.py").read_text())
    defined = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert defined == ["_load_credentials"], f"app.py defines {defined}"


def test_no_screen_holds_a_connection_at_import():
    """A module-level `con` in an imported module is opened once per process and kept,
    including across a test swapping in a throwaway vault. Screens ask session.vault()."""
    for path in sorted((ROOT / "medvault").glob("*.py")):
        tree = ast.parse(path.read_text())
        held = [t.id for n in tree.body if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name) and t.id == "con"]
        assert not held, f"{path.name} holds a connection at module level"


def test_the_connection_lookup_draws_nothing_on_the_page():
    source = (ROOT / "medvault" / "session.py").read_text()
    assert "@st.cache_resource(show_spinner=False)\ndef vault():" in source


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
