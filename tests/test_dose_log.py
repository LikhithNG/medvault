#!/usr/bin/env python3
"""The dose log in the vault: a taken dose comes out of the box, an undone one goes back.

Stock is moved by the log and only by the log, so these tests are about the two ways a
count drifts from the truth: taking the same dose off twice, and putting back a different
amount from the one that was taken off. And, as everywhere in this vault, about one
patient never reaching another's medicines.

Run with  python3 tests/test_dose_log.py
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "medvault"))
import accounts, db, doselog                                         # noqa: E402

DAY = "2026-11-03"


def vault_with_one_medicine(dose="1 tablet", **stock):
    con = db.connect(tempfile.mktemp(suffix=".db"))
    owner, _ = accounts.create(con, email="a@example.com", password="12345678", role="patient")
    rid = db.add_record(con, kind="prescription", title="Rx", service_date=DAY, owner_id=owner["id"])
    db.add_medication(con, rid, {"name": "Amoxicillin", "dose": dose, "frequency": "twice daily"})
    med_id = db.list_medications(con, owner_id=owner["id"])[0]["id"]
    if stock:
        doselog.set_stock(con, med_id, owner["id"], **stock)
    return con, owner["id"], med_id


def stock_of(con, owner, med_id):
    return next(m for m in db.list_medications(con, owner_id=owner) if m["id"] == med_id)["stock"]


def test_a_taken_dose_comes_out_of_the_box():
    con, me, med = vault_with_one_medicine(stock=10)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    assert stock_of(con, me, med) == 9


def test_a_skipped_dose_uses_no_stock():
    con, me, med = vault_with_one_medicine(stock=10)
    doselog.record_dose(con, med, DAY, "08:00", "skipped", owner_id=me)
    assert stock_of(con, me, med) == 10
    assert doselog.dose_log(con, me)[0]["status"] == "skipped"


def test_marking_the_same_dose_twice_takes_it_off_once():
    con, me, med = vault_with_one_medicine(stock=10)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    assert stock_of(con, me, med) == 9
    assert len(doselog.dose_log(con, me)) == 1


def test_changing_taken_to_skipped_puts_the_dose_back():
    con, me, med = vault_with_one_medicine(stock=10)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    doselog.record_dose(con, med, DAY, "08:00", "skipped", owner_id=me)
    assert stock_of(con, me, med) == 10


def test_undo_puts_back_what_was_taken_even_if_the_dose_changed_since():
    """MedTimer stores the stock before and after each event for exactly this reason: the
    amount to restore is the amount that was removed, not today's dose size."""
    con, me, med = vault_with_one_medicine(stock=10)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    doselog.set_stock(con, med, me, per_dose=2)
    doselog.undo_dose(con, med, DAY, "08:00", owner_id=me)
    assert stock_of(con, me, med) == 10
    assert doselog.dose_log(con, me) == []


def test_the_last_half_tablet_is_all_that_is_taken_and_all_that_comes_back():
    con, me, med = vault_with_one_medicine(stock=0.5)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    assert stock_of(con, me, med) == 0
    doselog.undo_dose(con, med, DAY, "08:00", owner_id=me)
    assert stock_of(con, me, med) == 0.5


def test_a_dose_with_no_count_is_logged_but_leaves_the_stock_alone():
    con, me, med = vault_with_one_medicine(dose="500 mg", stock=30)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    assert stock_of(con, me, med) == 30
    assert doselog.dose_log(con, me)[0]["used"] is None


def test_untracked_stock_stays_untracked():
    con, me, med = vault_with_one_medicine()
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    assert stock_of(con, me, med) is None


def test_clearing_the_stock_stops_the_count_and_keeps_the_rest():
    """An empty "In the box now" field arrives as stock=None: not counted any more, which is
    not the same as an empty box - and the refill size and expiry stay as they were."""
    con, me, med = vault_with_one_medicine(stock=10, refill_size=30, expires="2027-01-31")
    doselog.set_stock(con, med, me, stock=None)
    row = db.list_medications(con, owner_id=me)[0]
    assert (row["stock"], row["refill_size"], row["expires"]) == (None, 30, "2027-01-31")


