import type { RunMetricsView } from './RunMetricsPanel';

export type TraceListItem = {
  run_id: string;
  title: string;
  status: string;
  model_ref?: string | null;
  agent_profile_id?: string | null;
  updated_at: string;
  metrics?: RunMetricsView | null;
  outcome?: { outcome?: string; auto_score?: number | null } | null;
};

export function TraceTable({ traces, onOpen }: { traces: TraceListItem[]; onOpen: (runId: string) => void }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.035]">
      <div className="grid grid-cols-[1fr_110px_110px_100px] gap-3 border-b border-white/10 px-4 py-3 text-xs uppercase tracking-wide text-zinc-600 max-lg:grid-cols-[1fr_90px]">
        <div>Run</div>
        <div>Status</div>
        <div className="max-lg:hidden">Tools</div>
        <div className="max-lg:hidden">Score</div>
      </div>
      {traces.map((trace) => (
        <button key={trace.run_id} onClick={() => onOpen(trace.run_id)} className="grid w-full grid-cols-[1fr_110px_110px_100px] gap-3 border-b border-white/5 px-4 py-3 text-left text-sm transition hover:bg-white/[0.045] max-lg:grid-cols-[1fr_90px]">
          <div className="min-w-0">
            <div className="truncate text-stone-100">{trace.title || trace.run_id}</div>
            <div className="mt-1 truncate text-xs text-zinc-600">{trace.run_id} · {formatDate(trace.updated_at)}</div>
          </div>
          <div><StatusBadge status={trace.status} /></div>
          <div className="text-zinc-400 max-lg:hidden">{trace.metrics?.tool_calls_count || 0}</div>
          <div className="text-zinc-400 max-lg:hidden">{trace.outcome?.auto_score ?? '-'}</div>
        </button>
      ))}
      {traces.length === 0 && <div className="p-5 text-sm text-zinc-500">Aucune trace disponible.</div>}
    </section>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone = status === 'succeeded' || status === 'passed' ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100' : status === 'failed' || status === 'error' ? 'border-red-400/20 bg-red-500/10 text-red-100' : 'border-white/10 bg-white/[0.045] text-zinc-300';
  return <span className={`inline-flex h-6 items-center rounded-full border px-2 text-xs ${tone}`}>{status}</span>;
}

function formatDate(value: string) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
