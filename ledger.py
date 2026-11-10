"""The locker ledger: bills, locked money and payments, stored in SQLite.

Money is always stored as whole cents (integers) to avoid rounding errors.
Payment life cycle: LOCKED -> RESERVED -> PENDING -> SUCCESS
                    (a rejected payment becomes FAILED and can be retried)
"""
import sqlite3
import calendar
from datetime import date

DB_PATH = "locker.db"


class LedgerError(Exception):
    """Raised when an action would break a ledger rule."""


def dollars(cents):
    """Format cents for display, e.g. 12345 -> '$123.45'. Display only."""
    return f"${cents / 100:,.2f}"


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            payee_email TEXT NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'monthly'
                CHECK (frequency IN ('monthly', 'yearly', 'one_time')),
            due_day INTEGER NOT NULL DEFAULT 1 CHECK (due_day BETWEEN 1 AND 31),
            due_date TEXT
        );
        CREATE TABLE IF NOT EXISTS cycles (
            cycle_id TEXT PRIMARY KEY,
            salary_cents INTEGER NOT NULL CHECK (salary_cents >= 0),
            locked_cents INTEGER NOT NULL CHECK (locked_cents >= 0),
            start_date TEXT,
            end_date TEXT
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id TEXT NOT NULL REFERENCES cycles(cycle_id),
            bill_id INTEGER NOT NULL REFERENCES bills(id),
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            status TEXT NOT NULL DEFAULT 'LOCKED',
            attempts INTEGER NOT NULL DEFAULT 1,
            batch_id TEXT NOT NULL,
            payout_id TEXT,
            due_date TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (cycle_id, bill_id)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id TEXT,
            kind TEXT NOT NULL,
            amount_cents INTEGER,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()


def _log(conn, cycle_id, kind, amount_cents=None, note=None):
    conn.execute(
        "INSERT INTO events (cycle_id, kind, amount_cents, note) VALUES (?, ?, ?, ?)",
        (cycle_id, kind, amount_cents, note),
    )


def add_bill(conn, name, amount_cents, payee_email, frequency="monthly",
             due_day=1, due_date=None):
    if frequency in ("yearly", "one_time") and not due_date:
        raise ValueError(f"{frequency} bills need a due_date")
    with conn:
        cursor = conn.execute(
            "INSERT INTO bills (name, amount_cents, payee_email, frequency, due_day, due_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, amount_cents, payee_email, frequency, due_day, due_date),
        )
    return cursor.lastrowid


def list_bills(conn, frequency=None):
    if frequency:
        return conn.execute(
            "SELECT * FROM bills WHERE frequency = ? ORDER BY id", (frequency,)
        ).fetchall()
    return conn.execute("SELECT * FROM bills ORDER BY id").fetchall()


def get_cycle(conn, cycle_id):
    row = conn.execute(
        "SELECT * FROM cycles WHERE cycle_id = ?", (cycle_id,)
    ).fetchone()
    if row is None:
        raise LedgerError(f"Cycle {cycle_id} has not been started")
    return row


def start_cycle(conn, cycle_id, salary_cents, start_date=None, end_date=None):
    """Lock the bills due in the window, or every monthly bill if no dates are given."""
    locked = []  # pairs of (bill, due date as text)
    if start_date is None:
        for bill in list_bills(conn, "monthly"):
            locked.append((bill, None))
    else:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if end < start:
            raise LedgerError("End date is before the start date")
        if (end - start).days + 1 > 31:
            raise LedgerError("A cycle window can be at most 31 days")
        for bill in list_bills(conn):
            dates = due_dates_in_window(
                bill["frequency"], bill["due_day"], bill["due_date"], start, end
            )
            if dates:
                locked.append((bill, dates[0].isoformat()))

    total = sum(bill["amount_cents"] for bill, _ in locked)
    if total > salary_cents:
        raise LedgerError(
            f"Shortfall: bills total {dollars(total)} but salary is {dollars(salary_cents)}"
        )
    try:
        with conn:
            conn.execute(
                "INSERT INTO cycles (cycle_id, salary_cents, locked_cents, start_date, end_date) "
                "VALUES (?, ?, ?, ?, ?)",
                (cycle_id, salary_cents, total, start_date, end_date),
            )
            for bill, due in locked:
                conn.execute(
                    "INSERT INTO payments (cycle_id, bill_id, amount_cents, batch_id, due_date) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (cycle_id, bill["id"], bill["amount_cents"],
                     f"{cycle_id}-bill{bill['id']}-a1", due),
                )
            _log(conn, cycle_id, "salary_received", salary_cents)
            _log(conn, cycle_id, "bills_locked", total, f"{len(locked)} bills")
    except sqlite3.IntegrityError:
        raise LedgerError(f"Cycle {cycle_id} has already been started")
    return total


def safe_to_spend(conn, cycle_id):
    cycle = get_cycle(conn, cycle_id)
    return cycle["salary_cents"] - cycle["locked_cents"]


def locker_balance(conn, cycle_id):
    """Money still held in the locker (not yet sent to PayPal)."""
    get_cycle(conn, cycle_id)
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM payments "
        "WHERE cycle_id = ? AND status IN ('LOCKED', 'FAILED')",
        (cycle_id,),
    ).fetchone()
    return row["total"]


