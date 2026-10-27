#!/usr/bin/env python3
"""The storage backend that survives a restart.

Streamlit Community Cloud gives an app a disk that does not outlive a reboot, and reboots
on idle and on every redeploy. A vault that loses everything on Saturday morning is not a
vault.

These test the wire format and the routing, which is what can be tested without an
account. The round trip against a real Turso database is tools/check_turso.py, run once
with real credentials — stated plainly rather than implied by a green suite.
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import db      # noqa: E402
import store   # noqa: E402


def clear():
    import os
    for key in store.REQUIRED:
        os.environ.pop(key, None)


def test_a_local_file_is_the_default():
    clear()
    assert not store.configured()


def test_half_a_configuration_does_not_count():
    """A URL with no token would fail at the first query, in front of somebody."""
    import os
    clear()
    os.environ["TURSO_DATABASE_URL"] = "libsql://example.turso.io"
    try:
        assert not store.configured()
        assert store.missing() == ["TURSO_AUTH_TOKEN"]
    finally:
        clear()


def test_connecting_without_secrets_says_which_one_is_missing():
    clear()
    try:
        store.connect()
    except store.StoreError as problem:
        assert "TURSO_DATABASE_URL" in str(problem)
        return
    raise AssertionError("connected with no configuration")


def test_an_explicit_path_always_means_the_local_file():
    """Tests pass a path, so they never reach for the network however the environment is
    set. Without this, a developer with Turso secrets exported would have every test in
    this suite writing to the real vault."""
    import os
    import sqlite3
    clear()
    os.environ["TURSO_DATABASE_URL"] = "libsql://example.turso.io"
    os.environ["TURSO_AUTH_TOKEN"] = "not-a-real-token"
    try:
        con = db.connect(tempfile.mktemp(suffix=".db"))
        assert isinstance(con, sqlite3.Connection)
    finally:
        clear()


def test_a_libsql_url_becomes_the_http_endpoint():
    assert store.endpoint("libsql://x.turso.io") == "https://x.turso.io/v2/pipeline"
    assert store.endpoint("https://x.turso.io/") == "https://x.turso.io/v2/pipeline"
    assert store.endpoint("x.turso.io") == "https://x.turso.io/v2/pipeline"


def test_an_integer_travels_as_a_string():
    """How the protocol keeps a 64-bit row id exact through JSON."""
    assert store.encode(2 ** 53 + 1) == {"type": "integer", "value": str(2 ** 53 + 1)}
    assert store.decode({"type": "integer", "value": str(2 ** 53 + 1)}) == 2 ** 53 + 1


def test_a_scan_survives_the_round_trip():
    """file_bytes is an uploaded original. If blobs do not round trip, the vault hands
    back a corrupted page at a hospital desk."""
    page = bytes(range(256)) * 4
    assert store.decode(store.encode(page)) == page


def test_a_blob_decodes_however_the_server_encoded_it():
    """This is the test that was missing, and the shape of the hole is worth keeping.

    The round-trip test above encodes with store.encode and decodes with store.decode —
    so it only ever proved the two agree with each other. The real server strips base64
    padding, and b64decode refuses input without it, so an uploaded scan came back as
    "Incorrect padding" against a live database while the suite stayed green. These
    encode the SAME bytes three ways the server legitimately might, none of them using
    store.encode."""
    import base64
    page = bytes(range(256)) * 4
    standard = base64.b64encode(page).decode()

    for label, encoded in (
            ("padded", standard),
            ("padding stripped", standard.rstrip("=")),
            ("url-safe, unpadded",
             base64.urlsafe_b64encode(page).decode().rstrip("=")),
    ):
        assert store.decode({"type": "blob", "base64": encoded}) == page, label


def test_an_empty_blob_is_empty_bytes_not_an_error():
    assert store.decode({"type": "blob", "base64": ""}) == b""


def test_every_type_the_schema_uses_round_trips():
    for value in (None, 0, 1, -17, 3.5, "", "text", True, b"\x00\xff"):
        out = store.decode(store.encode(value))
        assert out == (int(value) if isinstance(value, bool) else value), value


def test_a_cursor_behaves_like_sqlite3s():
    cur = store.Cursor({
        "cols": [{"name": "id"}, {"name": "title"}],
        "rows": [[{"type": "integer", "value": "1"}, {"type": "text", "value": "Panel"}],
                 [{"type": "integer", "value": "2"}, {"type": "null"}]],
        "last_insert_rowid": "2", "affected_row_count": 2})

    assert [r["title"] for r in cur] == ["Panel", None]
    assert cur.fetchone()["id"] == 1
    assert len(cur.fetchall()) == 2
    assert cur.lastrowid == 2


def test_an_empty_result_fetches_none_rather_than_raising():
    empty = store.Cursor({"cols": [], "rows": [], "last_insert_rowid": None})
    assert empty.fetchone() is None and empty.fetchall() == []
    assert empty.lastrowid is None


def test_the_schema_can_be_split_on_semicolons():
    """executescript splits on ';'. That is safe for this schema and has to stay safe."""
    statements = [s for s in db.SCHEMA.split(";") if s.strip()]
    assert len(statements) >= 4
    for s in statements:
        assert s.count("'") % 2 == 0, f"a semicolon in a string literal would break: {s[:40]}"


def test_an_unreachable_database_raises_something_readable():
    con = store.Connection("https://127.0.0.1:9/", "token", timeout=2)
    try:
        con.execute("SELECT 1")
    except store.StoreError as problem:
        assert "could not be reached" in str(problem) or "HTTP" in str(problem)
        return
    raise AssertionError("a dead endpoint did not raise")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
