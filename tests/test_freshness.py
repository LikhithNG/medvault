#!/usr/bin/env python3
"""A deploy takes effect without a reboot.

The hosted app picks up each push in place, and Streamlit keeps the modules app.py
imported - so the newest app.py ran against modules from pushes ago. It took the live
site down twice: landing.footer() had lost an argument, then counts_by_kind() had gained
one. These run freshness.ensure() against a scratch folder of modules, never the real
one, and check it drops exactly what it should.
"""
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))

import freshness  # noqa: E402


def _folder():
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "fr_alpha.py").write_text("VERSION = 1\n")
    (tmp / "fr_beta.py").write_text("import fr_alpha\n")
    sys.path.insert(0, str(tmp))
    return tmp


def _cleanup(tmp):
    sys.path.remove(str(tmp))
    for name in ("fr_alpha", "fr_beta"):
        sys.modules.pop(name, None)


def test_modules_loaded_before_it_ever_ran_are_dropped():
    """The live case: an older app.py imported everything and never called this."""
    tmp = _folder()
    try:
        import fr_beta  # noqa: F401
        assert set(freshness.ensure(tmp)) == {"fr_alpha", "fr_beta"}
        assert "fr_alpha" not in sys.modules
    finally:
        _cleanup(tmp)


def test_nothing_is_dropped_while_the_code_is_unchanged():
    tmp = _folder()
    try:
        freshness.ensure(tmp)
        import fr_beta  # noqa: F401
        assert freshness.ensure(tmp) == []
        assert "fr_beta" in sys.modules
    finally:
        _cleanup(tmp)


def test_a_changed_file_drops_every_module_in_the_folder():
    """All of them, not only the one that changed: fr_beta holds a reference to the old
    fr_alpha, and keeping it would be the same mismatch one layer down."""
    tmp = _folder()
    try:
        freshness.ensure(tmp)
        import fr_alpha
        import fr_beta  # noqa: F401
        time.sleep(0.01)
        (tmp / "fr_alpha.py").write_text("VERSION = 2\n")
        assert set(freshness.ensure(tmp)) == {"fr_alpha", "fr_beta"}
        import fr_alpha as reloaded
        assert reloaded.VERSION == 2 and fr_alpha.VERSION == 1
    finally:
        _cleanup(tmp)


def test_modules_from_anywhere_else_are_left_alone():
    tmp = _folder()
    try:
        import json
        freshness.ensure(tmp)
        assert sys.modules["json"] is json
    finally:
        _cleanup(tmp)


def test_the_app_checks_before_it_imports_any_medvault_module():
    """Checking after the imports would compare against modules that are already stale."""
    source = (pathlib.Path(__file__).resolve().parent.parent / "app.py").read_text()
    check = source.index("freshness.ensure(")
    first_import = source.index("\nimport accounts")
    assert check < first_import
    assert "st.cache_resource.clear()" in source[check:first_import]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
