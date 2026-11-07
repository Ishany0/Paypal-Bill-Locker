import pytest
from ledger import (LedgerError, add_bill, connect, init_db, locker_balance,
                    mark_payment, reserve_payment, safe_to_spend, start_cycle)

CYCLE = "2026-11"


@pytest.fixture
def conn():
    db = connect(":memory:")
    init_db(db)
    add_bill(db, "Rent", 50000, "a@example.com")   # bill id 1
    add_bill(db, "Phone", 10000, "b@example.com")  # bill id 2
    yield db
    db.close()


def test_start_cycle_locks_bills(conn):
    assert start_cycle(conn, CYCLE, 200000) == 60000
    assert safe_to_spend(conn, CYCLE) == 140000
    assert locker_balance(conn, CYCLE) == 60000


def test_shortfall_is_refused(conn):
    with pytest.raises(LedgerError):
        start_cycle(conn, CYCLE, 50000)


def test_cycle_cannot_start_twice(conn):
    start_cycle(conn, CYCLE, 200000)
    with pytest.raises(LedgerError):
        start_cycle(conn, CYCLE, 200000)


def test_paying_reduces_locker(conn):
    start_cycle(conn, CYCLE, 200000)
    reserve_payment(conn, CYCLE, 2)
    assert locker_balance(conn, CYCLE) == 50000


def test_same_bill_cannot_be_paid_twice(conn):
    start_cycle(conn, CYCLE, 200000)
    reserve_payment(conn, CYCLE, 1)
    with pytest.raises(LedgerError):
        reserve_payment(conn, CYCLE, 1)


def test_bill_added_after_locking_cannot_be_paid(conn):
    start_cycle(conn, CYCLE, 200000)
    late_id = add_bill(conn, "Gym", 3000, "c@example.com")
    with pytest.raises(LedgerError):
        reserve_payment(conn, CYCLE, late_id)


def test_failed_payment_can_retry_with_new_batch_id(conn):
    start_cycle(conn, CYCLE, 200000)
    first = reserve_payment(conn, CYCLE, 1)
    mark_payment(conn, CYCLE, 1, "FAILED")
    assert locker_balance(conn, CYCLE) == 60000
    second = reserve_payment(conn, CYCLE, 1)
    assert first["batch_id"].endswith("-a1")
    assert second["batch_id"].endswith("-a2")