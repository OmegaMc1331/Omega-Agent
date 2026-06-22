import { useEffect, useMemo, useState } from 'react';
import { Database, RefreshCw, Search } from 'lucide-react';
import { api } from '../api/client';
import { MemoryCard, type MemoryEntryView } from '../components/MemoryCard';
import { MemoryEditor, type MemoryDraft } from '../components/MemoryEditor';

type MemorySuggestionView = {
  id: string;
  run_id: string;
  project_id?: string | null;
  suggested_type: string;
  content: string;
  reason: string;
  status: string;
  created_at: string;
};

const initialDraft: MemoryDraft = {
  scope: 'project',
  type: 'fact',
  key: '',
  content: '',
  tags: '',
  importance: 3,
  confidence: 0.8,
};

export function MemoryPage() {
  const [items, setItems] = useState<MemoryEntryView[]>([]);
  const [suggestions, setSuggestions] = useState<MemorySuggestionView[]>([]);
  const [draft, setDraft] = useState<MemoryDraft>(initialDraft);
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState('all');
  const [type, setType] = useState('all');
  const [status, setStatus] = useState('active');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (query.trim()) params.set('q', query.trim());
      if (scope !== 'all') params.set('scope', scope);
      params.set('status', status);
      const [nextItems, nextSuggestions] = await Promise.all([
        api<MemoryEntryView[]>(`/api/memory?${params.toString()}`),
        api<MemorySuggestionView[]>('/api/memory/suggestions'),
      ]);
      setItems(nextItems);
      setSuggestions(nextSuggestions);
      setError('');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  const filtered = useMemo(() => {
    if (type === 'all') return items;
    return items.filter((item) => item.type === type);
  }, [items, type]);

  async function save() {
    setSaving(true);
    try {
      await api<MemoryEntryView>('/api/memory', {
        method: 'POST',
        body: JSON.stringify({
          scope: draft.scope,
          type: draft.type,
          key: draft.key,
          content: draft.content,
          tags: draft.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
          importance: draft.importance,
          confidence: draft.confidence,
        }),
      });
      setDraft(initialDraft);
      await load();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setSaving(false);
    }
  }

  async function edit(item: MemoryEntryView) {
    const nextContent = window.prompt('Modifier la memoire', item.content);
    if (nextContent === null) return;
    await api<MemoryEntryView>(`/api/memory/${item.id}`, { method: 'PATCH', body: JSON.stringify({ content: nextContent }) });
    await load();
  }

  async function archive(item: MemoryEntryView) {
    await api<MemoryEntryView>(`/api/memory/${item.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'archived' }) });
    await load();
  }

  async function remove(item: MemoryEntryView) {
    await api<{ ok: boolean }>(`/api/memory/${item.id}`, { method: 'DELETE' });
    await load();
  }

  async function acceptSuggestion(id: string) {
    await api<MemoryEntryView>(`/api/memory/suggestions/${id}/accept`, { method: 'POST', body: '{}' });
    await load();
  }

  async function rejectSuggestion(id: string) {
    await api<{ ok: boolean }>(`/api/memory/suggestions/${id}/reject`, { method: 'POST', body: '{}' });
    await load();
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Database size={18} className="text-zinc-400" /> Project Memory</div>
          <p className="mt-1 text-sm text-zinc-500">Memoire locale editable avec provenance, scopes, confiance et suggestions.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>

      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</div>}

      <MemoryEditor draft={draft} onChange={setDraft} onSave={save} saving={saving} />

      <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-3 lg:grid-cols-[minmax(240px,1fr)_150px_190px_150px]">
        <label className="relative">
          <Search size={15} className="pointer-events-none absolute left-3 top-3 text-zinc-500" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void load(); }} className="field pl-9" placeholder="Search memory" />
        </label>
        <Filter value={scope} onChange={setScope} options={['all', 'global', 'project', 'session', 'agent', 'run']} />
        <Filter value={type} onChange={setType} options={['all', 'fact', 'preference', 'decision', 'procedure', 'warning', 'entity', 'project_note', 'tool_observation']} />
        <Filter value={status} onChange={setStatus} options={['active', 'archived', 'deleted']} />
      </div>

      {suggestions.length > 0 && (
        <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
          <div className="mb-3 text-sm font-semibold text-stone-100">Suggestions pending</div>
          <div className="space-y-2">
            {suggestions.map((suggestion) => (
              <div key={suggestion.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/10 px-3 py-2 text-sm text-zinc-300">
                <div className="min-w-0">
                  <div className="text-xs text-zinc-500">{suggestion.suggested_type} / run {suggestion.run_id}</div>
                  <div className="truncate">{suggestion.content}</div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => acceptSuggestion(suggestion.id)} className="secondary-button h-8 px-3 text-xs">Accept</button>
                  <button onClick={() => rejectSuggestion(suggestion.id)} className="secondary-button h-8 px-3 text-xs">Reject</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-3 xl:grid-cols-2">
        {filtered.map((item) => <MemoryCard key={item.id} item={item} onEdit={edit} onArchive={archive} onDelete={remove} />)}
      </div>
      {!loading && filtered.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-8 text-center text-sm text-zinc-500">Aucune memoire pour ces filtres.</div>}
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
