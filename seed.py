"""Create demo data: a few bills and a started cycle. Sandbox demo only."""
import os
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

from guardrail import init_guardrail
from ledger import add_bill, connect, dollars, init_db, start_cycle

load_dotenv()
DB = os.getenv("LEDGER_DB", "locker.db")
RECIPIENT = os.getenv("TEST_RECIPIENT_EMAIL")
if not RECIPIENT:
    raise SystemExit("Add TEST_RECIPIENT_EMAIL=... to your .env file")

if os.path.exists(DB):
    os.remove(DB)
conn = connect(DB)
init_db(conn)
init_guardrail(conn)

today = date.today()


def day_in(n):
    return (today + timedelta(days=n)).day


add_bill(conn, "Rent", 2000, RECIPIENT, due_day=day_in(3))
add_bill(conn, "Phone", 500, RECIPIENT, due_day=day_in(8))
add_bill(conn, "Electricity", 350, RECIPIENT, due_day=day_in(14))
add_bill(conn, "Streaming", 150, RECIPIENT, due_day=day_in(20))
add_bill(conn, "Insurance", 1200, RECIPIENT, frequency="yearly",
         due_date=(today + timedelta(days=10)).isoformat())
add_bill(conn, "Gym pass", 800, RECIPIENT, frequency="one_time",
         due_date=(today + timedelta(days=45)).isoformat())

cycle_id = datetime.now().strftime("%Y%m%d-%H%M")
locked = start_cycle(conn, cycle_id, 10000, today.isoformat(),
                     (today + timedelta(days=29)).isoformat())
print("Cycle:", cycle_id)
print("Locked:", dollars(locked), "of", dollars(10000))