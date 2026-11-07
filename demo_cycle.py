import os
import time

import paypal_client  # loads .env as a side effect
from executor import pay_cycle, refresh_statuses
from guardrail import NEEDS_APPROVAL, Limits, approve_payment, init_guardrail
from ledger import (LedgerError, add_bill, connect, dollars, init_db,
                    list_bills, payments_with_status, start_cycle, summary)

CYCLE = "demo-1"  # change to demo-2, demo-3... if you delete cycle_demo.db
RECEIVER = os.getenv("TEST_RECIPIENT_EMAIL")
if not RECEIVER:
    raise SystemExit("Add TEST_RECIPIENT_EMAIL=... to your .env file")

conn = connect("cycle_demo.db")
init_db(conn)
init_guardrail(conn)

if not list_bills(conn):
    add_bill(conn, "Rent", 2000, RECEIVER)
    add_bill(conn, "Phone", 500, RECEIVER)
    add_bill(conn, "Electricity", 350, RECEIVER)

try:
    locked = start_cycle(conn, CYCLE, salary_cents=10000)
    print("Salary arrived. Locked:", dollars(locked))
except LedgerError as error:
    print("Skipped locking:", error)

limits = Limits(approval_threshold_cents=1000)


def show(results):
    for r in results:
        print(f"  bill {r.bill_id}: {r.outcome} - {r.detail}")


print("Paying bills...")
results = pay_cycle(conn, CYCLE, limits)
show(results)
if not results:
    print("  Nothing left to pay")

waiting = [r.bill_id for r in results if r.outcome == NEEDS_APPROVAL]
for bill_id in waiting:
    print(f"Approving bill {bill_id} (the user would click Approve here)")
    approve_payment(conn, CYCLE, bill_id)
if waiting:
    show(pay_cycle(conn, CYCLE, limits))

print("Checking PayPal...")
for attempt in range(6):
    refresh_statuses(conn, CYCLE)
    if not payments_with_status(conn, CYCLE, "PENDING"):
        break
    time.sleep(5)

s = summary(conn, CYCLE)
print("Safe to spend:", dollars(s["safe_to_spend_cents"]))
print("Locker balance:", dollars(s["locker_balance_cents"]))
for p in s["payments"]:
    print(" ", p["name"], dollars(p["amount_cents"]), p["status"])
print("Stuck payments:", len(payments_with_status(conn, CYCLE, "RESERVED")))