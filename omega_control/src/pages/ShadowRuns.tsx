import { useEffect, useState } from 'react';
import { Box, Play, Plus, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import type { ShadowRunView } from '../types/shadow';

export function ShadowRunsPage({ onOpen }: { onOpen: (id: string) => void }) {
  const [items, setItems] = useState<ShadowRunView[]>([]);
  const [objective, setObjective] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  async function load() {
    setLoading(true);
    try {
      setItems(await api<ShadowRunView[]>('/api/shadow'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  async function create() {
    if (!objective.trim()) return;
    const created = await api<ShadowRunView>('/api/shadow', { method: 'POST', body: JSON.stringify({ objective }) });
    setObjective('');
    setMessage(`Shadow créé: ${created.id}`);
    await load();
    onOpen(created.id);
  }

  async function run(item: ShadowRunView) {
    const completed = await api<ShadowRunView>(`/api/shadow/${item.id}/run`, { method: 'POST', body: '{}' });
    setMessage(`Shadow ${completed.status}: ${completed.id}`);
    await load();
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Box size={18} className="text-violet-300" /> Shadow Runs</div>
          <p className="mt-1 text-sm text-zinc-500">Simuler dans un workspace isolé, vérifier le risque, puis promouvoir en live.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>
      <section className="rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <input value={objective} onChange={(event) => setObjective(event.target.value)} className="field flex-1" placeholder="Ex: crée un fichier test-shadow.txt avec OK" />
          <button onClick={create} className="primary-button"><Plus size={15} /> Créer</button>
        </div>
      </section>
      {message && <div className="rounded-2xl border border-blue-400/20 bg-blue-500/10 px-4 py-3 text-sm text-blue-100">{message}</div>}
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((item) => (
          <article key={item.id} className="rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4">
            <div className="flex items-start justify-between gap-3">
              <button onClick={() => onOpen(item.id)} className="min-w-0 text-left">
                <div className="truncate font-semibold text-stone-100">{item.objective}</div>
                <div className="mt-1 text-xs text-zinc-500">{item.source_type} · {item.id.slice(0, 10)}</div>
              </button>
              <Status value={item.status} />
            </div>
            <div className="mt-4 flex items-center justify-between text-xs text-zinc-500">
              <span>Risk: {item.risk_report?.risk_level || '-'}</span>
              <span>{item.risk_report?.recommendation || '-'}</span>
            </div>
            <div className="mt-4 flex gap-2">
              {item.status === 'pending' && <button onClick={() => run(item)} className="secondary-button"><Play size={14} /> Run shadow</button>}
              <button onClick={() => onOpen(item.id)} className="secondary-button">Open</button>
            </div>
          </article>
        ))}
      </div>
      {!items.length && !loading && <div className="rounded-3xl border border-dashed border-white/10 p-10 text-center text-sm text-zinc-500">Aucun shadow run.</div>}
    </div>
  );
}

function Status({ value }: { value: string }) {
  const tone = value === 'succeeded' || value === 'promoted' ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100' : value === 'failed' || value === 'rejected' ? 'border-red-400/20 bg-red-500/10 text-red-100' : 'border-amber-400/20 bg-amber-500/10 text-amber-100';
  return <span className={`rounded-full border px-2 py-1 text-[11px] ${tone}`}>{value}</span>;
}
