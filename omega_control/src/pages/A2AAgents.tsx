import { useEffect, useState } from 'react';
import { AlertTriangle, Bot, Plus } from 'lucide-react';
import { api } from '../api/client';

type A2AAgent = {
  id: string;
  name: string;
  description: string;
  endpoint?: string | null;
  agent_card: Record<string, unknown>;
  enabled: boolean;
  trust_level: string;
  scopes: string[];
  status: string;
  updated_at: string;
};

export function A2AAgentsPage() {
  const [items, setItems] = useState<A2AAgent[]>([]);
  const [draft, setDraft] = useState({ name: '', endpoint: '', description: '' });

  async function load() {
    setItems(await api<A2AAgent[]>('/api/a2a/agents'));
  }

  useEffect(() => {
    load().catch(() => setItems([]));
  }, []);

  async function addAgent() {
    if (!draft.name.trim()) return;
    await api<A2AAgent>('/api/a2a/agents', {
      method: 'POST',
      body: JSON.stringify({
        name: draft.name,
        endpoint: draft.endpoint || null,
        description: draft.description,
        agent_card: { name: draft.name, endpoint: draft.endpoint || null, description: draft.description },
      }),
    });
    setDraft({ name: '', endpoint: '', description: '' });
    await load();
  }

  async function toggle(item: A2AAgent) {
    await api<A2AAgent>(`/api/a2a/agents/${encodeURIComponent(item.id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled: !item.enabled }),
    });
    await load();
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div>
        <div className="flex items-center gap-2 font-semibold text-stone-100"><Bot size={18} className="text-zinc-400" /> A2A Agents</div>
        <p className="mt-1 text-sm text-zinc-500">External agent cards are registered as manifests. Omega does not delegate externally in v1.</p>
      </div>
      <div className="flex items-start gap-3 rounded-2xl border border-amber-400/20 bg-amber-400/10 p-4 text-sm text-amber-100">
        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
        <span>External A2A execution is disabled in v1. These entries are discovery metadata only.</span>
      </div>
      <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-4 md:grid-cols-[1fr_1fr_1fr_auto]">
        <input className="field" placeholder="Name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
        <input className="field" placeholder="Endpoint" value={draft.endpoint} onChange={(event) => setDraft({ ...draft, endpoint: event.target.value })} />
        <input className="field" placeholder="Description" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
        <button onClick={addAgent} className="primary-button"><Plus size={16} /> Add</button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((item) => (
          <article key={item.id} className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-semibold text-stone-100">{item.name}</div>
                <div className="mt-1 text-xs text-zinc-500">{item.id} · {item.status} · {item.trust_level}</div>
              </div>
              <button onClick={() => toggle(item)} className="secondary-button h-8 px-3 text-xs">{item.enabled ? 'Disable' : 'Enable'}</button>
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-500">{item.description || 'No description'}</p>
            <div className="mt-3 truncate text-xs text-zinc-500">Endpoint: {item.endpoint || 'none'}</div>
            <pre className="mt-3 max-h-36 overflow-auto rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-400">{JSON.stringify(item.agent_card, null, 2)}</pre>
          </article>
        ))}
      </div>
    </div>
  );
}
