#secrets are read from the .env file , never written here

#CENTRAL SETTINGS
import os
from dotenv import load_dotenv

load_dotenv()  #reads .env and turns each KEY=value line into an environment variable

PAYPAL_BASE_URL = "https://api-m.sandbox.paypal.com"
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")

if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
    raise RuntimeError("Missing Paypal client id or Paypal client secret in .env")