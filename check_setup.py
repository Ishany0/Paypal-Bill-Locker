import requests
from config import PAYPAL_BASE_URL , PAYPAL_CLIENT_ID , PAYPAL_CLIENT_SECRET

response = requests.post(
    f"{PAYPAL_BASE_URL}/v1/oauth2/token",
    auth = (PAYPAL_CLIENT_ID , PAYPAL_CLIENT_SECRET),
    data = {"grant_type":"client_credentials"},
    timeout = 30,
)

print("Status:" , response.status_code)
if response.ok:
    token = response.json()["access_token"]
    print("Token length:" , len(token))
else:
    print("Error:", response.text)