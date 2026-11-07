import pytest
from guardrail import (ALLOWED, NEEDS_APPROVAL, REFUSED, Limits,
                       approve_payment, check_payment, init_guardrail)
from ledger import (add_bill, connect, init_db, mark_payment,
                    reserve_payment, start_cycle)

CYCLE = "2026-11"
LIMITS = Limits(per_payment_cents=100_000, approval_threshold_cents=40_000, max_attempts=2)


@pytest.fixture
def conn():
    db = connect(":memory:")
    init_db(db)
    init_guardrail(db)
    add_bill(db, "Rent", 50000, "a@example.com")   # bill 1: above the approval threshold
    add_bill(db, "Phone", 10000, "b@example.com")  # bill 2: small
    start_cycle(db, CYCLE, 200000)
    yield db
    db.close()


def test_small_bill_is_allowed(conn):
    assert check_payment(conn, CYCLE, 2, LIMITS).outcome == ALLOWED


def test_large_bill_needs_approval_then_is_allowed(conn):
    assert check_payment(conn, CYCLE, 1, LIMITS).outcome == NEEDS_APPROVAL
    approve_payment(conn, CYCLE, 1)
    assert check_payment(conn, CYCLE, 1, LIMITS).outcome == ALLOWED


def test_amount_over_cap_is_refused(conn):
    tight = Limits(per_payment_cents=30_000, approval_threshold_cents=20_000)
    decision = check_payment(conn, CYCLE, 1, tight)
    assert decision.outcome == REFUSED
    assert "limit" in decision.reason


def test_already_reserved_bill_is_refused(conn):
    reserve_payment(conn, CYCLE, 2)
    decision = check_payment(conn, CYCLE, 2, LIMITS)
    assert decision.outcome == REFUSED
    assert "already" in decision.reason


def test_bill_that_was_never_locked_is_refused(conn):
    late_id = add_bill(conn, "Gym", 3000, "c@example.com")
    decision = check_payment(conn, CYCLE, late_id, LIMITS)
    assert decision.outcome == REFUSED
    assert "not locked" in decision.reason


def test_kill_switch_refuses_everything(conn):
    decision = check_payment(conn, CYCLE, 2, Limits(paused=True))
    assert decision.outcome == REFUSED
    assert "paused" in decision.reason


def test_too_many_failures_need_a_person(conn):
    reserve_payment(conn, CYCLE, 2)
    mark_payment(conn, CYCLE, 2, "FAILED")
    assert check_payment(conn, CYCLE, 2, LIMITS).outcome == ALLOWED  # one retry is fine
    reserve_payment(conn, CYCLE, 2)
    mark_payment(conn, CYCLE, 2, "FAILED")
    decision = check_payment(conn, CYCLE, 2, LIMITS)
    assert decision.outcome == REFUSED
    assert "failed" in decision.reason


def test_invalid_payee_email_is_refused(conn):
    bad_id = add_bill(conn, "Mystery", 2000, "not-an-email")
    start_cycle(conn, "2026-12", 500000)
    decision = check_payment(conn, "2026-12", bad_id, LIMITS)
    assert decision.outcome == REFUSED
    assert "not valid" in decision.reason


def test_cannot_pay_more_than_was_locked(conn):
    conn.execute("UPDATE cycles SET locked_cents = 1000 WHERE cycle_id = ?", (CYCLE,))
    conn.commit()
    decision = check_payment(conn, CYCLE, 1, LIMITS)
    assert decision.outcome == REFUSED
    assert "exceed" in decision.reason


def test_decisions_are_written_to_the_audit_log(conn):
    check_payment(conn, CYCLE, 2, LIMITS)
    count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE kind LIKE 'guardrail%'"
    ).fetchone()[0]
    assert count == 1