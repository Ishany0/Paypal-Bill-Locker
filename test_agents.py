import pytest

import agents
from agents import AgentError, briefing_agent, intake_agent, parse_json, reconcile_agent, reminder_agent, validate_bill


class FakeClient:
    """Stands in for the AI client: returns a fixed text answer."""

    def __init__(self, text):
        self.chat = self
        self.completions = self
        self.text = text

    def create(self, **kwargs):
        message = type("Message", (), {"content": self.text})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


GOOD = {"name": "Netflix", "amount": 15.99, "frequency": "monthly",
        "due_day": 12, "due_date": None, "note": ""}


def test_parse_json_finds_the_object_inside_text():
    assert parse_json('Sure! {"a": 1} Hope that helps') == {"a": 1}


def test_parse_json_without_json_raises():
    with pytest.raises(AgentError):
        parse_json("no braces here")


def test_valid_monthly_bill_is_converted_to_cents():
    bill = validate_bill(GOOD, "x@example.com")
    assert bill["amount_cents"] == 1599
    assert bill["due_day"] == 12
    assert bill["payee_email"] == "x@example.com"


def test_yearly_bill_without_a_date_is_rejected():
    with pytest.raises(AgentError):
        validate_bill({**GOOD, "frequency": "yearly"}, "x@example.com")


def test_zero_or_negative_amount_is_rejected():
    with pytest.raises(AgentError):
        validate_bill({**GOOD, "amount": -5}, "x@example.com")


def test_unknown_frequency_is_rejected():
    with pytest.raises(AgentError):
        validate_bill({**GOOD, "frequency": "weekly"}, "x@example.com")


def test_intake_agent_returns_a_validated_proposal():
    fake = FakeClient('{"name": "Gym", "amount": 20, "frequency": "yearly", '
                      '"due_day": null, "due_date": "2026-12-01", "note": ""}')
    bill = intake_agent("Gym 20 dollars on 1 December", "x@example.com", client=fake)
    assert bill["frequency"] == "yearly" and bill["due_date"] == "2026-12-01"


def test_agents_cannot_pay_anything():
    assert not hasattr(agents, "pay_bill") and not hasattr(agents, "executor")

def test_briefing_agent_returns_headline_and_bullets():
    fake = FakeClient('{"headline": "All good", "bullets": ["a", "b", "c"]}')
    result = briefing_agent({"x": 1}, client=fake)
    assert result["headline"] == "All good" and len(result["bullets"]) == 3


def test_reminder_agent_replaces_an_unknown_urgency():
    fake = FakeClient('{"reminders": [{"bill": "Rent", "urgency": "urgent!!", "message": "Pay soon"}]}')
    assert reminder_agent({}, client=fake)["reminders"][0]["urgency"] == "medium"


def test_reconcile_agent_returns_summary_and_issues():
    fake = FakeClient('{"summary": "One issue", "issues": [{"bill": "Phone", "what_happened": "x", "next_step": "y"}]}')
    assert reconcile_agent({}, client=fake)["issues"][0]["bill"] == "Phone"


def test_agent_answer_missing_a_field_is_rejected():
    with pytest.raises(AgentError):
        briefing_agent({}, client=FakeClient('{"headline": "x"}'))