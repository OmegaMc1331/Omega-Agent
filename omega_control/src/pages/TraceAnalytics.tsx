import { useEffect, useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { RunMetricsPanel } from '../components/RunMetricsPanel';
import { TraceTable, type TraceListItem } from '../components/TraceTable';

type RunTrace = {
  run?: { id: string; title: string; status: string };
  summary?: Record<string, unknown>;
  steps?: unknown[];
  actions?: unknown[];
  events?: unknown[];
  metrics?: Record<string, unknown>;
};

export function TraceAnalyticsPage() {
  const [traces, setTraces] = useState<TraceListItem[]>([]);
  const [selected, setSelected] = useState<RunTrace | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const path = filter ? `/api/traces?status=${encodeURIComponent(filter)}` : '/api/traces';
      const rows = await api<TraceListItem[]>(path);
      setTraces(rows);
      setError('');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [filter]);

  async function openTrace(runId: string) {
    setSelectedId(runId);
    setSelected(await api<RunTrace>(`/api/traces/${runId}`));
  }

  async function exportTrace() {
    if (!selectedId) return;
    const payload = await api<RunTrace>(`/api/traces/${selectedId}/export`);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `omega-trace-${selectedId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-lg font-semibold text-stone-100">Trace Analytics</div>
          <p className="mt-1 text-sm text-zinc-500">Runs, timeline compacte, actions et métriques redacted.</p>
        </div>
        <div className="flex gap-2">
          <select value={filter} onChange={(event) => setFilter(event.target.value)} className="field h-10 w-40">
            <option value="">All</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
        </div>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <TraceTable traces={traces} onOpen={openTrace} />
        <div className="space-y-5">
          <RunMetricsPanel metrics={selected?.metrics as never} />
          <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-stone-100">Trace detail</div>
              <button onClick={exportTrace} disabled={!selectedId} className="secondary-button h-8 px-3 text-xs"><Download size={14} /> Export JSON</button>
            </div>
            <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-xl bg-black/20 p-3 text-xs leading-5 text-zinc-400">{selected ? JSON.stringify(selected, null, 2) : 'Sélectionne un run.'}</pre>
          </section>
        </div>
      </div>
    </div>
  );
}
