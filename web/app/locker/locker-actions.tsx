'use client';

import { useCallback, useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:5001';

type Payment = {
  bill_id: number;
  name: string;
  amount_cents: number;
  status: string;
  due_date: string | null;
};
type PayResult = { bill_id: number; outcome: string; detail: string };

const money = (cents: number) => `$${(cents / 100).toFixed(2)}`; // display only

export default function LockerActions({ onChanged }: { onChanged: () => void }) {
  const [cycleId, setCycleId] = useState<string | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [waiting, setWaiting] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const cycles = await (await fetch(`${API}/api/cycles`)).json();
      if (!cycles.length) throw new Error('No cycle yet. Run python seed.py');
      const id = String(cycles[0].cycle_id);
      setCycleId(id);
      setPayments(await (await fetch(`${API}/api/cycles/${id}/payments`)).json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const post = useCallback(async (path: string) => {
    const response = await fetch(`${API}${path}`, { method: 'POST' });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error ?? `Request failed (${response.status})`);
    return body;
  }, []);

  const run = useCallback(
    async (action: () => Promise<void>) => {
      setBusy(true);
      let failure: string | null = null;
      try {
        await action();
      } catch (e) {
        failure = e instanceof Error ? e.message : String(e);
      }
      await reload();
      if (failure) setError(failure);
      onChanged();
      setBusy(false);
    },
    [reload, onChanged],
  );

  const pay = (billId: number) =>
    run(async () => {
      const result: PayResult = await post(`/api/cycles/${cycleId}/payments/${billId}/pay`);
      setNotes((n) => ({ ...n, [billId]: `${result.outcome}: ${result.detail}` }));
      setWaiting((w) => ({ ...w, [billId]: result.outcome === 'NEEDS_APPROVAL' }));
    });

  const approve = (billId: number) =>
    run(async () => {
      await post(`/api/cycles/${cycleId}/payments/${billId}/approve`);
      setWaiting((w) => ({ ...w, [billId]: false }));
      setNotes((n) => ({ ...n, [billId]: 'Approved. Press Pay again.' }));
    });

  const payAll = () =>
    run(async () => {
      const results: PayResult[] = await post(`/api/cycles/${cycleId}/pay-all`);
      setNotes((n) => {
        const next = { ...n };
        results.forEach((r) => {
          next[r.bill_id] = `${r.outcome}: ${r.detail}`;
        });
        return next;
      });
      setWaiting((w) => {
        const next = { ...w };
        results.forEach((r) => {
          next[r.bill_id] = r.outcome === 'NEEDS_APPROVAL';
        });
        return next;
      });
    });

  const refreshStatuses = () =>
    run(async () => {
      await post(`/api/cycles/${cycleId}/refresh`);
    });

  return (
    <aside
      style={{
        width: 340,
        padding: 12,
        overflowY: 'auto',
        borderLeft: '1px solid #ddd',
        fontFamily: 'sans-serif',
        fontSize: 14,
      }}
    >
      <h2 style={{ margin: '0 0 8px', fontSize: 16 }}>Bills this cycle</h2>
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        <button disabled={busy || !cycleId} onClick={payAll}>
          Pay all
        </button>
        <button disabled={busy || !cycleId} onClick={refreshStatuses}>
          Refresh PayPal status
        </button>
      </div>
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      {payments.map((p) => {
        const canPay = p.status === 'LOCKED' || p.status === 'FAILED';
        return (
          <div key={p.bill_id} style={{ borderBottom: '1px solid #eee', padding: '8px 0' }}>
            <strong>{p.name}</strong> {money(p.amount_cents)}
            <div>
              Due {p.due_date ?? 'n/a'} · {p.status}
            </div>
            <div style={{ marginTop: 4 }}>
              {waiting[p.bill_id] ? (
                <button disabled={busy} onClick={() => approve(p.bill_id)}>
                  Approve
                </button>
              ) : (
                <button disabled={busy || !canPay} onClick={() => pay(p.bill_id)}>
                  Pay
                </button>
              )}
            </div>
            {notes[p.bill_id] && <small>{notes[p.bill_id]}</small>}
          </div>
        );
      })}
    </aside>
  );
}