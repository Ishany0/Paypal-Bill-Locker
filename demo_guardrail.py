import os
from guardrail import Limits, approve_payment, check_payment, init_guardrail
from ledger import add_bill, connect, init_db, start_cycle

if os.path.exists("demo.db"):
    os.remove("demo.db")

conn = connect("demo.db")
init_db(conn)
init_guardrail(conn)

add_bill(conn, "Rent", 50000, "landlord@example.com")
add_bill(conn, "Phone", 10000, "telecom@example.com")
start_cycle(conn, "2026-11", salary_cents=200000)

limits = Limits(approval_threshold_cents=40_000)

for bill_id in (1, 2):
    d = check_payment(conn, "2026-11", bill_id, limits)
    print(f"Bill {bill_id}: {d.outcome} - {d.reason}")

approve_payment(conn, "2026-11", 1)
d = check_payment(conn, "2026-11", 1, limits)
print(f"After approval, bill 1: {d.outcome} - {d.reason}")

d = check_payment(conn, "2026-11", 2, Limits(paused=True))
print(f"Paused: {d.outcome} - {d.reason}")

count = conn.execute("SELECT COUNT(*) FROM events WHERE kind LIKE 'guardrail%'").fetchone()[0]
print("Guardrail log entries:", count)