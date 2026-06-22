import { useEffect, useState } from 'react';
import { ListChecks, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { TestResultPanel, type TestRunView } from '../components/TestResultPanel';

export function TestRunsPage() {
  const [runs, setRuns] = useState<TestRunView[]>([]);
  const [selected, setSelected] = useState<TestRunView | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const nextRuns = await api<TestRunView[]>('/api/code/tests');
      setRuns(nextRuns);
      setSelected((current) => nextRuns.find((run) => run.id === current?.id) || nextRuns[0] || null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><ListChecks size={18} className="text-zinc-400" /> Test Runs</div>
          <p className="mt-1 text-sm text-zinc-500">Historique des commandes de test executees dans le workspace.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>

      <div className="grid gap-5 xl:grid-cols-[420px_minmax(0,1fr)]">
        <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.035]">
          {runs.map((run) => (
            <button key={run.id} onClick={() => setSelected(run)} className={`block w-full border-b border-white/5 px-4 py-3 text-left text-sm ${selected?.id === run.id ? 'bg-white/[0.06]' : 'hover:bg-white/[0.035]'}`}>
              <div className="flex items-center justify-between gap-3">
                <span className="truncate font-medium text-stone-100">{run.command || 'No command'}</span>
                <span className={run.status === 'passed' ? 'text-emerald-200' : 'text-red-200'}>{run.status}</span>
              </div>
              <div className="mt-1 truncate text-xs text-zinc-500">{run.summary}</div>
            </button>
          ))}
          {runs.length === 0 && <div className="p-6 text-sm text-zinc-500">Aucun test run.</div>}
        </section>
        <TestResultPanel run={selected} />
      </div>
    </div>
  );
}
