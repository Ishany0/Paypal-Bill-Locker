import pytest

from api import create_app
from ledger import add_bill, connect, start_cycle


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    app = create_app(db_path)
    conn = connect(db_path)
    add_bill(conn, "Rent", 50000, "a@example.com", due_day=1)
    start_cycle(conn, "2026-11", 200000, "2026-11-01", "2026-11-30")
    conn.close()
    return app.test_client()


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_summary_endpoint(client):
    data = client.get("/api/cycles/2026-11/summary").get_json()
    assert data["locked_cents"] == 50000
    assert data["safe_to_spend_cents"] == 150000


def test_calendar_endpoint_has_dated_events(client):
    events = client.get("/api/cycles/2026-11/calendar").get_json()
    assert events[0]["name"] == "Rent"
    assert events[0]["startDate"] == "2026-11-01"


def test_unknown_cycle_returns_400(client):
    assert client.get("/api/cycles/nope/summary").status_code == 400