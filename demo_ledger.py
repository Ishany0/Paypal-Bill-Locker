import os
from ledger import (LedgerError, add_bill, connect, dollars, init_db,
                    mark_payment, reserve_payment, start_cycle, summary)

if os.path.exists("demo.db"):
    os.remove("demo.db")

conn = connect("demo.db")
init_db(conn)

add_bill(conn, "Rent", 50000, "landlord@example.com")
add_bill(conn, "Phone", 10000, "telecom@example.com")
add_bill(conn, "Electricity", 7500, "power@example.com")

locked = start_cycle(conn, "2026-11", salary_cents=200000)
print("Locked:", dollars(locked))

s = summary(conn, "2026-11")
print("Safe to spend:", dollars(s["safe_to_spend_cents"]))
print("Locker balance:", dollars(s["locker_balance_cents"]))

ticket = reserve_payment(conn, "2026-11", 1)
print("Reserved:", ticket["bill_name"], dollars(ticket["amount_cents"]), ticket["batch_id"])
mark_payment(conn, "2026-11", 1, "SUCCESS", payout_id="DEMO123")

try:
    reserve_payment(conn, "2026-11", 1)
except LedgerError as error:
    print("Refused:", error)

s = summary(conn, "2026-11")
print("Locker balance now:", dollars(s["locker_balance_cents"]))
for p in s["payments"]:
    print(" ", p["name"], dollars(p["amount_cents"]), p["status"])