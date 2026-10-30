#!/usr/bin/env python3
"""Storage. One SQLite file, created on first use, never migrated in place destructively.

Where this file lives is the whole privacy story of the product, so it is a single constant
rather than something each caller decides. MEDVAULT_DB points it elsewhere for tests.

Everything returns plain dicts. No ORM, no models leaking into the interface, and no silent
schema changes: add_column() is explicit and additive so an existing vault is never dropped
to make room for a new field.
"""
import json, os, pathlib, re, sqlite3, time

DEFAULT_PATH = pathlib.Path(os.environ.get(
    "MEDVAULT_DB", pathlib.Path(__file__).resolve().parent.parent / "vault.db"))

# agent_runs is how each agent run went - see runtime.py. Deliberately nothing about whose
# run it was or what it read: agent, timing, outcome, model, attempts, kind of failure.
#
# ai_use is how many AI reads each account started on each day - see quota.py. An account,
# a date and a count: never what was read, asked or answered. Days before today are
# deleted as soon as a new one is counted.
#
# care_views is when each clinician on a care team last had that patient's records on
# screen, and how many separate visits that was - see careteam.note_view. One row per
# pair, so it never grows past the size of the care team.
SCHEMA = """
CREATE TABLE IF NOT EXISTS care_team (
    patient_id   INTEGER NOT NULL,
    clinician_id INTEGER NOT NULL,
    added_at     REAL    NOT NULL,
    PRIMARY KEY (patient_id, clinician_id)
);
CREATE TABLE IF NOT EXISTS care_views (
    patient_id   INTEGER NOT NULL,
    clinician_id INTEGER NOT NULL,
    last_seen_at REAL    NOT NULL,
    visits       INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (patient_id, clinician_id)
);
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
CREATE TABLE IF NOT EXISTS lab_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id       INTEGER REFERENCES records(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    value           TEXT NOT NULL,
    unit            TEXT,
    reference_range TEXT,
    flag            TEXT
);
CREATE TABLE IF NOT EXISTS profile (
    account_id INTEGER NOT NULL DEFAULT 0,
    key        TEXT    NOT NULL,
    value      TEXT,
    PRIMARY KEY (account_id, key)
);
CREATE TABLE IF NOT EXISTS agent_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent       TEXT    NOT NULL,
    started_at  REAL    NOT NULL,
    seconds     REAL    NOT NULL,
    ok          INTEGER NOT NULL,
    model       TEXT,
    attempts    INTEGER,
    error_kind  TEXT,
    over_budget INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ai_use (
    account_id INTEGER NOT NULL,
    day        TEXT    NOT NULL,
    n          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, day)
);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent, started_at);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(service_date);
CREATE INDEX IF NOT EXISTS idx_meds_record  ON medications(record_id);
CREATE INDEX IF NOT EXISTS idx_labs_record  ON lab_results(record_id);
"""


# Columns added after the first version shipped. Applied with ALTER TABLE rather than by
# recreating the table, because a vault that drops a patient's records to make room for a
# new field is not a vault. Each entry is (table, column, definition) and running it twice
# is harmless.
ADDITIONS = [
    ("records", "provenance",  "TEXT NOT NULL DEFAULT 'SELF'"),
    ("records", "owner_id",    "INTEGER"),
    ("records", "verified_by", "INTEGER"),
    ("records", "verified_at", "REAL"),
    ("records", "verifier_note", "TEXT"),
]


def _migrate(con):
    # profile predates accounts and was keyed on `key` alone. Rebuilt rather than altered,
    # because the primary key itself has to change; the rows that exist are handed to the
    # first patient account, which is whose card they actually were.
    cols = {r["name"] for r in con.execute("PRAGMA table_info(profile)")}
    if cols and "account_id" not in cols:
        first = con.execute(
            "SELECT id FROM accounts WHERE role='patient' ORDER BY id LIMIT 1").fetchone()
        owner = first["id"] if first else 0
        con.execute("ALTER TABLE profile RENAME TO profile_old")
        con.executescript(SCHEMA)
        con.execute("INSERT OR REPLACE INTO profile (account_id, key, value)"
                    " SELECT ?, key, value FROM profile_old", (owner,))
        con.execute("DROP TABLE profile_old")
        con.commit()

    for table, column, decl in ADDITIONS:
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    con.commit()


