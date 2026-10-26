#!/usr/bin/env python3
"""Storage. One SQLite file, created on first use, never migrated in place destructively.

Where this file lives is the whole privacy story of the product, so it is a single constant
rather than something each caller decides. MEDVAULT_DB points it elsewhere for tests.

Everything returns plain dicts. No ORM, no models leaking into the interface, and no silent
schema changes: add_column() is explicit and additive so an existing vault is never dropped
to make room for a new field.
"""
import json, os, pathlib, sqlite3, time

DEFAULT_PATH = pathlib.Path(os.environ.get(
    "MEDVAULT_DB", pathlib.Path(__file__).resolve().parent.parent / "vault.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT    NOT NULL,
    service_date TEXT,
    provider     TEXT,
    title        TEXT    NOT NULL,
    summary      TEXT,
    raw_text     TEXT,
    file_name    TEXT,
    file_mime    TEXT,
    file_bytes   BLOB,
    added_at     REAL    NOT NULL,
    read_by      TEXT
);
CREATE TABLE IF NOT EXISTS medications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id  INTEGER REFERENCES records(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    dose       TEXT,
    frequency  TEXT,
    duration   TEXT,
    reason     TEXT,
    active     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS profile (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(service_date);
CREATE INDEX IF NOT EXISTS idx_meds_record  ON medications(record_id);
"""


def connect(path=None):
    """A connection with foreign keys on and rows that behave like dicts."""
    p = pathlib.Path(path or DEFAULT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


def _rows(cur):
    return [dict(r) for r in cur.fetchall()]


# ---- records ---------------------------------------------------------------

def add_record(con, *, kind, title, service_date=None, provider=None, summary=None,
               raw_text=None, file_name=None, file_mime=None, file_bytes=None,
               read_by=None):
    """Store one document. Returns its id.

    file_bytes is the original the patient uploaded, kept so the vault can hand back the
    actual page at a hospital desk rather than only what a model made of it. A summary is
    useful; the original is evidence.
    """
    cur = con.execute(
        "INSERT INTO records (kind, service_date, provider, title, summary, raw_text,"
        " file_name, file_mime, file_bytes, added_at, read_by)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (kind, service_date, provider, title, summary, raw_text,
         file_name, file_mime, file_bytes, time.time(), read_by))
    con.commit()
    return cur.lastrowid


def list_records(con, kind=None, query=None, limit=500):
    """Newest first by the date on the document, falling back to when it was added.

    A record with no printed date must not vanish to the bottom of the timeline, which is
    what ORDER BY service_date alone does to every undated prescription.
    """
    sql = ("SELECT id, kind, service_date, provider, title, summary, file_name, file_mime,"
           " added_at, read_by, LENGTH(file_bytes) AS file_size FROM records")
    where, args = [], []
    if kind:
        where.append("kind = ?"); args.append(kind)
    if query:
        where.append("(title LIKE ? OR summary LIKE ? OR provider LIKE ? OR raw_text LIKE ?)")
        args += [f"%{query}%"] * 4
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(service_date, date(added_at,'unixepoch')) DESC, id DESC LIMIT ?"
    args.append(limit)
    return _rows(con.execute(sql, args))


def get_record(con, record_id):
    cur = con.execute("SELECT * FROM records WHERE id = ?", (record_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def delete_record(con, record_id):
    con.execute("DELETE FROM records WHERE id = ?", (record_id,))
    con.commit()


def counts_by_kind(con):
    return {r["kind"]: r["n"] for r in
            _rows(con.execute("SELECT kind, COUNT(*) AS n FROM records GROUP BY kind"))}


# ---- medications -----------------------------------------------------------

def add_medication(con, record_id, med):
    con.execute(
        "INSERT INTO medications (record_id, name, dose, frequency, duration, reason)"
        " VALUES (?,?,?,?,?,?)",
        (record_id, med.get("name"), med.get("dose"), med.get("frequency"),
         med.get("duration"), med.get("reason")))
    con.commit()


def list_medications(con, active_only=True):
    sql = ("SELECT m.*, r.service_date, r.provider FROM medications m"
           " LEFT JOIN records r ON r.id = m.record_id")
    if active_only:
        sql += " WHERE m.active = 1"
    sql += " ORDER BY COALESCE(r.service_date,'') DESC, m.id DESC"
    return _rows(con.execute(sql))


def set_medication_active(con, med_id, active):
    con.execute("UPDATE medications SET active = ? WHERE id = ?", (1 if active else 0, med_id))
    con.commit()


# ---- profile ---------------------------------------------------------------

def get_profile(con):
    return {r["key"]: r["value"] for r in _rows(con.execute("SELECT key, value FROM profile"))}


def save_profile(con, values):
    for k, v in values.items():
        con.execute("INSERT INTO profile (key, value) VALUES (?,?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (k, "" if v is None else str(v)))
    con.commit()


# ---- the whole vault, for export and import --------------------------------

def export_vault(con):
    """Everything except the stored originals, as JSON a person could read.

    The files are left out on purpose: this export is meant to be small enough to email to
    yourself, and a vault of scans is not. Originals stay in the database file.
    """
    return json.dumps({
        "exported_at": time.strftime("%Y-%m-%d %H:%M"),
        "profile": get_profile(con),
        "records": list_records(con, limit=10_000),
        "medications": list_medications(con, active_only=False),
    }, indent=2, default=str)
