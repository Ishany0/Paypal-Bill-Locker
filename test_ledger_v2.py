from datetime import date
import pytest
from ledger import (LedgerError, add_bill, connect, due_dates_in_window, init_db,
                    start_cycle, summary, yearly_set_aside_cents)


def d(text):
    return date.fromisoformat(text)


def test_monthly_inside_one_month():
    assert due_dates_in_window("monthly", 15, None, d("2026-11-01"), d("2026-11-30")) == [d("2026-11-15")]


def test_monthly_day_31_uses_last_day_of_short_month():
    assert due_dates_in_window("monthly", 31, None, d("2027-02-01"), d("2027-02-28")) == [d("2027-02-28")]


def test_window_crossing_a_month_boundary():
    start, end = d("2026-11-25"), d("2026-12-24")
    assert due_dates_in_window("monthly", 28, None, start, end) == [d("2026-11-28")]
    assert due_dates_in_window("monthly", 5, None, start, end) == [d("2026-12-05")]


def test_window_edges_are_inclusive():
    start, end = d("2026-11-25"), d("2026-12-24")
    assert due_dates_in_window("monthly", 25, None, start, end) == [d("2026-11-25")]
    assert due_dates_in_window("monthly", 24, None, start, end) == [d("2026-12-24")]


def test_one_time_and_yearly_use_their_date():
    start, end = d("2026-11-01"), d("2026-11-30")
    assert due_dates_in_window("one_time", None, "2026-11-20", start, end) == [d("2026-11-20")]
    assert due_dates_in_window("yearly", None, "2026-12-15", start, end) == []


@pytest.fixture
def conn():
    db = connect(":memory:")
    init_db(db)
    add_bill(db, "Rent", 50000, "a@example.com", due_day=1)
    add_bill(db, "Phone", 10000, "b@example.com", due_day=15)
    add_bill(db, "Insurance", 30000, "c@example.com", frequency="yearly", due_date="2026-11-20")
    add_bill(db, "Gym", 5000, "d@example.com", frequency="one_time", due_date="2026-12-10")
    yield db
    db.close()


def test_only_bills_due_in_the_window_are_locked(conn):
    assert start_cycle(conn, "2026-11", 200000, "2026-11-01", "2026-11-30") == 90000
    names = [p["name"] for p in summary(conn, "2026-11")["payments"]]
    assert names == ["Rent", "Phone", "Insurance"]


def test_payments_remember_their_due_date(conn):
    start_cycle(conn, "2026-11", 200000, "2026-11-01", "2026-11-30")
    dates = {p["name"]: p["due_date"] for p in summary(conn, "2026-11")["payments"]}
    assert dates["Phone"] == "2026-11-15"
    assert dates["Insurance"] == "2026-11-20"


def test_shortfall_inside_the_window_is_refused(conn):
    with pytest.raises(LedgerError):
        start_cycle(conn, "2026-11", 50000, "2026-11-01", "2026-11-30")


def test_window_longer_than_31_days_is_refused(conn):
    with pytest.raises(LedgerError):
        start_cycle(conn, "2026-11", 500000, "2026-11-01", "2026-12-31")


def test_yearly_bill_needs_a_date(conn):
    with pytest.raises(ValueError):
        add_bill(conn, "Oops", 1000, "e@example.com", frequency="yearly")


def test_yearly_set_aside_is_one_twelfth_rounded_up(conn):
    assert yearly_set_aside_cents(conn) == 2500
    add_bill(conn, "Domain", 1001, "f@example.com", frequency="yearly", due_date="2027-01-05")
    assert yearly_set_aside_cents(conn) == 2500 + 84