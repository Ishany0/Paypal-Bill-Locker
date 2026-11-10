'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AgStudio, AgStudioProvider } from 'ag-studio-react';
import { initialState } from './locker-state';
import LockerActions from './locker-actions';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:5000';
const LICENSE_KEY = process.env.NEXT_PUBLIC_AG_STUDIO_LICENSE_KEY;

type Row = Record<string, unknown>;
type Source = { id: string; data: Row[] };

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

// Display only: money stays in whole cents inside the Python ledger.
const dollars = (cents: unknown) => Number(cents) / 100;

async function loadSources(): Promise<Source[]> {
  const cycles = await getJson<Row[]>('/api/cycles');
  if (cycles.length === 0) throw new Error('No cycle found. Run python seed.py first.');
  const cycleId = String(cycles[0].cycle_id);

  const [summary, payments, events, bills] = await Promise.all([
    getJson<Row>(`/api/cycles/${cycleId}/summary`),
    getJson<Row[]>(`/api/cycles/${cycleId}/payments`),
    getJson<Row[]>(`/api/events?cycle_id=${cycleId}`),
    getJson<Row[]>('/api/bills'),
  ]);

  return [
    {
      id: 'summary',
      data: [
        {
          cycle: cycleId,
          salary: dollars(summary.salary_cents),
          locked: dollars(summary.locked_cents),
          safeToSpend: dollars(summary.safe_to_spend_cents),
          lockerBalance: dollars(summary.locker_balance_cents),
          yearlySetAside: dollars(summary.yearly_set_aside_cents),
        },
      ],
    },
    { id: 'payments', data: payments.map((p) => ({ ...p, amount: dollars(p.amount_cents) })) },
    {
      id: 'events',
      data: events.map((e) => ({
        ...e,
        amount: e.amount_cents == null ? null : dollars(e.amount_cents),
      })),
    },
    { id: 'bills', data: bills.map((b) => ({ ...b, amount: dollars(b.amount_cents) })) },
  ];
}

export default function LockerStudio() {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'view' | 'edit'>('edit');
  const latestState = useRef<unknown>(null);

  const load = useCallback(() => {
    loadSources()
      .then((s) => {
        setSources(s);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const data = useMemo(() => (sources ? { sources } : null), [sources]);

  const onStateUpdated = useCallback((event: { state: unknown }) => {
    latestState.current = event.state;
  }, []);

  const copyState = useCallback(async () => {
    if (!latestState.current) return;
    await navigator.clipboard.writeText(JSON.stringify(latestState.current, null, 2));
    alert('Dashboard state copied. Paste it into locker-state.ts');
  }, []);

  if (error) return <p style={{ padding: 24 }}>Could not load the ledger: {error}</p>;
  if (!data) return <p style={{ padding: 24 }}>Loading...</p>;

  const studio = (
    <AgStudio
      data={data}
      mode={mode}
      initialState={initialState}
      onStateUpdated={onStateUpdated}
    />
  );

   return (
     <div>
      <div style={{ display: 'flex', gap: 8, padding: 8, justifyContent: 'flex-end' }}>
        <button onClick={load}>Refresh data</button>
        <button onClick={copyState}>Copy dashboard state</button>
        <button onClick={() => setMode((m) => (m === 'edit' ? 'view' : 'edit'))}>
          {mode === 'edit' ? 'Switch to view mode' : 'Switch to edit mode'}
        </button>
      </div>
      <div style={{ display: 'flex', height: 'calc(100vh - 56px)' }}>
        <div style={{ flex: 1, minWidth: 0, height: '100%' }}>
          {LICENSE_KEY ? (
            <AgStudioProvider licenseKey={LICENSE_KEY}>{studio}</AgStudioProvider>
          ) : (
            studio
          )}
        </div>
        <LockerActions onChanged={load} />
      </div>
    </div>
  );
}