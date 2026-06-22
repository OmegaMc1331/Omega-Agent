import { useEffect, useState } from 'react';
import { Play, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { EvalScoreCard } from '../components/EvalScoreCard';
import { StatusBadge } from '../components/TraceTable';

type EvalRun = {
  id: string;
  name: string;
  description: string;
  status: string;
  dataset_name?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  summary?: { total?: number; passed?: number; failed?: number; error?: number; average_score?: number };
};

type EvalCase = {
  id: string;
  name: string;
  status: string;
  score?: number | null;
  error?: string | null;
  result?: { run_id?: string; comparison?: { checks?: Array<{ kind: string; target: string; passed: boolean }> } };
};

export function EvalsPage() {
  const [evals, setEvals] = useState<EvalRun[]>([]);
  const [cases, setCases] = useState<EvalCase[]>([]);
  const [dataset, setDataset] = useState('');
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const rows = await api<EvalRun[]>('/api/evals');
      setEvals(rows);
      if (!selected && rows[0]) setSelected(rows[0].id);
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

  useEffect(() => {
    if (!selected) return;
    api<EvalCase[]>(`/api/evals/${selected}/cases`).then(setCases).catch(() => setCases([]));
  }, [selected]);

  async function runEval() {
    if (!dataset.trim()) return;
    setLoading(true);
    try {
      const result = await api<EvalRun>('/api/evals/run', { method: 'POST', body: JSON.stringify({ dataset: dataset.trim() }) });
      setSelected(result.id);
      await load();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setLoading(false);
    }
  }

  const latest = evals.find((item) => item.id === selected) || evals[0];

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-lg font-semibold text-stone-100">Evals</div>
          <p className="mt-1 text-sm text-zinc-500">Datasets locaux, scores de tâche et résultats par case.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
      <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
        <div className="grid gap-3 md:grid-cols-[1fr_auto]">
          <input value={dataset} onChange={(event) => setDataset(event.target.value)} className="field" placeholder="dataset name or path" />
          <button onClick={runEval} className="primary-button"><Play size={16} /> Run eval</button>
        </div>
      </section>
      <div className="grid gap-3 md:grid-cols-4">
        <EvalScoreCard title="Eval runs" value={evals.length} />
        <EvalScoreCard title="Average score" value={latest?.summary?.average_score ?? '-'} />
        <EvalScoreCard title="Passed" value={latest?.summary?.passed ?? 0} />
        <EvalScoreCard title="Failed" value={(latest?.summary?.failed || 0) + (latest?.summary?.error || 0)} />
      </div>
      <div className="grid gap-5 xl:grid-cols-[420px_minmax(0,1fr)]">
        <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.035]">
          {evals.map((item) => (
            <button key={item.id} onClick={() => setSelected(item.id)} className={`block w-full border-b border-white/5 p-4 text-left transition hover:bg-white/[0.045] ${selected === item.id ? 'bg-white/[0.055]' : ''}`}>
              <div className="flex items-center justify-between gap-3">
                <div className="truncate text-sm font-medium text-stone-100">{item.name}</div>
                <StatusBadge status={item.status} />
              </div>
              <div className="mt-1 text-xs text-zinc-600">{item.dataset_name || item.id}</div>
            </button>
          ))}
          {evals.length === 0 && <div className="p-5 text-sm text-zinc-500">Aucun eval run.</div>}
        </section>
        <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
          <div className="mb-3 text-sm font-semibold text-stone-100">Cases</div>
          <div className="space-y-2">
            {cases.map((item) => (
              <div key={item.id} className="rounded-xl bg-black/10 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-medium text-zinc-200">{item.name}</div>
                  <div className="flex items-center gap-2"><StatusBadge status={item.status} /><span className="text-xs text-zinc-500">{item.score ?? '-'}</span></div>
                </div>
                {item.error && <div className="mt-2 text-xs text-red-200">{item.error}</div>}
                {item.result?.comparison?.checks?.length ? <div className="mt-2 text-xs text-zinc-500">{item.result.comparison.checks.map((check) => `${check.kind}:${check.passed ? 'ok' : 'fail'}`).join(' · ')}</div> : null}
              </div>
            ))}
            {cases.length === 0 && <div className="text-sm text-zinc-500">Aucune case sélectionnée.</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