def connect(path=None):
    """A connection with foreign keys on and rows that behave like dicts.

    Two backends, one surface. A local file by default - a vault on your own machine
    should be something you can copy - and a remote libSQL database when the app is
    hosted somewhere whose disk does not survive a restart. Same SQL either way: libSQL
    speaks SQLite's dialect, which is the entire reason it was chosen over Postgres.

    An explicit path always means the local file. Tests pass one, so they never reach for
    the network, and `MEDVAULT_DB` keeps working.
    """
    import store
    if path is None and store.configured():
        con = store.connect()
        con.executescript(SCHEMA)
        _migrate(con)
        import accounts
        accounts.ensure(con)
        return con

    p = pathlib.Path(path or DEFAULT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    _migrate(con)
    import accounts
    accounts.ensure(con)
    return con


def _rows(cur):
    return [dict(r) for r in cur.fetchall()]


# ---- records ---------------------------------------------------------------

def add_record(con, *, kind, title, service_date=None, provider=None, summary=None,
               raw_text=None, file_name=None, file_mime=None, file_bytes=None,
               read_by=None, provenance="SELF", owner_id=None, verified_by=None):
    """Store one document. Returns its id.

    file_bytes is the original the patient uploaded, kept so the vault can hand back the
    actual page at a hospital desk rather than only what a model made of it. A summary is
    useful; the original is evidence.
    """
    cur = con.execute(
        "INSERT INTO records (kind, service_date, provider, title, summary, raw_text,"
        " file_name, file_mime, file_bytes, added_at, read_by, provenance, owner_id,"
        " verified_by, verified_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (kind, service_date, provider, title, summary, raw_text,
         file_name, file_mime, file_bytes, time.time(), read_by, provenance, owner_id,
         verified_by, time.time() if verified_by else None))
    con.commit()
    return cur.lastrowid


def list_records(con, kind=None, query=None, limit=500, owner_id=None, owner_ids=None):
    """Newest first by the date on the document, falling back to when it was added.

    A record with no printed date must not vanish to the bottom of the timeline, which is
    what ORDER BY service_date alone does to every undated prescription.
    """
    sql = ("SELECT id, kind, service_date, provider, title, summary, file_name, file_mime,"
           " added_at, read_by, provenance, verified_by, verified_at, verifier_note,"
           " LENGTH(file_bytes) AS file_size FROM records")
    where, args = [], []
    # A patient screen must always pass their own id: without this filter every account saw
    # every other account's medical history.
    #
    # owner_ids is the clinician's path: the patients who put this clinician on their care
    # team. An EMPTY list means no records, never all of them - a clinician nobody has
    # chosen sees nothing. owner_id=None with no owner_ids still means "every record", and
    # nothing a person signs in to reaches that any more; it used to be how a clinician's
    # review queue saw every patient on the server.
    if owner_ids is not None:
        if not owner_ids:
            return []
        where.append(f"owner_id IN ({','.join('?' * len(owner_ids))})")
        args += list(owner_ids)
    elif owner_id is not None:
        where.append("owner_id = ?"); args.append(owner_id)
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