def test_a_refill_adds_the_refill_size():
    con, me, med = vault_with_one_medicine(stock=2, refill_size=30)
    doselog.refill(con, med, me)
    assert stock_of(con, me, med) == 32


def test_a_refill_with_no_size_is_refused():
    con, me, med = vault_with_one_medicine(stock=2)
    try:
        doselog.refill(con, med, me)
    except ValueError:
        return
    raise AssertionError("a refill of unknown size changed nothing and said nothing")


class DropsOn:
    """A connection that fails the first statement starting with `prefix`, as the hosted
    vault's HTTP connection does when the network goes between two statements."""
    def __init__(self, con, prefix):
        self.con, self.prefix, self.dropped = con, prefix, False

    def execute(self, sql, args=()):
        if not self.dropped and sql.lstrip().upper().startswith(self.prefix):
            self.dropped = True
            raise ConnectionError("the network went")
        return self.con.execute(sql, args)

    def commit(self):
        return self.con.commit()


def _consistent(con, me, med, full=10):
    """The box and the log agree: what is missing from it is what the log says was taken."""
    used = sum(r["used"] or 0 for r in doselog.dose_log(con, me))
    assert stock_of(con, me, med) == full - used, (stock_of(con, me, med), used)


def test_a_connection_lost_mid_change_leaves_the_box_and_the_log_agreeing():
    """Each step used to be two statements, the stock and then the log. On the hosted
    vault each statement is its own transaction, so a drop between them left a stock
    taken off with no dose to show for it, or put back while the dose stayed logged."""
    con, me, med = vault_with_one_medicine(stock=10)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    for prefix in ("INSERT", "DELETE"):
        flaky = DropsOn(con, prefix)
        try:
            doselog.record_dose(flaky, med, DAY, "08:00", "skipped", owner_id=me)
        except ConnectionError:
            pass
        _consistent(con, me, med)
        doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)     # and retried
        _consistent(con, me, med)
    assert stock_of(con, me, med) == 9


def test_not_a_number_is_not_a_stock():
    """json.loads reads a bare NaN; every comparison with it is False, so it passed."""
    con, me, med = vault_with_one_medicine()
    try:
        doselog.set_stock(con, med, me, stock=float("nan"))
    except ValueError:
        return
    raise AssertionError("NaN was stored as a stock")


def test_stock_values_are_checked_before_they_are_stored():
    con, me, med = vault_with_one_medicine()
    for bad in ({"stock": -1}, {"per_dose": 0}, {"per_dose": 0.001}, {"stock": 10 ** 9},
                {"expires": "31/12/2026"}, {"status": "taken"}):
        try:
            doselog.set_stock(con, med, me, **bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"accepted {bad}")


def test_a_bad_status_or_time_is_refused():
    con, me, med = vault_with_one_medicine(stock=10)
    for day, at, status in ((DAY, "08:00", "maybe"), (DAY, "8am", "taken"), ("tomorrow", "08:00", "taken")):
        try:
            doselog.record_dose(con, med, day, at, status, owner_id=me)
        except ValueError:
            continue
        raise AssertionError(f"accepted {day} {at} {status}")


def test_another_patient_cannot_log_a_dose_on_my_medicine():
    con, me, med = vault_with_one_medicine(stock=10)
    other, _ = accounts.create(con, email="b@example.com", password="12345678", role="patient")
    for act in (lambda: doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=other["id"]),
                lambda: doselog.set_stock(con, med, other["id"], stock=0),
                lambda: doselog.refill(con, med, other["id"])):
        try:
            act()
        except PermissionError:
            continue
        raise AssertionError("one patient changed another's medicine")
    assert stock_of(con, me, med) == 10


def test_another_patient_does_not_see_my_log():
    con, me, med = vault_with_one_medicine(stock=10)
    other, _ = accounts.create(con, email="b@example.com", password="12345678", role="patient")
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    assert doselog.dose_log(con, other["id"]) == []


