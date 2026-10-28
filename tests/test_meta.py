#!/usr/bin/env python3
"""The tests have to run the way the README says they run.

Every file here can be run directly - `python3 tests/test_x.py` - through a small runner
at the bottom. Three times now a test was appended to a file AFTER that runner, so pytest
ran it and the direct command silently skipped it: test_isolation.py ran 8 of its 14 that
way, which meant the export-and-restore tests guarding against one patient's vault
leaking into another were invisible to anybody using the documented command.
"""
import pathlib
import re

TESTS = pathlib.Path(__file__).resolve().parent
# A real top-level runner starts a line. Matching the text anywhere found this file's own
# string literal first and failed on itself.
RUNNER = re.compile(r'^if __name__ == "__main__":', re.M)


def test_every_runner_is_the_last_thing_in_its_file():
    late = []
    for path in sorted(TESTS.glob("test_*.py")):
        source = path.read_text()
        found = RUNNER.search(source)
        if not found:
            continue
        tail = source[found.start():]
        if re.search(r"^def test_", tail, re.M):
            late.append(path.name)
    assert not late, f"tests defined after the runner, skipped when run directly: {late}"


def test_every_file_can_be_run_directly():
    missing = [p.name for p in sorted(TESTS.glob("test_*.py"))
               if not RUNNER.search(p.read_text())]
    assert not missing, f"no runner, so `python3 {missing[0]}` does nothing" if missing else ""


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
