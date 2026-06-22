import { useEffect, useMemo, useState } from 'react';
import { Plug, RefreshCw, Search } from 'lucide-react';
import { api } from '../api/client';
import { ConnectorCard, type ConnectorView } from '../components/ConnectorCard';
import { ConnectorOperationTable, type ConnectorOperationView } from '../components/ConnectorOperationTable';

type UsageEvent = {
  id: string;
  connector_id: string;
  operation_id?: string | null;
  status: string;
  latency_ms?: number | null;
  error?: string | null;
  created_at: string;
};

export function ConnectorsPage() {
  const [items, setItems] = useState<ConnectorView[]>([]);
  const [operations, setOperations] = useState<ConnectorOperationView[]>([]);
  const [usage, setUsage] = useState<UsageEvent[]>([]);
  const [selected, setSelected] = useState<ConnectorView | null>(null);
  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const [trust, setTrust] = useState('all');
  const [enabled, setEnabled] = useState('all');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [nextItems, nextUsage] = await Promise.all([
        api<ConnectorView[]>('/api/connectors'),
        api<UsageEvent[]>('/api/connectors/usage'),
      ]);
      setItems(nextItems);
      const nextSelected = nextItems.find((item) => item.id === selected?.id) || nextItems[0] || null;
      setSelected(nextSelected);
      if (nextSelected) {
        setOperations(await api<ConnectorOperationView[]>(`/api/connectors/${encodeURIComponent(nextSelected.id)}/operations`));
      } else {
        setOperations([]);
      }
      setUsage(nextUsage);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch((error) => setMessage(String(error.message || error)));
  }, []);

  async function select(connector: ConnectorView) {
    setSelected(connector);
    setOperations(await api<ConnectorOperationView[]>(`/api/connectors/${encodeURIComponent(connector.id)}/operations`));
  }

  async function toggle(connector: ConnectorView) {
    await api(`/api/connectors/${encodeURIComponent(connector.id)}/${connector.enabled ? 'disable' : 'enable'}`, { method: 'POST' });
    await load();
  }

  async function test() {
    if (!selected) return;
    const result = await api<Record<string, unknown>>(`/api/connectors/${encodeURIComponent(selected.id)}/test`, { method: 'POST' });
    setMessage(JSON.stringify(result));
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      if (type !== 'all' && item.type !== type) return false;
      if (trust !== 'all' && item.trust_level !== trust) return false;
      if (enabled !== 'all' && String(item.enabled) !== enabled) return false;
      if (!needle) return true;
      return `${item.id} ${item.name} ${item.description} ${item.type} ${item.scopes.join(' ')}`.toLowerCase().includes(needle);
    });
  }, [items, query, type, trust, enabled]);

  const types = ['all', ...Array.from(new Set(items.map((item) => item.type))).sort()];
  const trusts = ['all', ...Array.from(new Set(items.map((item) => item.trust_level))).sort()];
  const selectedUsage = usage.filter((event) => event.connector_id === selected?.id).slice(0, 8);

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Plug size={18} className="text-zinc-400" /> Connectors</div>
          <p className="mt-1 text-sm text-zinc-500">API-first control plane for governed external and local operations. Browser fallback stays disabled by default.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={test} className="secondary-button" disabled={!selected}>Test</button>
          <button onClick={() => load().catch((error) => setMessage(String(error.message || error)))} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
        </div>
      </div>

      {message && <div className="rounded-2xl border border-white/10 bg-white/[0.035] px-4 py-3 text-sm text-zinc-300">{message}</div>}

      <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-3 lg:grid-cols-[minmax(240px,1fr)_160px_160px_160px]">
        <label className="relative">
          <Search size={15} className="pointer-events-none absolute left-3 top-3 text-zinc-500" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} className="field pl-9" placeholder="Search connectors" />
        </label>
        <Filter value={type} onChange={setType} options={types} />
        <Filter value={trust} onChange={setTrust} options={trusts} />
        <Filter value={enabled} onChange={setEnabled} options={['all', 'true', 'false']} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="grid gap-3 md:grid-cols-2">
          {filtered.map((connector) => (
            <ConnectorCard key={connector.id} connector={connector} selected={connector.id === selected?.id} onSelect={select} onToggle={toggle} />
          ))}
          {filtered.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-6 text-sm text-zinc-500">No connectors match the filters.</div>}
        </div>
        <aside className="space-y-4">
          <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
            <div className="mb-2 text-sm font-semibold text-stone-100">{selected?.name || 'No connector selected'}</div>
            <div className="space-y-1 text-sm text-zinc-400">
              <div>Status: {selected?.status || '-'}</div>
              <div>Trust: {selected?.trust_level || '-'}</div>
              <div>Base URL: {selected?.base_url || '-'}</div>
              <div>Auth ref: {selected?.auth_ref || '-'}</div>
            </div>
          </section>
          <ConnectorOperationTable operations={operations} />
          <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
            <div className="mb-3 text-sm font-semibold text-stone-100">Recent usage</div>
            <div className="space-y-2">
              {selectedUsage.map((event) => (
                <div key={event.id} className="rounded-xl border border-white/10 bg-black/10 px-3 py-2 text-xs text-zinc-400">
                  <div className="flex justify-between gap-3"><span>{event.operation_id || '-'}</span><span>{event.status}</span></div>
                  {event.error && <div className="mt-1 text-red-200">{event.error}</div>}
                </div>
              ))}
              {selectedUsage.length === 0 && <div className="text-sm text-zinc-500">No recent usage.</div>}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function Filter({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: string[] }) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)} className="field">
      {options.map((option) => <option key={option}>{option}</option>)}
    </select>
  );
}
