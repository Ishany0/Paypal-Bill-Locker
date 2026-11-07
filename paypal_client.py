"""Thin wrapper around the PayPal sandbox REST API."""
import time
import requests
from config import PAYPAL_BASE_URL, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET


class PayPalError(Exception):
    """Raised when PayPal rejects a request."""

    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        super().__init__(f"PayPal returned {status_code}: {body}")


_token = None
_token_expires_at = 0.0


def get_token():
    """Return a valid access token, fetching a new one only when needed."""
    global _token, _token_expires_at
    if _token and time.time() < _token_expires_at - 60:
        return _token
    response = requests.post(
        f"{PAYPAL_BASE_URL}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    if not response.ok:
        raise PayPalError(response.status_code, response.text)
    data = response.json()
    _token = data["access_token"]
    _token_expires_at = time.time() + data["expires_in"]
    return _token


def _headers(request_id=None):
    headers = {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
    }
    if request_id:
        headers["PayPal-Request-Id"] = request_id
    return headers


def format_amount(cents):
    """Turn 1050 into '10.50' without floating-point rounding."""
    return f"{cents // 100}.{cents % 100:02d}"


def create_payout(batch_id, receiver_email, amount_cents, currency="USD", note="Bill payment"):
    """Send one payment. batch_id must be unique for every payment."""
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")
    body = {
        "sender_batch_header": {
            "sender_batch_id": batch_id,
            "email_subject": "Bill payment",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {"value": format_amount(amount_cents), "currency": currency},
                "receiver": receiver_email,
                "note": note,
                "sender_item_id": batch_id,
            }
        ],
    }
    response = requests.post(
        f"{PAYPAL_BASE_URL}/v1/payments/payouts",
        json=body,
        headers=_headers(request_id=batch_id),
        timeout=30,
    )
    if not response.ok:
        raise PayPalError(response.status_code, response.text)
    return response.json()["batch_header"]["payout_batch_id"]


def get_payout_status(payout_batch_id):
    """Return the batch status, for example PENDING or SUCCESS."""
    response = requests.get(
        f"{PAYPAL_BASE_URL}/v1/payments/payouts/{payout_batch_id}",
        headers=_headers(),
        timeout=30,
    )
    if not response.ok:
        raise PayPalError(response.status_code, response.text)
    return response.json()["batch_header"]["batch_status"]