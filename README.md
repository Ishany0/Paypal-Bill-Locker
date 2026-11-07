# Bill Locker

Pay your bills first. Bill Locker locks the month's bills the moment your salary
arrives, pays each one automatically from the locker through PayPal, and shows
you one number: what is safe to spend.

Built for the PayPal AI Hackathon 2026. Sandbox only: no real money is used.

## The problem

People underestimate their subscriptions, forget yearly bills, and get hit by
bills that land before payday. Bill Locker removes all three by setting bill
money aside before anything can be spent.

## How it works

1. Bills are stored in a local database.
2. When salary arrives, every monthly bill is locked in one step.
3. Safe to spend = salary minus locked bills.
4. Each payment goes through four steps in a fixed order:
   guardrail check, ledger reservation, PayPal payout, ledger record.

## Design rule: AI proposes, plain code moves money

AI agents will suggest and explain. Plain, tested code decides and pays.

| Component | Status |
|---|---|
| PayPal client (token, payout, status) | Done |
| Locker ledger (SQLite) | Done |
| Guardrail (caps, approvals, kill switch, audit log) | Done |
| Payout executor | Done |
| Intake agent (text or photo to bill) | In progress |
| Forecast agent (variable bills) | Planned |
| Planner, Reminder and Reconcile agents | Planned |
| Web dashboard | Planned |

## Safety features

- One payment per bill per cycle, enforced by the database
- The payment is reserved before PayPal is called
- Unclear failures (timeouts, server errors) are never retried automatically
- Per-payment cap, approval threshold and a kill switch
- Every decision is written to an audit log
- Money is stored as whole cents, never as decimals
- Secrets live in `.env`, which is never committed

## Setup (Windows PowerShell)

```
git clone https://github.com/YOUR_USERNAME/paypal-bill-locker.git
cd paypal-bill-locker
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your PayPal sandbox values. The
sandbox business account that owns your app must be in a country where PayPal
Payouts is available (we used the United States).

## Run

```
python check_setup.py      # confirms your keys work
python demo_ledger.py      # locking and paying, no network
python demo_guardrail.py   # the guardrail decisions
python demo_cycle.py       # a full cycle against the PayPal sandbox
pytest -q                  # all tests
```

## Project layout

| File | Purpose |
|---|---|
| `config.py` | Settings and keys from `.env` |
| `paypal_client.py` | The only code that talks to PayPal |
| `ledger.py` | Bills, locked money and payments in SQLite |
| `guardrail.py` | Safety checks before any money moves |
| `executor.py` | Runs the four-step payment order |
| `test_*.py` | Automated tests |

## License

MIT