def reserve_payment(conn, cycle_id, bill_id):
    """Claim a locked bill for payment. Returns what the caller needs to pay it."""
    row = conn.execute(
        "SELECT p.id, p.status, p.attempts, p.amount_cents, b.name, b.payee_email "
        "FROM payments p JOIN bills b ON b.id = p.bill_id "
        "WHERE p.cycle_id = ? AND p.bill_id = ?",
        (cycle_id, bill_id),
    ).fetchone()
    if row is None:
        raise LedgerError(f"Bill {bill_id} was not locked for cycle {cycle_id}")
    if row["status"] not in ("LOCKED", "FAILED"):
        raise LedgerError(
            f"Bill {bill_id} is already {row['status']} for cycle {cycle_id}"
        )
    attempts = row["attempts"] + (1 if row["status"] == "FAILED" else 0)
    batch_id = f"{cycle_id}-bill{bill_id}-a{attempts}"
    with conn:
        cursor = conn.execute(
            "UPDATE payments SET status = 'RESERVED', attempts = ?, batch_id = ?, "
            "updated_at = datetime('now') "
            "WHERE id = ? AND status IN ('LOCKED', 'FAILED')",
            (attempts, batch_id, row["id"]),
        )
        if cursor.rowcount != 1:
            raise LedgerError(f"Bill {bill_id} changed while reserving it")
        _log(conn, cycle_id, "payment_reserved", row["amount_cents"],
             f"{row['name']} ({batch_id})")
    return {
        "batch_id": batch_id,
        "amount_cents": row["amount_cents"],
        "payee_email": row["payee_email"],
        "bill_name": row["name"],
    }


VALID_STATUSES = ("PENDING", "SUCCESS", "FAILED")


def mark_payment(conn, cycle_id, bill_id, status, payout_id=None):
    """Record PayPal's answer for a reserved or pending payment."""
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}")
    with conn:
        cursor = conn.execute(
            "UPDATE payments SET status = ?, payout_id = COALESCE(?, payout_id), "
            "updated_at = datetime('now') "
            "WHERE cycle_id = ? AND bill_id = ? AND status IN ('RESERVED', 'PENDING')",
            (status, payout_id, cycle_id, bill_id),
        )
        if cursor.rowcount != 1:
            raise LedgerError(
                f"Bill {bill_id} is not waiting for a result in cycle {cycle_id}"
            )
        _log(conn, cycle_id, f"payment_{status.lower()}", None, f"bill {bill_id}")


def summary(conn, cycle_id):
    cycle = get_cycle(conn, cycle_id)
    payments = conn.execute(
        "SELECT b.name, p.amount_cents, p.status , p.due_date FROM payments p "
        "JOIN bills b ON b.id = p.bill_id WHERE p.cycle_id = ? ORDER BY p.id",
        (cycle_id,),
    ).fetchall()
    return {
        "cycle_id": cycle_id,
        "salary_cents": cycle["salary_cents"],
        "locked_cents": cycle["locked_cents"],
        "safe_to_spend_cents": cycle["salary_cents"] - cycle["locked_cents"],
        "locker_balance_cents": locker_balance(conn, cycle_id),
        "payments": [dict(p) for p in payments],
    }

def payments_with_status(conn, cycle_id, *statuses):
    """Payments in a cycle whose status is one of the given statuses."""
    marks = ",".join("?" * len(statuses))
    return conn.execute(
        "SELECT bill_id, payout_id, amount_cents, batch_id FROM payments "
        f"WHERE cycle_id = ? AND status IN ({marks}) ORDER BY id",
        (cycle_id, *statuses),
    ).fetchall()



def due_dates_in_window(frequency, due_day, due_date, start, end):
    """Return a sorted list of date objects inside [start, end] when a bill is due.

    monthly: due_day of every month the window touches (use the last day if short)
    yearly or one_time: due_date, a 'YYYY-MM-DD' string, if it falls in the window
    """
    if frequency in ("yearly", "one_time"):
        when = date.fromisoformat(due_date)
        return [when] if start <= when <= end else []      # GAP 1: must RETURN

    dates = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        last_day = calendar.monthrange(year, month)[1]
        candidate = date(year, month, min(due_day, last_day))
        if start <= candidate <= end:
            dates.append(candidate)
        month += 1                                          # GAP 2: inside the while loop
        if month == 13:
            month = 1
            year += 1
    return dates

def yearly_set_aside_cents(conn):
    rows = conn.execute(
        "SELECT amount_cents FROM bills WHERE frequency = 'yearly'"
    ).fetchall()
    return sum(-(-row["amount_cents"] // 12) for row in rows)

def list_payments(conn, cycle_id):
    return conn.execute(
        "SELECT p.bill_id, b.name, b.payee_email, b.frequency, p.amount_cents, "
        "p.status, p.attempts, p.batch_id, p.payout_id, p.due_date "
        "FROM payments p JOIN bills b ON b.id = p.bill_id "
        "WHERE p.cycle_id = ? ORDER BY p.due_date, p.id",
        (cycle_id,),
    ).fetchall()


def list_events(conn, cycle_id=None, limit=100):
    if cycle_id:
        return conn.execute(
            "SELECT * FROM events WHERE cycle_id = ? ORDER BY id DESC LIMIT ?",
            (cycle_id, limit),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()