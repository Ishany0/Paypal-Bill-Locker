import pytest
from paypal_client import format_amount, create_payout


def test_whole_dollars():
    assert format_amount(1000) == "10.00"


def test_single_digit_cents():
    assert format_amount(5) == "0.05"


def test_large_amount():
    assert format_amount(123456) == "1234.56"


def test_rejects_zero_amount():
    with pytest.raises(ValueError):
        create_payout("x", "a@b.com", amount_cents=0)