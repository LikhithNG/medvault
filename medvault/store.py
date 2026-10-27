#!/usr/bin/env python3
"""A vault that survives the server restarting.

The problem. Streamlit Community Cloud gives an app a disk that does not outlive a reboot,
and it reboots on idle and on every redeploy. For a bill checker that is annoying. For
something called a vault it is a promise broken quietly — somebody files their paperwork,
comes back on Saturday, and it is gone.

The fix is a database that is not a file on that disk. libSQL (Turso) costs this project
the least of the options: it speaks SQLite's own dialect, so not one line of SQL in db.py
changes. Postgres would have meant rewriting every query for a different parameter style
and a different autoincrement, four days before a presentation.

**Why this talks HTTP by hand rather than using the official client.** The first version
imported libsql-client. Its synchronous client hung — under pytest, and again in a plain
probe outside it. Streamlit runs a script inside a thread that already owns an event loop,
which is exactly the shape that deadlocks an async client wrapped in a sync facade, and a
storage layer that sometimes never returns is worse than no storage layer at all. So this
speaks Turso's HTTP pipeline API with urllib, the same no-SDK discipline gemini.py and
groq.py already follow here. No dependency, no asyncio, no threads, nothing to deadlock.

Local SQLite stays the default and the tests never touch this. A vault on somebody's own
machine should be a file they can copy.
"""
import base64
import json
import os
import pathlib
import urllib.error
import urllib.request


def _load_env():
    """Settings come from the real environment first, then .env at the project root.

    Same loader gemini.py and groq.py use, for the same reason: credentials belong in a
    chmod 600 file that git ignores, not in a shell history or a screenshot.
    """
    env = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env()

REQUIRED = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")
TIMEOUT = int(os.environ.get("TURSO_TIMEOUT", "30"))
UA = "medvault/1.0 (INFO7375 coursework; python-urllib)"


def configured():
    """Whether a remote database is set up. Both halves or neither."""
    return all(os.environ.get(k, "").strip() for k in REQUIRED)


def missing():
    return [k for k in REQUIRED if not os.environ.get(k, "").strip()]


def endpoint(url):
    """Turso hands out libsql:// URLs; the HTTP API is the same host over https."""
    url = (url or "").strip().rstrip("/")
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url + "/v2/pipeline"


def encode(value):
    """A Python value as the protocol wants it. Integers travel as strings, which is how
    the API keeps 64-bit ids exact through JSON."""
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"type": "blob", "base64": base64.b64encode(bytes(value)).decode()}
    return {"type": "text", "value": str(value)}


def decode(cell):
    """One cell back. Blobs come back base64 so an uploaded scan survives the trip."""
    kind = (cell or {}).get("type")
    if kind in (None, "null"):
        return None
    if kind == "integer":
        return int(cell["value"])
    if kind == "float":
        return float(cell["value"])
    if kind == "blob":
        # The server returns base64 with the padding stripped, and may use the URL-safe
        # alphabet. b64decode insists on padding and rejects '-' and '_', so a stored
        # scan came back as "Incorrect padding" rather than as bytes. Found by running
        # tools/check_turso.py against a real database, which is the only place it could
        # have been found - the wire format tests used my own encoder for both halves.
        raw = (cell.get("base64") or "").strip().replace("-", "+").replace("_", "/")
        return base64.b64decode(raw + "=" * (-len(raw) % 4))
    return cell.get("value")


class StoreError(RuntimeError):
    pass


class Cursor:
    """What execute() hands back. Iterable, because db.py iterates it directly."""

    def __init__(self, result):
        cols = [c.get("name") for c in (result.get("cols") or [])]
        self._rows = [dict(zip(cols, (decode(c) for c in row)))
                      for row in (result.get("rows") or [])]
        rowid = result.get("last_insert_rowid")
        self.lastrowid = int(rowid) if rowid not in (None, "") else None
        self.rowcount = result.get("affected_row_count", -1)

    def __iter__(self):
        return iter(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class Connection:
    """A libSQL database wearing sqlite3's clothes.

    commit() is a no-op on purpose: each request over this protocol is its own
    transaction, so there is nothing held open. db.py should keep calling it — against a
    local file that call is load-bearing, and a storage layer that is only correct on one
    backend is not a storage layer.
    """

    def __init__(self, url, token, timeout=TIMEOUT):
        self._url, self._token, self._timeout = endpoint(url), token, timeout

    def _pipeline(self, statements):
        body = {"requests": [{"type": "execute",
                              "stmt": {"sql": sql,
                                       "args": [encode(a) for a in args],
                                       "want_rows": True}}
                             for sql, args in statements] + [{"type": "close"}]}
        request = urllib.request.Request(
            self._url, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._token}",
                     "Content-Type": "application/json", "User-Agent": UA},
            method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as problem:
            detail = problem.read()[:400].decode("utf-8", "ignore")
            raise StoreError(f"the vault database answered HTTP {problem.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, OSError) as problem:
            raise StoreError(f"the vault database could not be reached: {problem}")

        out = []
        for entry in payload.get("results", []):
            if entry.get("type") == "error":
                raise StoreError("the vault database rejected a statement: "
                                 + str((entry.get("error") or {}).get("message")))
            response = entry.get("response") or {}
            if response.get("type") == "execute":
                out.append(response.get("result") or {})
        return out

    def execute(self, sql, args=()):
        return Cursor(self._pipeline([(sql, list(args) if args else [])])[0])

    def executescript(self, script):
        # Safe for this schema: CREATE TABLE statements with no semicolon inside any
        # string literal. tests/test_store.py asserts that stays true.
        statements = [(s.strip(), []) for s in script.split(";") if s.strip()]
        if statements:
            self._pipeline(statements)
        return self

    def commit(self):
        return None

    def close(self):
        return None


def connect():
    """Open the remote vault, with an error a person mid-deploy can act on."""
    if not configured():
        raise StoreError(
            "Remote storage needs " + " and ".join(missing())
            + ". Set them in the app's secrets, or leave both unset to use a local file.")
    return Connection(os.environ["TURSO_DATABASE_URL"],
                      os.environ["TURSO_AUTH_TOKEN"].strip())


def describe():
    """One line for the diagnostics screen."""
    if not configured():
        return ("local file — survives only as long as this server does. Set "
                + " and ".join(REQUIRED) + " for a vault that outlives a restart.")
    host = endpoint(os.environ["TURSO_DATABASE_URL"]).split("://", 1)[-1].split("/")[0]
    return f"remote libSQL at {host}"
