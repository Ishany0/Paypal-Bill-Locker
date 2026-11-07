import os
import time
from paypal_client import create_payout, get_payout_status, PayPalError

receiver = os.getenv("TEST_RECIPIENT_EMAIL")
if not receiver:
    raise SystemExit("Add TEST_RECIPIENT_EMAIL=... to your .env file")

batch_id = f"test-{int(time.time())}"

try:
    payout_id = create_payout(batch_id, receiver, amount_cents=1000, note="Day 2 test")
except PayPalError as error:
    print("PayPal refused the payout:", error)
    raise SystemExit(1)

print("Payout accepted. Batch ID:", payout_id)

for attempt in range(6):
    status = get_payout_status(payout_id)
    print("Status:", status)
    if status == "SUCCESS":
        break
    time.sleep(5)