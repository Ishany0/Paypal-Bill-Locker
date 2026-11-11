"""Flask API: exposes the ledger, guardrail and executor as JSON."""
import os
from dataclasses import asdict
import agents
import sqlite3

from flask import Flask, g, jsonify, request
from flask_cors import CORS

import executor
from guardrail import Limits, approve_payment, init_guardrail
from ledger import (LedgerError, add_bill, connect, init_db, list_bills,
                    list_events, list_payments, start_cycle, summary,
                    yearly_set_aside_cents)


def create_app(db_path=None):
    app = Flask(__name__)
    CORS(app, origins=["http://localhost:3000"])
    path = db_path or os.getenv("LEDGER_DB", "locker.db")
    limits = Limits(
        approval_threshold_cents=int(os.getenv("APPROVAL_THRESHOLD_CENTS", "50000"))
    )

    setup = connect(path)
    init_db(setup)
    init_guardrail(setup)
    setup.close()

    def get_db():
        if "db" not in g:
            g.db = connect(path)
        return g.db

    @app.teardown_appcontext
    def close_db(_error):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.errorhandler(LedgerError)
    @app.errorhandler(ValueError)
    def bad_request(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(sqlite3.IntegrityError)
    def rejected_by_database(error):
        return jsonify(error=f"The database rejected this: {error}"), 400

    @app.errorhandler(KeyError)
    def missing_field(error):
        return jsonify(error=f"Missing field: {error}"), 400

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.get("/")
    def index():
        return jsonify(
            name="Bill Locker API",
            health="/api/health",
            dashboard="Open http://localhost:3000/locker",
        )

    @app.get("/api/bills")
    def bills():
        return jsonify([dict(b) for b in list_bills(get_db())])

    @app.post("/api/bills")
    def create_bill():
        data = request.get_json(force=True)
        bill_id = add_bill(
            get_db(), data["name"], int(data["amount_cents"]), data["payee_email"],
            data.get("frequency", "monthly"), int(data.get("due_day", 1)),
            data.get("due_date"),
        )
        return jsonify(id=bill_id), 201

    @app.get("/api/cycles")
    def cycles():
        rows = get_db().execute("SELECT * FROM cycles ORDER BY rowid DESC").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/cycles")
    def begin_cycle():
        data = request.get_json(force=True)
        total = start_cycle(
            get_db(), data["cycle_id"], int(data["salary_cents"]),
            data.get("start_date"), data.get("end_date"),
        )
        return jsonify(locked_cents=total), 201

    @app.get("/api/cycles/<cycle_id>/summary")
    def cycle_summary(cycle_id):
        conn = get_db()
        data = summary(conn, cycle_id)
        data["yearly_set_aside_cents"] = yearly_set_aside_cents(conn)
        return jsonify(data)

    @app.get("/api/cycles/<cycle_id>/payments")
    def payments(cycle_id):
        return jsonify([dict(r) for r in list_payments(get_db(), cycle_id)])

    @app.get("/api/cycles/<cycle_id>/calendar")
    def calendar_events(cycle_id):
        return jsonify([
            {
                "id": r["bill_id"], "name": r["name"],
                "startDate": r["due_date"], "endDate": r["due_date"],
                "allDay": True, "status": r["status"], "amountCents": r["amount_cents"],
            }
            for r in list_payments(get_db(), cycle_id) if r["due_date"]
        ])

    @app.get("/api/events")
    def events():
        rows = list_events(get_db(), request.args.get("cycle_id"))
        return jsonify([dict(r) for r in rows])

    @app.post("/api/cycles/<cycle_id>/payments/<int:bill_id>/pay")
    def pay(cycle_id, bill_id):
        result = executor.pay_bill(get_db(), cycle_id, bill_id, limits)
        return jsonify(asdict(result))

    @app.post("/api/cycles/<cycle_id>/payments/<int:bill_id>/approve")
    def approve(cycle_id, bill_id):
        approve_payment(get_db(), cycle_id, bill_id, approved_by="user")
        return jsonify(status="approved")

    @app.post("/api/cycles/<cycle_id>/pay-all")
    def pay_all(cycle_id):
        results = executor.pay_cycle(get_db(), cycle_id, limits)
        return jsonify([asdict(r) for r in results])

    @app.post("/api/cycles/<cycle_id>/refresh")
    def refresh(cycle_id):
        changed = executor.refresh_statuses(get_db(), cycle_id)
        return jsonify([{"bill_id": b, "status": s} for b, s in changed])

    @app.errorhandler(agents.AgentError)
    def agent_failed(error):
        return jsonify(error=str(error)), 503

    @app.post("/api/agents/intake")
    def agent_intake():
        text = (request.get_json(force=True).get("text") or "").strip()
        if not text:
            raise ValueError("Type a sentence describing the bill")
        payee = os.getenv("TEST_RECIPIENT_EMAIL", "")
        return jsonify(agents.intake_agent(text, payee))

    @app.get("/api/cycles/<cycle_id>/agents/briefing")
    def agent_briefing(cycle_id):
        return jsonify(agents.run_briefing(get_db(), cycle_id))

    @app.get("/api/cycles/<cycle_id>/agents/reminders")
    def agent_reminders(cycle_id):
        return jsonify(agents.run_reminders(get_db(), cycle_id))

    @app.get("/api/cycles/<cycle_id>/agents/reconcile")
    def agent_reconcile(cycle_id):
        return jsonify(agents.run_reconcile(get_db(), cycle_id))

    return app


if __name__ == "__main__":
    create_app().run(port=int(os.getenv("PORT", "5001")),
                    debug=os.getenv("FLASK_DEBUG") == "1")