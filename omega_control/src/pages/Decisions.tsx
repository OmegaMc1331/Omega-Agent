import { useEffect, useState } from 'react';
import { Plus, RefreshCw, ScrollText } from 'lucide-react';
import { api } from '../api/client';
import { DecisionCard, type DecisionView } from '../components/DecisionCard';

export function DecisionsPage() {
  const [items, setItems] = useState<DecisionView[]>([]);
  const [draft, setDraft] = useState({ title: '', content: '', reason: '' });
  const [status, setStatus] = useState('active');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (status !== 'all') params.set('status', status);
      setItems(await api<DecisionView[]>(`/api/decisions?${params.toString()}`));
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

  async function addDecision() {
    try {
      await api<DecisionView>('/api/decisions', {
        method: 'POST',
        body: JSON.stringify({ title: draft.title, content: draft.content, reason: draft.reason }),
      });
      setDraft({ title: '', content: '', reason: '' });
      await load();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    }
  }

  async function archive(item: DecisionView) {
    await api<{ ok: boolean }>(`/api/decisions/${item.id}`, { method: 'DELETE' });
    await load();
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><ScrollText size={18} className="text-zinc-400" /> Decisions</div>
          <p className="mt-1 text-sm text-zinc-500">Journal de decisions projet avec raisons et provenance.</p>
        </div>
        <div className="flex gap-2">
          <select value={status} onChange={(event) => setStatus(event.target.value)} className="field h-10 w-36">
            {['active', 'superseded', 'archived', 'all'].map((item) => <option key={item}>{item}</option>)}
          </select>
          <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
        </div>
      </div>

      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</div>}

      <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
        <div className="grid gap-3 lg:grid-cols-[220px_1fr]">
          <input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} className="field" placeholder="Titre" />
          <input value={draft.reason} onChange={(event) => setDraft({ ...draft, reason: event.target.value })} className="field" placeholder="Reason" />
        </div>
        <textarea value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} className="field mt-3 min-h-24 resize-y" placeholder="Decision" />
        <div className="mt-3 flex justify-end">
          <button onClick={addDecision} disabled={!draft.title.trim() || !draft.content.trim()} className="primary-button disabled:cursor-not-allowed disabled:opacity-50">
            <Plus size={16} /> Add decision
          </button>
        </div>
      </section>

      <div className="space-y-3">
        {items.map((item) => <DecisionCard key={item.id} item={item} onArchive={archive} />)}
      </div>
      {!loading && items.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-8 text-center text-sm text-zinc-500">Aucune decision.</div>}
    </div>
  );
}
