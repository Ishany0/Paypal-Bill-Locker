"""AI agents: each has ONE narrow job and only ADVISES.

Agents propose or explain. They never move money. Plain code (guardrail,
ledger, executor) decides and pays. Every answer is JSON that code validates.
Works with any OpenAI-compatible provider (Gemini, Groq, OpenRouter, Ollama).
"""
import json
import os
import re
from datetime import date

import openai
from dotenv import load_dotenv

from ledger import (dollars, get_cycle, list_events, list_payments, summary,
                    yearly_set_aside_cents)

load_dotenv()

MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
_client = None


class AgentError(Exception):
    """Raised when an agent cannot give a usable answer."""


def _get_client():
    global _client
    if _client is None:
        if not os.getenv("LLM_API_KEY"):
            raise AgentError("LLM_API_KEY is missing in the .env file")
        _client = openai.OpenAI(
            base_url=os.getenv("LLM_BASE_URL"),
            api_key=os.getenv("LLM_API_KEY"),
        )
    return _client


def parse_json(text):
    """Pull the first JSON object out of a model reply."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise AgentError("The agent did not return JSON")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise AgentError(f"The agent returned invalid JSON: {error}")


def ask(system, payload, max_tokens=700, client=None):
    """Send one request to the model and return its JSON answer as a dictionary."""
    client = client or _get_client()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            # Some free models spend part of the budget "thinking", so keep it generous.
            max_tokens=max(max_tokens, 1500),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload)},
            ],
        )
    except openai.OpenAIError as error:
        raise AgentError(f"AI provider error: {error}")
    return parse_json(response.choices[0].message.content or "")

def _need(answer, key, kind):
    value = answer.get(key)
    if not isinstance(value, kind):
        raise AgentError(f"The agent's answer is missing '{key}'")
    return value


# ---------------------------------------------------------------- Intake agent

INTAKE_SYSTEM = """You are the Intake agent of a bill-locker app.
Turn the user's sentence into ONE bill. Reply with a single JSON object and nothing else:
{"name": string, "amount": number (dollars), "frequency": "monthly" | "yearly" | "one_time",
 "due_day": integer 1-31 or null, "due_date": "YYYY-MM-DD" or null, "note": string}
Rules: monthly bills need due_day. Yearly and one_time bills need due_date.
The input gives today's date. If something is missing or unclear, use null and explain it
in "note". Never invent an amount."""


def validate_bill(raw, payee_email):
    """Plain-code check of the Intake agent's answer. Returns a clean proposal."""
    try:
        name = str(raw["name"]).strip()
        amount_cents = round(float(raw["amount"]) * 100)  # dollars to cents, at the gate
    except (KeyError, TypeError, ValueError):
        raise AgentError("Could not read the name or amount")
    if not name or amount_cents <= 0:
        raise AgentError("A bill needs a name and a positive amount")
    frequency = raw.get("frequency")
    if frequency not in ("monthly", "yearly", "one_time"):
        raise AgentError("Frequency must be monthly, yearly or one_time")
    due_day, due_date = raw.get("due_day"), raw.get("due_date")
    if frequency == "monthly":
        if not isinstance(due_day, int) or not 1 <= due_day <= 31:
            raise AgentError("A monthly bill needs a due day between 1 and 31")
        due_date = None
    else:
        try:
            due_date = date.fromisoformat(str(due_date)).isoformat()
        except ValueError:
            raise AgentError(f"A {frequency} bill needs a valid due date")
        due_day = 1
    return {
        "name": name, "amount_cents": amount_cents, "payee_email": payee_email,
        "frequency": frequency, "due_day": due_day, "due_date": due_date,
        "note": str(raw.get("note", "")),
    }


def intake_agent(text, payee_email, client=None):
    payload = {"today": date.today().isoformat(), "sentence": text}
    return validate_bill(ask(INTAKE_SYSTEM, payload, 400, client), payee_email)


# --------------------------------------------------------------- Planner agent

BRIEFING_SYSTEM = """You are the Planner agent of a bill-locker app.
You receive a cycle summary computed by the app. Use ONLY the numbers given and never change them.
Reply with a single JSON object and nothing else:
{"headline": string (max 15 words), "bullets": [string, string, string]}
The bullets cover: what is safe to spend, what is due next, and one risk or action."""