def test_deleting_the_record_deletes_its_doses():
    """With foreign keys off, as on the hosted vault's connection: the cascade would
    silently not happen there, so the delete has to do it itself."""
    con, me, med = vault_with_one_medicine(stock=10)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    con.execute("PRAGMA foreign_keys = OFF")
    rid = db.list_medications(con, owner_id=me)[0]["record_id"]
    db.delete_record(con, rid, me)
    assert con.execute("SELECT COUNT(*) AS n FROM dose_log").fetchone()["n"] == 0


def test_an_export_and_import_bring_back_the_stock_and_the_log():
    con, me, med = vault_with_one_medicine(stock=10, refill_size=30, expires="2027-01-31")
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    payload = db.export_vault(con, me)

    fresh = db.connect(tempfile.mktemp(suffix=".db"))
    them, _ = accounts.create(fresh, email="a@example.com", password="12345678", role="patient")
    done = db.import_vault(fresh, them["id"], payload)

    restored = db.list_medications(fresh, owner_id=them["id"])[0]
    assert (restored["stock"], restored["refill_size"], restored["expires"]) == (9, 30, "2027-01-31")
    log = doselog.dose_log(fresh, them["id"])
    assert [(r["day"], r["at"], r["status"], r["used"]) for r in log] == [(DAY, "08:00", "taken", 1)]
    assert log[0]["med_id"] == restored["id"]
    assert done["doses_added"] == 1


def test_a_file_listing_one_medicine_twice_does_not_inflate_either_copy():
    con, me, med = vault_with_one_medicine(stock=10)
    doselog.record_dose(con, med, DAY, "08:00", "taken", owner_id=me)
    data = json.loads(db.export_vault(con, me))
    data["medications"] = data["medications"] * 2          # same id, twice

    fresh = db.connect(tempfile.mktemp(suffix=".db"))
    them, _ = accounts.create(fresh, email="a@example.com", password="12345678", role="patient")
    db.import_vault(fresh, them["id"], data)
    assert [m["stock"] for m in db.list_medications(fresh, owner_id=them["id"])] == [9, 9]


def test_a_second_tap_on_the_same_dose_at_the_same_moment_is_ignored_not_an_error():
    """Two sessions, one dose: the second insert meets the first one's row."""
    con, me, med = vault_with_one_medicine(stock=10)
    con.execute("INSERT INTO dose_log (med_id, day, at, status, used, recorded_at)"
                " VALUES (?, ?, ?, 'taken', 1, 0)", (med, DAY, "08:00"))
    real = con.execute

    class Racing:
        """Lets the DELETE run, then puts the other session's row back before the INSERT."""
        def execute(self, sql, args=()):
            out = real(sql, args)
            if sql.startswith("DELETE FROM dose_log"):
                real("INSERT INTO dose_log (med_id, day, at, status, used, recorded_at)"
                     " VALUES (?, ?, ?, 'taken', 1, 0)", (med, DAY, "08:00"))
            return out

        def commit(self):
            return con.commit()

    doselog.record_dose(Racing(), med, DAY, "08:00", "taken", owner_id=me)
    assert len(doselog.dose_log(con, me)) == 1
    _consistent(con, me, med)


def test_an_import_drops_log_entries_it_cannot_trust():
    con, me, med = vault_with_one_medicine(stock=10)
    data = json.loads(db.export_vault(con, me))
    data["dose_log"] = [{"med_id": data["medications"][0]["id"], "day": "not a day", "at": "08:00",
                         "status": "taken"},
                        {"med_id": data["medications"][0]["id"], "day": DAY, "at": "25:00",
                         "status": "taken"},
                        {"med_id": data["medications"][0]["id"], "day": DAY, "at": "08:00",
                         "status": "drunk"},
                        {"med_id": 99999, "day": DAY, "at": "08:00", "status": "taken"}]

    fresh = db.connect(tempfile.mktemp(suffix=".db"))
    them, _ = accounts.create(fresh, email="a@example.com", password="12345678", role="patient")
    done = db.import_vault(fresh, them["id"], data)
    assert done["doses_added"] == 0
    assert doselog.dose_log(fresh, them["id"]) == []


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