def delete_record(con, record_id, owner_id):
    """Delete one of this account's records, and the medicines and results that came off it.

    owner_id is required for the same reason get_profile's account_id is: a delete that
    does not know whose record it is would delete anybody's. Returns whether anything
    was deleted - False for a record that is not this owner's, which is left untouched.

    The medicines are deleted here rather than left to ON DELETE CASCADE. connect() turns
    foreign keys on for a local file, but the hosted vault's HTTP connection (store.py)
    never does, so there the cascade would silently not happen and the medicines would
    stay on the card with no record behind them.
    """
    if owner_id is None:
        raise ValueError("delete_record needs to know whose record it is deleting")
    if not con.execute("SELECT 1 FROM records WHERE id = ? AND owner_id = ?",
                       (record_id, owner_id)).fetchone():
        return False
    con.execute("DELETE FROM medications WHERE record_id = ?", (record_id,))
    con.execute("DELETE FROM lab_results WHERE record_id = ?", (record_id,))
    con.execute("DELETE FROM records WHERE id = ? AND owner_id = ?", (record_id, owner_id))
    con.commit()
    return True


def medicines_from(con, record_id):
    """How many medicines came off this record - what deleting it takes off the card."""
    row = con.execute("SELECT COUNT(*) AS n FROM medications WHERE record_id = ?",
                      (record_id,)).fetchone()
    return row["n"] if row else 0


def counts_by_kind(con, owner_id=None, owner_ids=None):
    sql = "SELECT kind, COUNT(*) AS n FROM records"
    args = []
    if owner_ids is not None:
        if not owner_ids:
            return {}
        sql += f" WHERE owner_id IN ({','.join('?' * len(owner_ids))})"
        args += list(owner_ids)
    elif owner_id is not None:
        sql += " WHERE owner_id = ?"; args.append(owner_id)
    return {r["kind"]: r["n"] for r in _rows(con.execute(sql + " GROUP BY kind", args))}


# ---- medications -----------------------------------------------------------

def add_medication(con, record_id, med):
    """Store one medicine. `active` False keeps a finished one finished - an export then an
    import used to bring every finished course back onto the emergency card."""
    con.execute(
        "INSERT INTO medications (record_id, name, dose, frequency, duration, reason, active)"
        " VALUES (?,?,?,?,?,?,?)",
        (record_id, med.get("name"), med.get("dose"), med.get("frequency"),
         med.get("duration"), med.get("reason"),
         0 if med.get("active") in (0, False, "0") else 1))
    con.commit()


