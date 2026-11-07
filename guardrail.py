"""Guardrail: plain-code safety checks that run before any money moves.

AI agents may PROPOSE a payment. Only this module decides whether it is
ALLOWED, needs a person's APPROVAL, or is REFUSED. Every decision is logged.
"""
import re
from dataclasses import dataclass

from ledger import dollars

ALLOWED = "ALLOWED"
NEEDS_APPROVAL = "NEEDS_APPROVAL"
REFUSED = "REFUSED"

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Limits:
    per_payment_cents: int = 200_000        # hard cap for one payment
    approval_threshold_cents: int = 50_000  # above this, a person must approve
    max_attempts: int = 3                   # failed payments are retried at most this often
    paused: bool = False                    # kill switch


DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str

    @property
    def allowed(self):
        return self.outcome == ALLOWED


def init_guardrail(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id TEXT NOT NULL,
            bill_id INTEGER NOT NULL,
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (cycle_id, bill_id)
        );
        """
    )
    conn.commit()


def approve_payment(conn, cycle_id, bill_id, approved_by="user"):
    """Record a person's approval. Only the user interface should call this."""
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO approvals (cycle_id, bill_id, approved_by) "
            "VALUES (?, ?, ?)",
            (cycle_id, bill_id, approved_by),
        )
        conn.execute(
            "INSERT INTO events (cycle_id, kind, note) VALUES (?, 'payment_approved', ?)",
            (cycle_id, f"bill {bill_id} by {approved_by}"),
        )


def _decide(conn, cycle_id, bill_id, limits):
    if limits.paused:
        return Decision(REFUSED, "Payments are paused (kill switch is on)")

    row = conn.execute(
        "SELECT p.status, p.attempts, p.amount_cents, b.payee_email, c.locked_cents "
        "FROM payments p "
        "JOIN bills b ON b.id = p.bill_id "
        "JOIN cycles c ON c.cycle_id = p.cycle_id "
        "WHERE p.cycle_id = ? AND p.bill_id = ?",
        (cycle_id, bill_id),
    ).fetchone()

    if row is None:
        return Decision(REFUSED, f"Bill {bill_id} is not locked for cycle {cycle_id}")
    if row["status"] not in ("LOCKED", "FAILED"):
        return Decision(REFUSED, f"Bill {bill_id} is already {row['status']}")
    if row["status"] == "FAILED" and row["attempts"] >= limits.max_attempts:
        return Decision(
            REFUSED,
            f"Bill {bill_id} failed {row['attempts']} times; a person must look at it",
        )
    if not EMAIL_PATTERN.match(row["payee_email"]):
        return Decision(REFUSED, f"Payee email for bill {bill_id} is not valid")

    amount = row["amount_cents"]
    if amount > limits.per_payment_cents:
        return Decision(
            REFUSED,
            f"{dollars(amount)} is above the per-payment limit of "
            f"{dollars(limits.per_payment_cents)}",
        )

    already_out = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM payments "
        "WHERE cycle_id = ? AND status IN ('RESERVED', 'PENDING', 'SUCCESS')",
        (cycle_id,),
    ).fetchone()["total"]
    if already_out + amount > row["locked_cents"]:
        return Decision(REFUSED, "Paying this would exceed the money locked for the cycle")

    if amount > limits.approval_threshold_cents:
        approved = conn.execute(
            "SELECT 1 FROM approvals WHERE cycle_id = ? AND bill_id = ?",
            (cycle_id, bill_id),
        ).fetchone()
        if approved is None:
            return Decision(NEEDS_APPROVAL, "Large payment: waiting for the user to approve")

    return Decision(ALLOWED, "All checks passed")


def check_payment(conn, cycle_id, bill_id, limits=DEFAULT_LIMITS):
    """Decide about one payment and write the decision to the audit log."""
    decision = _decide(conn, cycle_id, bill_id, limits)
    with conn:
        conn.execute(
            "INSERT INTO events (cycle_id, kind, note) VALUES (?, ?, ?)",
            (cycle_id, f"guardrail_{decision.outcome.lower()}",
             f"bill {bill_id}: {decision.reason}"),
        )
    return decision