"""Payout executor: the only place where guardrail, ledger and PayPal meet.

Order of operations for every payment (never change it):
  1. guardrail decides     2. ledger reserves (claim first)
  3. PayPal sends          4. ledger records the answer
"""
from dataclasses import dataclass

import requests

import paypal_client
from guardrail import DEFAULT_LIMITS, REFUSED, check_payment
from ledger import LedgerError, mark_payment, payments_with_status, reserve_payment

SENT = "SENT"          # PayPal accepted the payout (status now PENDING)
REJECTED = "REJECTED"  # PayPal clearly said no; safe to retry later
UNKNOWN = "UNKNOWN"    # no clear answer; a person must check PayPal


@dataclass(frozen=True)
class PaymentResult:
    bill_id: int
    outcome: str
    detail: str


def _note(conn, cycle_id, kind, text):
    with conn:
        conn.execute(
            "INSERT INTO events (cycle_id, kind, note) VALUES (?, ?, ?)",
            (cycle_id, kind, text),
        )


def pay_bill(conn, cycle_id, bill_id, limits=DEFAULT_LIMITS, paypal=paypal_client):
    decision = check_payment(conn, cycle_id, bill_id, limits)
    if not decision.allowed:
        return PaymentResult(bill_id, decision.outcome, decision.reason)

    try:
        ticket = reserve_payment(conn, cycle_id, bill_id)
    except LedgerError as error:
        return PaymentResult(bill_id, REFUSED, str(error))

    try:
        payout_id = paypal.create_payout(
            ticket["batch_id"],
            ticket["payee_email"],
            ticket["amount_cents"],
            note=ticket["bill_name"],
        )
    except paypal_client.PayPalError as error:
        if 400 <= error.status_code < 500:
            mark_payment(conn, cycle_id, bill_id, "FAILED")
            return PaymentResult(bill_id, REJECTED, f"PayPal said no ({error.status_code})")
        _note(conn, cycle_id, "payment_unknown", f"bill {bill_id}: PayPal error {error.status_code}")
        return PaymentResult(
            bill_id, UNKNOWN, f"PayPal error {error.status_code}: check PayPal before retrying"
        )
    except requests.RequestException as error:
        _note(conn, cycle_id, "payment_unknown", f"bill {bill_id}: {type(error).__name__}")
        return PaymentResult(
            bill_id,
            UNKNOWN,
            f"No clear answer from PayPal ({type(error).__name__}): check PayPal before retrying",
        )

    mark_payment(conn, cycle_id, bill_id, "PENDING", payout_id=payout_id)
    return PaymentResult(bill_id, SENT, f"Payout {payout_id} accepted")


def pay_cycle(conn, cycle_id, limits=DEFAULT_LIMITS, paypal=paypal_client):
    """Try to pay every bill that is still waiting. Safe to call repeatedly."""
    results = []
    for row in payments_with_status(conn, cycle_id, "LOCKED", "FAILED"):
        results.append(pay_bill(conn, cycle_id, row["bill_id"], limits, paypal))
    return results


def refresh_statuses(conn, cycle_id, paypal=paypal_client):
    """Ask PayPal about every PENDING payment and record the outcome."""
    changed = []
    for row in payments_with_status(conn, cycle_id, "PENDING"):
        status = paypal.get_payout_status(row["payout_id"])
        if status == "SUCCESS":
            mark_payment(conn, cycle_id, row["bill_id"], "SUCCESS")
            changed.append((row["bill_id"], "SUCCESS"))
        elif status in ("DENIED", "CANCELED"):
            mark_payment(conn, cycle_id, row["bill_id"], "FAILED")
            changed.append((row["bill_id"], "FAILED"))
    return changed