def list_medications(con, active_only=True, owner_id=None):
    """Medicines belong to the record they came off, so they inherit its owner."""
    sql = ("SELECT m.*, r.service_date, r.provider FROM medications m"
           " LEFT JOIN records r ON r.id = m.record_id")
    where, args = [], []
    if active_only:
        where.append("m.active = 1")
    if owner_id is not None:
        where.append("r.owner_id = ?"); args.append(owner_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(r.service_date,'') DESC, m.id DESC"
    return _rows(con.execute(sql, args))


def set_medication_active(con, med_id, active):
    con.execute("UPDATE medications SET active = ? WHERE id = ?", (1 if active else 0, med_id))
    con.commit()


# ---- lab results -----------------------------------------------------------

LAB_COLUMNS = ("name", "value", "unit", "reference_range", "flag")


def add_lab_result(con, record_id, result):
    """Store one result, as printed. See schema.LAB_FIELDS."""
    con.execute("INSERT INTO lab_results (record_id, name, value, unit, reference_range, flag)"
                " VALUES (?,?,?,?,?,?)",
                (record_id, *(result.get(k) for k in LAB_COLUMNS)))
    con.commit()


def lab_results_by_record(con, owner_ids):
    """{record_id: [results, in the order printed]} for these owners' records.

    Scoped like list_records: an EMPTY list of owners means no results, never all of them.
    """
    if not owner_ids:
        return {}
    rows = _rows(con.execute(
        "SELECT l.* FROM lab_results l JOIN records r ON r.id = l.record_id"
        f" WHERE r.owner_id IN ({','.join('?' * len(owner_ids))}) ORDER BY l.id",
        list(owner_ids)))
    out = {}
    for row in rows:
        out.setdefault(row["record_id"], []).append(row)
    return out


# ---- profile ---------------------------------------------------------------

def get_profile(con, account_id):
    """One account's card. account_id is required - there is no "the" profile.

    This table used to be a bare key/value store with no account column, which meant every
    account on the server shared a single health card: a second person signing up was shown
    the first person's name, blood type, allergies and emergency contact. In a medical
    records app that is the worst defect available, and it is why account_id has no default
    here. A caller that does not know whose card it wants should not get one.
    """
    return {r["key"]: r["value"] for r in _rows(con.execute(
        "SELECT key, value FROM profile WHERE account_id = ?", (account_id,)))}


def save_profile(con, account_id, values):
    for k, v in values.items():
        con.execute("INSERT INTO profile (account_id, key, value) VALUES (?,?,?)"
                    " ON CONFLICT(account_id, key) DO UPDATE SET value = excluded.value",
                    (account_id, k, "" if v is None else str(v)))
    con.commit()


# ---- the whole vault, for export and import --------------------------------

def export_vault(con, account_id):
    """One account's vault, as JSON a person could read.

    account_id is required for the same reason get_profile's is. This function used to
    take none: it called get_profile(con) - which has not accepted that since the
    isolation fix, so it raised TypeError and had evidently never been called - and
    list_records(con, limit=10_000) with no owner filter, which would have written every
    account on the server into one file. A dead function kept a live defect.

    Stored originals are left out on purpose: this is meant to be small enough to email
    to yourself, and a vault of scans is not.
    """
    if account_id is None:
        raise ValueError("export_vault needs to know whose vault it is exporting")
    return json.dumps({
        "medvault_export": 1,
        "exported_at": time.strftime("%Y-%m-%d %H:%M"),
        "profile": get_profile(con, account_id),
        "records": list_records(con, limit=10_000, owner_id=account_id),
        "medications": list_medications(con, active_only=False, owner_id=account_id),
        "lab_results": [row for rows in lab_results_by_record(con, [account_id]).values()
                        for row in rows],
    }, indent=2, default=str)


RESTORABLE = ("kind", "service_date", "provider", "title", "summary", "read_by",
              "provenance")

# What one import may hold. A real vault's export is far under these; a file past them is
# not one, and on the hosted copy every record is a round trip to the database.
IMPORT_MAX_RECORDS = 2000
IMPORT_MAX_MEDICATIONS = 5000
IMPORT_MAX_LAB_RESULTS = 20000
_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _text(value, limit=20_000):
    if value is None:
        return None
    return str(value).strip()[:limit] or None


def _iso_date(value):
    """A real calendar date in a year the date arithmetic can handle, or None. "9999-12-30"
    plus a seven-day course overflowed and took the Medicines screen down."""
    import datetime
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        day = datetime.date.fromisoformat(text)
    except ValueError:
        return None
    return text if 1900 <= day.year <= 2100 else None


def _vetted(data):
    """An export, checked before anything is written: (records, medications, results,
    profile).

    A file of the wrong shape raises ValueError and writes nothing. Values inside a
    well-shaped file are cleaned rather than trusted - including card values a screen would
    fail on, such as organ_donor "maybe", which made the Card screen raise on every load
    with the restore control on that same screen.
    """
    from schema import BLOOD_TYPES, DONOR_CHOICES, KIND_ORDER, PROFILE_FIELDS
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("that file is not a MedVault export")
    records, meds = data["records"], data.get("medications") or []
    labs = data.get("lab_results") or []         # exports from before results have none
    profile = data.get("profile") or {}
    if not isinstance(meds, list) or not isinstance(labs, list) \
            or not isinstance(profile, dict) \
            or not all(isinstance(r, dict) for r in records + meds + labs):
        raise ValueError("that file is not a MedVault export")
    if len(records) > IMPORT_MAX_RECORDS or len(meds) > IMPORT_MAX_MEDICATIONS \
            or len(labs) > IMPORT_MAX_LAB_RESULTS:
        raise ValueError(f"that file holds more than {IMPORT_MAX_RECORDS} records, so it "
                         "is not an export of one vault")

    def whole(v):
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    clean_records = [{
        "id": whole(r.get("id")),
        "kind": r.get("kind") if r.get("kind") in KIND_ORDER else "other",
        "title": _text(r.get("title"), 300) or "Untitled record",
        "service_date": _iso_date(r.get("service_date")),
        "provider": _text(r.get("provider"), 300),
        "summary": _text(r.get("summary")),
        "read_by": _text(r.get("read_by"), 100),
    } for r in records]
    clean_meds = [{
        "record_id": whole(m.get("record_id")),
        "name": _text(m.get("name"), 200),
        **{k: _text(m.get(k), 500) for k in ("dose", "frequency", "duration", "reason")},
        "active": m.get("active") not in (0, False, "0"),
    } for m in meds if _text(m.get("name"))]

    def word(v, limit):
        return _text(v, limit) if isinstance(v, (str, int, float)) else None

    clean_labs = [{
        "record_id": whole(t.get("record_id")),
        "name": word(t.get("name"), 200), "value": word(t.get("value"), 200),
        "unit": word(t.get("unit"), 50), "reference_range": word(t.get("reference_range"), 100),
        "flag": word(t.get("flag"), 50),
    } for t in labs]
    clean_labs = [t for t in clean_labs if t["name"] and t["value"]]
    valid = {"organ_donor": DONOR_CHOICES, "blood_type": BLOOD_TYPES}
    clean_profile = {}
    for key, value in profile.items():
        if key not in PROFILE_FIELDS and key != "day_start":
            continue
        value = _text(value, 2000) or ""
        if key in valid and value not in valid[key]:
            continue
        if key == "day_start" and not _HHMM.fullmatch(value):
            continue
        clean_profile[key] = value
    return clean_records, clean_meds, clean_labs, clean_profile


def import_vault(con, account_id, payload):
    """Put an exported vault back, into this account. Returns what it did.

    Why this exists at all: hosted free tiers have ephemeral disks. A deployment reboots
    and the database file goes with it, which for a bill checker is annoying and for
    something called a vault is a broken promise. Export and import are what make the
    promise survivable without a paid database - and they also mean a person can leave
    with their own records, which a vault that only accepts deposits does not allow.

    A record already here with the same kind, title and date is skipped rather than
    duplicated, so restoring twice is safe.

    Provenance is deliberately NOT carried across. A record that a clinician confirmed on
    one server has no confirmation on this one: the verifying account does not exist here
    and the badge would be a claim with nothing behind it. Everything lands as SELF.
    """
    if account_id is None:
        raise ValueError("import_vault needs to know whose vault it is importing into")
    data = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    records, meds, labs, profile = _vetted(data)

    existing = {(r["kind"], r["title"], r.get("service_date"))
                for r in list_records(con, limit=10_000, owner_id=account_id)}

    added, skipped, meds_added, labs_added = 0, 0, 0, 0
    id_map = {}
    for row in records:
        key = (row["kind"], row["title"], row["service_date"])
        if key in existing:
            skipped += 1
            continue
        fields = {k: row.get(k) for k in RESTORABLE}
        # Imported, so unverified: see the docstring.
        fields["provenance"] = "SELF"
        new_id = add_record(con, owner_id=account_id, **fields)
        if row["id"] is not None:
            id_map[row["id"]] = new_id
        existing.add(key)
        added += 1

    for med in meds:
        target = id_map.get(med["record_id"])
        if target is None:
            continue            # its record was a duplicate, or carried no id to match
        add_medication(con, target, med)
        meds_added += 1

    for result in labs:
        target = id_map.get(result["record_id"])
        if target is None:
            continue
        add_lab_result(con, target, result)
        labs_added += 1

    if profile:
        save_profile(con, account_id, profile)

    return {"records_added": added, "records_skipped": skipped,
            "medications_added": meds_added, "lab_results_added": labs_added,
            "profile_restored": bool(profile)}


# ---- verification ----------------------------------------------------------

def verify_record(con, record_id, clinician_id, note=None):
    """A clinician confirms a record matches what they issued.

    Deliberately one-way and attributed: the row keeps who verified it and when, so a badge
    on screen can always be traced back to an account with a checked NPI.
    """
    con.execute("UPDATE records SET provenance='VERIFIED', verified_by=?, verified_at=?,"
                " verifier_note=? WHERE id=?",
                (clinician_id, time.time(), note, record_id))
    con.commit()


def unverify_record(con, record_id, note=None):
    """Withdraw a verification - a clinician who confirmed the wrong record must be able to
    take it back, and the record returns to self-filed rather than being deleted."""
    con.execute("UPDATE records SET provenance='SELF', verified_by=NULL, verified_at=NULL,"
                " verifier_note=? WHERE id=?", (note, record_id))
    con.commit()


def pending_verification(con, limit=200, owner_ids=None):
    """Self-filed records a clinician has not yet looked at, oldest first.

    owner_ids scopes it to the clinician's care team, and an empty team is an empty
    queue. Unscoped, this used to list every self-filed record on the server to every
    verified clinician - including patients who had never heard of them.
    """
    sql = ("SELECT id, owner_id, kind, service_date, provider, title, summary, added_at,"
           " provenance, LENGTH(file_bytes) AS file_size FROM records"
           " WHERE provenance = 'SELF'")
    args = []
    if owner_ids is not None:
        if not owner_ids:
            return []
        sql += f" AND owner_id IN ({','.join('?' * len(owner_ids))})"
        args += list(owner_ids)
    return _rows(con.execute(sql + " ORDER BY added_at ASC LIMIT ?", (*args, limit)))


def provenance_counts(con):
    return {r["provenance"]: r["n"] for r in _rows(con.execute(
        "SELECT provenance, COUNT(*) AS n FROM records GROUP BY provenance"))}


def ai_use(con, account_id, day):
    """(this account's AI reads on `day`, every account's) - the two counts quota.py needs."""
    row = con.execute("SELECT COALESCE(SUM(CASE WHEN account_id = ? THEN n END), 0) AS mine,"
                      " COALESCE(SUM(n), 0) AS site FROM ai_use WHERE day = ?",
                      (account_id, day)).fetchone()
    return int(row["mine"]), int(row["site"])


def count_ai_use(con, account_id, day):
    """One more AI read for this account on `day`. Earlier days go as this one is counted."""
    con.execute("DELETE FROM ai_use WHERE day < ?", (day,))
    con.execute("INSERT INTO ai_use (account_id, day, n) VALUES (?, ?, 1)"
                " ON CONFLICT(account_id, day) DO UPDATE SET n = n + 1", (account_id, day))
    con.commit()


def take_ai_use(con, account_id, day, per_account, site):
    """count_ai_use, only while this account is under `per_account` and everyone under
    `site` on `day`. True when it counted.

    The check and the count are one statement. As two, every tab and every person that
    looked before the first count landed could start a read - three tabs at 9 of 10 ended
    at 12. (The WHERE on the SELECT is also what lets SQLite parse the ON CONFLICT.)
    """
    con.execute("DELETE FROM ai_use WHERE day < ?", (day,))
    cur = con.execute(
        "INSERT INTO ai_use (account_id, day, n) SELECT ?, ?, 1"
        " WHERE (SELECT COALESCE(SUM(n), 0) FROM ai_use WHERE day = ?) < ?"
        " AND (SELECT COALESCE(SUM(n), 0) FROM ai_use"
        "      WHERE day = ? AND account_id = ?) < ?"
        " ON CONFLICT(account_id, day) DO UPDATE SET n = n + 1",
        (account_id, day, day, site, day, account_id, per_account))
    con.commit()
    # -1 is "the database did not say" (store.Cursor's default). Read as counted: a
    # missing number must not lock every account out of every read.
    return cur.rowcount != 0
