import { useEffect, useState } from 'react';
import { AlertTriangle, Plug, Plus } from 'lucide-react';
import { api } from '../api/client';

type MCPServer = {
  id: string;
  name: string;
  description: string;
  command?: string | null;
  url?: string | null;
  enabled: boolean;
  trust_level: string;
  scopes: string[];
  status: string;
  updated_at: string;
};

export function MCPServersPage() {
  const [items, setItems] = useState<MCPServer[]>([]);
  const [draft, setDraft] = useState({ name: '', url: '', command: '' });

  async function load() {
    setItems(await api<MCPServer[]>('/api/mcp/servers'));
  }

  useEffect(() => {
    load().catch(() => setItems([]));
  }, []);

  async function addServer() {
    if (!draft.name.trim()) return;
    await api<MCPServer>('/api/mcp/servers', {
      method: 'POST',
      body: JSON.stringify({ name: draft.name, url: draft.url || null, command: draft.command || null }),
    });
    setDraft({ name: '', url: '', command: '' });
    await load();
  }

  async function toggle(item: MCPServer) {
    await api<MCPServer>(`/api/mcp/servers/${encodeURIComponent(item.id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled: !item.enabled }),
    });
    await load();
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div>
        <div className="flex items-center gap-2 font-semibold text-stone-100"><Plug size={18} className="text-zinc-400" /> MCP Servers</div>
        <p className="mt-1 text-sm text-zinc-500">Manifest registry only. Omega does not execute external MCP servers in v1.</p>
      </div>
      <div className="flex items-start gap-3 rounded-2xl border border-amber-400/20 bg-amber-400/10 p-4 text-sm text-amber-100">
        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
        <span>MCP execution is disabled in Capability Control Plane v1 unless explicitly enabled later by policy and implementation.</span>
      </div>
      <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-4 md:grid-cols-[1fr_1fr_1fr_auto]">
        <input className="field" placeholder="Name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
        <input className="field" placeholder="URL" value={draft.url} onChange={(event) => setDraft({ ...draft, url: event.target.value })} />
        <input className="field" placeholder="Command" value={draft.command} onChange={(event) => setDraft({ ...draft, command: event.target.value })} />
        <button onClick={addServer} className="primary-button"><Plus size={16} /> Add</button>
      </div>
      <div className="grid gap-3">
        {items.map((item) => (
          <article key={item.id} className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-semibold text-stone-100">{item.name}</div>
                <div className="mt-1 text-xs text-zinc-500">{item.id} · {item.status} · {item.trust_level}</div>
              </div>
              <button onClick={() => toggle(item)} className="secondary-button h-8 px-3 text-xs">{item.enabled ? 'Disable' : 'Enable'}</button>
            </div>
            <div className="mt-3 grid gap-2 text-sm text-zinc-500 md:grid-cols-2">
              <div className="truncate">URL: {item.url || 'none'}</div>
              <div className="truncate">Command: {item.command || 'none'}</div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