def briefing_agent(context, client=None):
    answer = ask(BRIEFING_SYSTEM, context, 500, client)
    return {
        "headline": _need(answer, "headline", str),
        "bullets": [str(b) for b in _need(answer, "bullets", list)][:4],
    }


# -------------------------------------------------------------- Reminder agent

REMINDER_SYSTEM = """You are the Reminder agent of a bill-locker app.
You receive today's date and the bills of the current cycle with due dates and statuses.
Write a friendly, calm reminder for each bill that still needs attention (LOCKED, FAILED or
RESERVED), soonest first. Skip bills that are PENDING or SUCCESS.
Reply with a single JSON object and nothing else:
{"reminders": [{"bill": string, "urgency": "low" | "medium" | "high", "message": string (max 25 words)}]}
Use only the data given."""


def reminder_agent(context, client=None):
    answer = ask(REMINDER_SYSTEM, context, 700, client)
    reminders = []
    for item in _need(answer, "reminders", list):
        if not isinstance(item, dict):
            continue
        urgency = item.get("urgency")
        reminders.append({
            "bill": str(item.get("bill", "")),
            "urgency": urgency if urgency in ("low", "medium", "high") else "medium",
            "message": str(item.get("message", "")),
        })
    return {"reminders": reminders}


# -------------------------------------------------------------- Reconcile agent

RECONCILE_SYSTEM = """You are the Reconcile agent of a bill-locker app.
You receive payment statuses and recent audit events. Explain in plain words what happened
and what a person should do next.
Statuses: LOCKED = money set aside, not yet paid. RESERVED = a payment was started and the
outcome is unclear, so a person must check PayPal before retrying. PENDING = PayPal accepted
it and is processing. SUCCESS = paid. FAILED = rejected, safe to retry.
Reply with a single JSON object and nothing else:
{"summary": string (max 30 words), "issues": [{"bill": string, "what_happened": string, "next_step": string}]}
Include only bills that need attention (RESERVED, FAILED, or waiting for approval according
to the events). Never suggest paying a RESERVED bill again without checking PayPal."""


def reconcile_agent(context, client=None):
    answer = ask(RECONCILE_SYSTEM, context, 800, client)
    issues = [
        {
            "bill": str(i.get("bill", "")),
            "what_happened": str(i.get("what_happened", "")),
            "next_step": str(i.get("next_step", "")),
        }
        for i in _need(answer, "issues", list)
        if isinstance(i, dict)
    ]
    return {"summary": _need(answer, "summary", str), "issues": issues}


# ------------------------------------------- building each agent's input (code)

def _payment_rows(conn, cycle_id):
    return [
        {"bill": r["name"], "amount": dollars(r["amount_cents"]),
         "due_date": r["due_date"], "status": r["status"], "attempts": r["attempts"]}
        for r in list_payments(conn, cycle_id)
    ]


def run_briefing(conn, cycle_id, client=None):
    data = summary(conn, cycle_id)
    context = {
        "today": date.today().isoformat(),
        "salary": dollars(data["salary_cents"]),
        "locked": dollars(data["locked_cents"]),
        "safe_to_spend": dollars(data["safe_to_spend_cents"]),
        "locker_balance": dollars(data["locker_balance_cents"]),
        "yearly_set_aside_per_month": dollars(yearly_set_aside_cents(conn)),
        "payments": _payment_rows(conn, cycle_id),
    }
    return briefing_agent(context, client)


def run_reminders(conn, cycle_id, client=None):
    get_cycle(conn, cycle_id)
    context = {"today": date.today().isoformat(), "bills": _payment_rows(conn, cycle_id)}
    return reminder_agent(context, client)


def run_reconcile(conn, cycle_id, client=None):
    get_cycle(conn, cycle_id)
    events = [{"kind": e["kind"], "note": e["note"]} for e in list_events(conn, cycle_id, 15)]
    context = {"payments": _payment_rows(conn, cycle_id), "recent_events": events}
    return reconcile_agent(context, client)