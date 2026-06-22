import { useEffect, useMemo, useState } from 'react';
import { Boxes, RefreshCw, Search } from 'lucide-react';
import { api } from '../api/client';
import { CapabilityDetails, type CapabilityView } from '../components/CapabilityDetails';
import { CapabilityTable } from '../components/CapabilityTable';

type UsageEvent = {
  id: string;
  capability_id: string;
  status: string;
  created_at: string;
  latency_ms?: number | null;
  error?: string | null;
};

export function CapabilitiesPage() {
  const [items, setItems] = useState<CapabilityView[]>([]);
  const [usage, setUsage] = useState<UsageEvent[]>([]);
  const [selected, setSelected] = useState<CapabilityView | null>(null);
  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const [risk, setRisk] = useState('all');
  const [enabled, setEnabled] = useState('all');
  const [auth, setAuth] = useState('all');
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [nextItems, nextUsage] = await Promise.all([
        api<CapabilityView[]>('/api/capabilities'),
        api<UsageEvent[]>('/api/capabilities/usage'),
      ]);
      setItems(nextItems);
      setUsage(nextUsage);
      setSelected((current) => nextItems.find((item) => item.id === current?.id) || nextItems[0] || null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      if (type !== 'all' && item.type !== type) return false;
      if (risk !== 'all' && item.risk_level !== risk) return false;
      if (enabled !== 'all' && String(item.enabled) !== enabled) return false;
      if (auth !== 'all' && item.auth_status !== auth) return false;
      if (!needle) return true;
      return `${item.id} ${item.name} ${item.description} ${item.tags.join(' ')}`.toLowerCase().includes(needle);
    });
  }, [items, query, type, risk, enabled, auth]);

  async function refresh() {
    await api('/api/capabilities/refresh', { method: 'POST', body: '{}' });
    await load();
  }

  async function toggle(item: CapabilityView) {
    await api<CapabilityView>(`/api/capabilities/${encodeURIComponent(item.id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled: !item.enabled }),
    });
    await load();
  }

  const types = ['all', ...Array.from(new Set(items.map((item) => item.type))).sort()];
  const risks = ['all', 'low', 'medium', 'high', 'critical'];
  const authStatuses = ['all', ...Array.from(new Set(items.map((item) => item.auth_status || 'none'))).sort()];
  const selectedUsage = usage.filter((event) => event.capability_id === selected?.id).slice(0, 8);

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Boxes size={18} className="text-zinc-400" /> Capabilities</div>
          <p className="mt-1 text-sm text-zinc-500">Plan de contrôle unifié pour tools, skills, plugins, providers, agents, MCP, A2A et channels.</p>
        </div>
        <button onClick={refresh} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>

      <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-3 lg:grid-cols-[minmax(240px,1fr)_160px_150px_150px_170px]">
        <label className="relative">
          <Search size={15} className="pointer-events-none absolute left-3 top-3 text-zinc-500" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} className="field pl-9" placeholder="Search capabilities" />
        </label>
        <Filter value={type} onChange={setType} options={types} />
        <Filter value={risk} onChange={setRisk} options={risks} />
        <Filter value={enabled} onChange={setEnabled} options={['all', 'true', 'false']} />
        <Filter value={auth} onChange={setAuth} options={authStatuses} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <CapabilityTable items={filtered} selectedId={selected?.id} onSelect={setSelected} onToggle={toggle} />
        <div className="space-y-4">
          <CapabilityDetails item={selected} />
          <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
            <div className="mb-3 text-sm font-semibold text-stone-100">Usage récent</div>
            {selectedUsage.length === 0 && <div className="text-sm text-zinc-500">Aucun usage récent pour cette capability.</div>}
            <div className="space-y-2">
              {selectedUsage.map((event) => (
                <div key={event.id} className="rounded-xl border border-white/10 bg-black/10 px-3 py-2 text-xs text-zinc-400">
                  <div className="flex justify-between gap-3">
                    <span>{event.status}</span>
                    <span>{formatDate(event.created_at)}</span>
                  </div>
                  {event.error && <div className="mt-1 text-red-200">{event.error}</div>}
                </div>
              ))}
            </div>
          </section>
        </div>
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

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
