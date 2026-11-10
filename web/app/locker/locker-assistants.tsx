'use client';

import { useCallback, useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:5000';
const JSON_HEADERS = { 'Content-Type': 'application/json' };

type Cycle = { cycle_id: string; salary_cents: number };
type Proposal = {
  name: string;
  amount_cents: number;
  payee_email: string;
  frequency: string;
  due_day: number;
  due_date: string | null;
  note: string;
};
type Briefing = { headline: string; bullets: string[] };
type Reminders = { reminders: { bill: string; urgency: string; message: string }[] };
type Reconcile = {
  summary: string;
  issues: { bill: string; what_happened: string; next_step: string }[];
};

const money = (cents: number) => `$${(cents / 100).toFixed(2)}`; // display only
const box = { border: '1px solid #ddd', borderRadius: 6, padding: 8, marginTop: 8 } as const;

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error ?? `Request failed (${response.status})`);
  return body as T;
}

export default function LockerAssistants({
  onChanged,
  onNewCycle,
}: {
  onChanged: () => void;
  onNewCycle: () => void;
}) {
  const [cycle, setCycle] = useState<Cycle | null>(null);
  const [text, setText] = useState('');
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [reminders, setReminders] = useState<Reminders | null>(null);
  const [reconcile, setReconcile] = useState<Reconcile | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadCycle = useCallback(async () => {
    const rows = await call<Cycle[]>('/api/cycles');
    setCycle(rows[0] ?? null);
  }, []);

  useEffect(() => {
    loadCycle().catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [loadCycle]);

  const work = useCallback(async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }, []);

  const askIntake = () =>
    work(async () => {
      setInfo(null);
      setProposal(
        await call<Proposal>('/api/agents/intake', {
          method: 'POST',
          headers: JSON_HEADERS,
          body: JSON.stringify({ text }),
        }),
      );
    });

  const confirmBill = () =>
    work(async () => {
      if (!proposal) return;
      await call('/api/bills', {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify({
          name: proposal.name,
          amount_cents: proposal.amount_cents,
          payee_email: proposal.payee_email,
          frequency: proposal.frequency,
          due_day: proposal.due_day,
          due_date: proposal.due_date,
        }),
      });
      setProposal(null);
      setText('');
      setInfo('Bill added. Start a new cycle to lock it.');
      onChanged();
    });

  const startCycle = () =>
    work(async () => {
      if (!cycle) throw new Error('No earlier cycle to copy the salary from');
      const today = new Date();
      const end = new Date(today.getTime() + 29 * 86400000);
      await call('/api/cycles', {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify({
          cycle_id: today.toISOString().replace(/[-:T]/g, '').slice(0, 12),
          salary_cents: cycle.salary_cents,
          start_date: today.toISOString().slice(0, 10),
          end_date: end.toISOString().slice(0, 10),
        }),
      });
      await loadCycle();
      setInfo('New cycle started. Open the Bills tab.');
      onChanged();
      onNewCycle();
    });

  const runAgent = <T,>(path: string, set: (value: T) => void) =>
    work(async () => {
      if (!cycle) throw new Error('No cycle yet. Run python seed.py');
      set(await call<T>(`/api/cycles/${cycle.cycle_id}/agents/${path}`));
    });

  return (
    <div style={{ padding: 12, fontFamily: 'sans-serif', fontSize: 14 }}>
      <h2 style={{ margin: '0 0 4px', fontSize: 16 }}>AI assistants</h2>
      <small>They only advise. Payments still go through the guardrail.</small>
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      {info && <p style={{ color: 'green' }}>{info}</p>}
      {busy && <p>Thinking...</p>}

      <div style={box}>
        <strong>Intake agent</strong>
        <textarea
          rows={3}
          style={{ width: '100%', marginTop: 4 }}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. Netflix $15.99 every month on the 12th"
        />
        <button disabled={busy || !text.trim()} onClick={askIntake}>
          Read my sentence
        </button>
        {proposal && (
          <div style={{ marginTop: 8 }}>
            <div>
              <strong>{proposal.name}</strong> {money(proposal.amount_cents)} ({proposal.frequency})
            </div>
            <div>Due {proposal.due_date ?? `day ${proposal.due_day}`}</div>
            {proposal.note && <small>{proposal.note}</small>}
            <div style={{ marginTop: 4 }}>
              <button disabled={busy} onClick={confirmBill}>
                Confirm and add
              </button>
            </div>
          </div>
        )}
        <div style={{ marginTop: 8 }}>
          <button disabled={busy || !cycle} onClick={startCycle}>
            Start a new cycle (locks all bills)
          </button>
        </div>
      </div>

      <div style={box}>
        <strong>Planner agent</strong>
        <div>
          <button disabled={busy} onClick={() => runAgent<Briefing>('briefing', setBriefing)}>
            AI briefing
          </button>
        </div>
        {briefing && (
          <div style={{ marginTop: 6 }}>
            <strong>{briefing.headline}</strong>
            <ul style={{ margin: '4px 0', paddingLeft: 18 }}>
              {briefing.bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div style={box}>
        <strong>Reminder agent</strong>
        <div>
          <button disabled={busy} onClick={() => runAgent<Reminders>('reminders', setReminders)}>
            AI reminders
          </button>
        </div>
        {reminders?.reminders.map((r, i) => (
          <p key={i} style={{ margin: '6px 0' }}>
            <strong>
              {r.bill} ({r.urgency})
            </strong>
            <br />
            {r.message}
          </p>
        ))}
      </div>

      <div style={box}>
        <strong>Reconcile agent</strong>
        <div>
          <button disabled={busy} onClick={() => runAgent<Reconcile>('reconcile', setReconcile)}>
            Explain payments
          </button>
        </div>
        {reconcile && (
          <div style={{ marginTop: 6 }}>
            <p style={{ margin: '4px 0' }}>{reconcile.summary}</p>
            {reconcile.issues.map((x, i) => (
              <p key={i} style={{ margin: '6px 0' }}>
                <strong>{x.bill}</strong>: {x.what_happened}
                <br />
                Next: {x.next_step}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}