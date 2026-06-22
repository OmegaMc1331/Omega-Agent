import { useEffect, useMemo, useState } from 'react';
import { Activity, RefreshCw, Send } from 'lucide-react';
import { api } from '../api/client';
import { ConnectionStatus } from '../components/ConnectionStatus';
import { EventDetailDrawer } from '../components/EventDetailDrawer';
import { EventFilterBar, type EventFilters } from '../components/EventFilterBar';
import { EventTimeline } from '../components/EventTimeline';
import { OmegaEventClient } from '../ws/eventClient';
import type { EventConnectionStatus, OmegaEvent } from '../ws/eventTypes';

const emptyFilters: EventFilters = { type: '', source: '', level: '', session_id: '', run_id: '' };

export function EventInspectorPage() {
  const [events, setEvents] = useState<OmegaEvent[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [filters, setFilters] = useState<EventFilters>(emptyFilters);
  const [selected, setSelected] = useState<OmegaEvent | null>(null);
  const [status, setStatus] = useState<EventConnectionStatus>('closed');
  const client = useMemo(() => new OmegaEventClient('/ws'), []);

  async function load() {
    const params = new URLSearchParams({ limit: '200' });
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    const [nextEvents, nextTypes] = await Promise.all([
      api<OmegaEvent[]>(`/api/events/v2?${params.toString()}`),
      api<{ types: string[] }>('/api/events/v2/types'),
    ]);
    setEvents(nextEvents);
    setTypes(nextTypes.types || []);
  }

  async function emitTest() {
    const event = await api<OmegaEvent>('/api/events/v2/test', {
      method: 'POST',
      body: JSON.stringify({ type: 'system.test', payload: { ok: true, origin: 'omega_control' } }),
    });
    setEvents((current) => [event, ...current.filter((item) => item.id !== event.id)].slice(0, 200));
  }

  useEffect(() => {
    load().catch(() => setEvents([]));
  }, [filters.type, filters.source, filters.level, filters.session_id, filters.run_id]);

  useEffect(() => {
    const offEvent = client.onEvent((event) => {
      setEvents((current) => [event, ...current.filter((item) => item.id !== event.id)].slice(0, 200));
    });
    const offStatus = client.onStatus(setStatus);
    client.connect();
    return () => {
      offEvent();
      offStatus();
      client.close();
    };
  }, [client]);

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Activity size={18} className="text-zinc-400" /> Event Inspector</div>
          <p className="mt-1 text-sm text-zinc-500">AG-UI events v1 persistants, redacted et rejouables.</p>
        </div>
        <div className="flex items-center gap-2">
          <ConnectionStatus status={status} />
          <button className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-zinc-300 hover:text-stone-100" onClick={() => load()} type="button">
            <RefreshCw size={15} /> Refresh
          </button>
          <button className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-zinc-300 hover:text-stone-100" onClick={() => emitTest()} type="button">
            <Send size={15} /> Test
          </button>
        </div>
      </div>
      <EventFilterBar filters={filters} types={types} onChange={setFilters} />
      <EventTimeline events={events} onSelect={(event) => setSelected(event as OmegaEvent)} />
      <EventDetailDrawer event={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
