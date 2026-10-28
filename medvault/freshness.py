#!/usr/bin/env python3
"""Making a deploy take effect without a reboot.

Streamlit reruns app.py on every click but keeps every module app.py imports, and the
hosted app picks up each push in place. So the newest app.py ran against modules from
several pushes earlier. That took the live site down twice - once over a footer that had
lost an argument, once over counts_by_kind gaining one - and kept the vault on a
connection an older db.py had opened, with a schema from before the care team existed.
"Reboot after every deploy" was the instruction, and it did not hold.

So before app.py imports anything from medvault/, it asks this whether the code on disk
is the code that is loaded. When it is not, every medvault module is dropped, and the
imports that follow load what is on disk. The caller clears Streamlit's cached
resources too, because a cached connection outlives the module that opened it.
"""
import pathlib
import sys

# Kept on sys, because sys is the one thing that outlives both a rerun of app.py and the
# modules this drops. Keyed by folder, so a test pointing this at a scratch folder cannot
# disturb the real one.
_STAMPS = "_medvault_code_stamps"


def stamp(folder):
    """What the code on disk looks like: every module's name, size and modified time."""
    return tuple(sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                        for p in pathlib.Path(folder).glob("*.py")))


def loaded_from(folder):
    """The modules currently imported from this folder."""
    root = pathlib.Path(folder).resolve()
    found = []
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if path and pathlib.Path(path).resolve().parent == root:
            found.append(name)
    return found


def ensure(folder):
    """Drop every module from `folder` if the code there changed since it was loaded.

    Returns the names dropped - empty when everything loaded is current. The first call
    in a process drops whatever is already loaded, because the only way modules get
    loaded before this runs is an older app.py that never called it, which is exactly
    the case this exists for. In a freshly started process nothing is loaded yet, so the
    first call drops nothing.
    """
    key = str(pathlib.Path(folder).resolve())
    stamps = getattr(sys, _STAMPS, None)
    if stamps is None:
        stamps = {}
        setattr(sys, _STAMPS, stamps)
    now = stamp(folder)
    if stamps.get(key) == now:
        return []
    stale = loaded_from(folder)
    for name in stale:
        del sys.modules[name]
    stamps[key] = now
    return stale
