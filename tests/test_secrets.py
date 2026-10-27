#!/usr/bin/env python3
"""Every setting the app reads has to be reachable from a hosting platform's secrets.

This exists because the same defect has now happened twice.

Streamlit puts secrets in `st.secrets`, not in `os.environ`. app.py bridges the two by
copying a hand-written tuple of key names across. Anything missing from that tuple is
read as unset when deployed, and nothing says so — the app just quietly behaves as though
you never set it.

  * Itemized shipped with GEMINI_API_KEY missing from the list. The key was set on the
    server, the reader could not see it, and the interface reported no key configured.
  * MedVault shipped with TURSO_DATABASE_URL and TURSO_AUTH_TOKEN missing. A vault with a
    real database behind it went on writing to a disk that gets wiped on restart, and the
    warning that would have said so was keyed on MEDVAULT_HOSTED — which was also missing.

So this reads the source for environment lookups and fails when one is not listed.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

# Both quote styles: gemini.py and groq.py use single, the rest use double.
LOOKUP = re.compile(r"""environ(?:\.get)?[\(\[]\s*['"]([A-Z][A-Z0-9_]*)['"]""")

# Set by the operating system, never by us, and meaningless in a secrets file.
SYSTEM = {"HOME", "HOSTNAME", "PATH", "USER", "TMPDIR", "PWD", "LANG"}


def declared():
    source = (ROOT / "app.py").read_text()
    block = source[source.index("SECRET_KEYS = ("):]
    block = block[:block.index(")")]
    return set(re.findall(r'"([A-Z][A-Z0-9_]*)"', block))


def looked_up():
    found = {}
    for path in [ROOT / "app.py"] + sorted((ROOT / "medvault").glob("*.py")):
        for key in LOOKUP.findall(path.read_text()):
            found.setdefault(key, set()).add(path.name)
    return found


def test_every_setting_the_app_reads_can_come_from_secrets():
    missing = {k: sorted(v) for k, v in looked_up().items()
               if k not in declared() and k not in SYSTEM}

    assert not missing, (
        "these are read from the environment but never promoted out of st.secrets, "
        f"so they are silently ignored when deployed: {missing}")


def test_the_two_that_have_already_bitten_are_listed():
    """Named individually so the regression is unmistakable in a failure message."""
    for key in ("GEMINI_API_KEY", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN",
                "MEDVAULT_HOSTED"):
        assert key in declared(), f"{key} would be ignored on a deployment"


def test_the_list_holds_no_key_nothing_reads():
    """A name in the list that no code reads is either a typo or a leftover, and both
    look like working configuration to whoever sets it."""
    reads = set(looked_up())
    # MEDVAULT_DB is read by db.py at import time through a module-level default.
    stale = declared() - reads - {"MEDVAULT_DB"}

    assert not stale, f"listed but never read: {sorted(stale)}"


def test_system_variables_are_not_dragged_in():
    assert "HOME" not in declared()


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")


def test_the_landing_page_says_where_the_records_actually_live():
    """The one claim on the signed-out page a deployment can falsify, and the only way
    to check a deployment's storage without signing in to it."""
    sys.path.insert(0, str(ROOT / "medvault"))
    import landing

    temporary = landing.footer(durable=False)
    durable = landing.footer(durable=True)

    assert "wipes that disk" in temporary
    assert "outlives a restart" in durable
    assert temporary != durable


def test_the_footer_can_be_called_the_old_way():
    """A landing page must not be able to crash. The first version of this took the live
    site down: a new app.py called footer(durable=...) against a landing module still in
    memory from the previous deploy, which did not accept the keyword."""
    import landing

    assert landing.footer()
    assert landing.footer(durable=True) != landing.footer(durable=False)
