#!/usr/bin/env python3
"""Prove the remote vault works, before a presentation depends on it.

    TURSO_DATABASE_URL="libsql://...turso.io" TURSO_AUTH_TOKEN="..." \
        python3 tools/check_turso.py

The unit tests cover the wire format and the routing. They cannot cover the round trip,
because that needs a real database and an account — so this is the part that has to be
run by hand once, and it is better to say that than to let a green suite imply it.

It writes into a scratch table, reads it back, and drops it. Nothing in the vault's own
tables is touched.
"""
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import store   # noqa: E402

TABLE = "medvault_connection_check"


def main():
    if not store.configured():
        print("Not configured. Set " + " and ".join(store.missing()))
        return 2

    print(f"Checking {store.describe()}\n")
    con = store.connect()
    started = time.perf_counter()

    checks = []

    def step(label, fn):
        begin = time.perf_counter()
        try:
            outcome = fn()
            ms = (time.perf_counter() - begin) * 1000
            print(f"  ok    {label:<42} {ms:7.0f} ms   {outcome if outcome else ''}")
            checks.append(True)
        except Exception as problem:            # noqa: BLE001 - reported, not swallowed
            print(f"  FAIL  {label:<42}         {type(problem).__name__}: {problem}")
            checks.append(False)

    step("reachable", lambda: con.execute("SELECT 1 AS one").fetchone()["one"] == 1 and "")
    step("create a scratch table", lambda: con.executescript(
        f"DROP TABLE IF EXISTS {TABLE};"
        f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        f" label TEXT, size REAL, page BLOB)") and "")

    page = bytes(range(256)) * 8      # stands in for an uploaded scan

    def insert():
        cur = con.execute(f"INSERT INTO {TABLE} (label, size, page) VALUES (?,?,?)",
                          ("a record", 1.5, page))
        return f"row id {cur.lastrowid}"

    step("insert, and get the row id back", insert)

    def read_back():
        row = con.execute(f"SELECT * FROM {TABLE} ORDER BY id DESC LIMIT 1").fetchone()
        assert row["label"] == "a record", "text did not survive"
        assert row["size"] == 1.5, "float did not survive"
        assert row["page"] == page, "a blob did not survive — uploaded scans would corrupt"
        return f"{len(row['page'])} byte blob intact"

    step("read it back, every column", read_back)
    step("the vault's own tables are visible", lambda: ", ".join(sorted(
        r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('records','medications','profile','accounts')"))) or "none yet — "
        "the app creates them on first run")
    step("clean up", lambda: con.execute(f"DROP TABLE IF EXISTS {TABLE}") and "")

    total = (time.perf_counter() - started) * 1000
    ok = all(checks)
    print(f"\n{'ALL CHECKS PASSED' if ok else 'SOMETHING FAILED'} · {total:.0f} ms total")
    if ok:
        print("The vault will outlive a restart. Set the same two secrets in the "
              "Streamlit app's settings.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
