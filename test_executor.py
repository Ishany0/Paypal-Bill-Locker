import pytest
import requests

from executor import (REJECTED, SENT, UNKNOWN, pay_cycle, refresh_statuses)
from guardrail import (NEEDS_APPROVAL, REFUSED, Limits, approve_payment,
                       init_guardrail)
from ledger import (add_bill, connect, init_db, locker_balance,
                    payments_with_status, start_cycle)
from paypal_client import PayPalError

CYCLE = "2026-11"
LIMITS = Limits(approval_threshold_cents=100_000)


class FakePayPal:
    """Stands in for paypal_client: records calls, can simulate failures."""

    def __init__(self):
        self.calls = []
        self.fail_with = None
        self.statuses = {}

    def create_payout(self, batch_id, receiver_email, amount_cents,
                      currency="USD", note="Bill payment"):
        if self.fail_with:
            raise self.fail_with
        self.calls.append((batch_id, receiver_email, amount_cents))
        return f"PAYOUT-{len(self.calls)}"

    def get_payout_status(self, payout_id):
        return self.statuses.get(payout_id, "PENDING")


@pytest.fixture
def conn():
    db = connect(":memory:")
    init_db(db)
    init_guardrail(db)
    add_bill(db, "Rent", 50000, "a@example.com")   # bill 1
    add_bill(db, "Phone", 10000, "b@example.com")  # bill 2
    start_cycle(db, CYCLE, 200000)
    yield db
    db.close()


@pytest.fixture
def paypal():
    return FakePayPal()


def outcomes(results):
    return {r.bill_id: r.outcome for r in results}


def test_each_bill_is_sent_exactly_once(conn, paypal):
    assert outcomes(pay_cycle(conn, CYCLE, LIMITS, paypal)) == {1: SENT, 2: SENT}
    assert len(paypal.calls) == 2
    assert pay_cycle(conn, CYCLE, LIMITS, paypal) == []
    assert len(paypal.calls) == 2


def test_large_payment_waits_for_approval(conn, paypal):
    limits = Limits(approval_threshold_cents=40_000)
    assert outcomes(pay_cycle(conn, CYCLE, limits, paypal)) == {1: NEEDS_APPROVAL, 2: SENT}
    assert len(paypal.calls) == 1
    approve_payment(conn, CYCLE, 1)
    assert outcomes(pay_cycle(conn, CYCLE, limits, paypal)) == {1: SENT}
    assert len(paypal.calls) == 2


def test_rejected_payment_can_be_retried_with_new_batch_id(conn, paypal):
    paypal.fail_with = PayPalError(400, "bad request")
    assert outcomes(pay_cycle(conn, CYCLE, LIMITS, paypal)) == {1: REJECTED, 2: REJECTED}
    assert locker_balance(conn, CYCLE) == 60000
    paypal.fail_with = None
    assert outcomes(pay_cycle(conn, CYCLE, LIMITS, paypal)) == {1: SENT, 2: SENT}
    assert all(call[0].endswith("-a2") for call in paypal.calls)


def test_timeout_leaves_payment_reserved_and_is_never_retried(conn, paypal):
    paypal.fail_with = requests.exceptions.Timeout()
    assert outcomes(pay_cycle(conn, CYCLE, LIMITS, paypal)) == {1: UNKNOWN, 2: UNKNOWN}
    assert len(payments_with_status(conn, CYCLE, "RESERVED")) == 2
    paypal.fail_with = None
    assert pay_cycle(conn, CYCLE, LIMITS, paypal) == []
    assert paypal.calls == []


def test_server_error_is_treated_as_unknown(conn, paypal):
    paypal.fail_with = PayPalError(500, "server error")
    assert outcomes(pay_cycle(conn, CYCLE, LIMITS, paypal)) == {1: UNKNOWN, 2: UNKNOWN}


def test_refresh_marks_success(conn, paypal):
    pay_cycle(conn, CYCLE, LIMITS, paypal)
    paypal.statuses = {"PAYOUT-1": "SUCCESS", "PAYOUT-2": "SUCCESS"}
    changed = refresh_statuses(conn, CYCLE, paypal)
    assert sorted(changed) == [(1, "SUCCESS"), (2, "SUCCESS")]
    assert payments_with_status(conn, CYCLE, "PENDING") == []


def test_denied_payout_becomes_failed_and_can_be_retried(conn, paypal):
    pay_cycle(conn, CYCLE, LIMITS, paypal)
    paypal.statuses = {"PAYOUT-1": "DENIED"}
    assert refresh_statuses(conn, CYCLE, paypal) == [(1, "FAILED")]
    assert outcomes(pay_cycle(conn, CYCLE, LIMITS, paypal)) == {1: SENT}
    assert paypal.calls[-1][0].endswith("-a2")


def test_kill_switch_makes_no_paypal_calls(conn, paypal):
    results = pay_cycle(conn, CYCLE, Limits(paused=True), paypal)
    assert outcomes(results) == {1: REFUSED, 2: REFUSED}
    assert paypal.calls == []