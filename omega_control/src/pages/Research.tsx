import { useEffect, useState } from 'react';
import { ArrowRight, RefreshCw, Search } from 'lucide-react';
import { api } from '../api/client';
import { RunStatusBadge } from '../components/RunStatusBadge';
import type { ResearchRunView } from '../types/research';

export function ResearchPage({ onOpen }: { onOpen: (researchRunId: string) => void }) {
  const [runs, setRuns] = useState<ResearchRunView[]>([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      setRuns(await api<ResearchRunView[]>('/api/research'));
      setError('');
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  async function startResearch() {
    if (!question.trim()) return;
    setLoading(true);
    try {
      const run = await api<ResearchRunView>('/api/research', { method: 'POST', body: JSON.stringify({ question }) });
      setQuestion('');
      await load();
      onOpen(run.id);
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Search size={18} className="text-blue-200" /> Omega Research</div>
          <p className="mt-1 text-sm text-zinc-500">Recherche locale et connecteurs read-only, claims vérifiés, citations et evidence graph.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</div>}
      <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
        <label className="text-sm font-medium text-stone-100" htmlFor="research-question">Nouvelle recherche</label>
        <textarea id="research-question" value={question} onChange={(event) => setQuestion(event.target.value)} className="field mt-3 min-h-28 resize-y" placeholder="Ex: Quelles décisions d'architecture sont documentées dans ce workspace ?" />
        <div className="mt-3 flex items-center justify-between gap-3">
          <span className="text-xs text-zinc-600">Web désactivé par défaut. Aucun shell ou browser.</span>
          <button onClick={startResearch} disabled={loading || !question.trim()} className="primary-button"><Search size={16} /> Start research</button>
        </div>
      </section>
      <section className="grid gap-3 md:grid-cols-2">
        {runs.map((run) => (
          <button key={run.id} onClick={() => onOpen(run.id)} className="rounded-2xl border border-white/10 bg-white/[0.035] p-4 text-left transition hover:bg-white/[0.055]">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate font-medium text-stone-100">{run.title}</div>
                <p className="mt-1 line-clamp-2 text-sm text-zinc-500">{run.question}</p>
              </div>
              <RunStatusBadge status={run.status} />
            </div>
            <div className="mt-4 flex items-center justify-between text-xs text-zinc-600"><span>{new Date(run.updated_at).toLocaleString('fr-FR')}</span><span className="flex items-center gap-1 text-zinc-400">Open <ArrowRight size={13} /></span></div>
          </button>
        ))}
        {runs.length === 0 && <div className="rounded-2xl border border-dashed border-white/10 p-8 text-sm text-zinc-500">Aucun research run.</div>}
      </section>
    </div>
  );
}
