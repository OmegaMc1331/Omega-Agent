export type ModelPerformanceView = {
  model_ref?: string;
  agent_profile_id?: string;
  runs: number;
  success_rate: number;
  average_duration_ms: number;
  failed_tool_calls: number;
};

export function ModelPerformanceTable({ title, rows, labelKey }: { title: string; rows: ModelPerformanceView[]; labelKey: 'model_ref' | 'agent_profile_id' }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.035]">
      <div className="border-b border-white/10 px-4 py-3 text-sm font-semibold text-stone-100">{title}</div>
      <div className="grid grid-cols-[1fr_80px_90px_110px] gap-3 border-b border-white/10 px-4 py-2 text-xs uppercase tracking-wide text-zinc-600">
        <div>Name</div>
        <div>Runs</div>
        <div>Success</div>
        <div>Avg</div>
      </div>
      {rows.map((row) => (
        <div key={`${row[labelKey]}-${row.runs}`} className="grid grid-cols-[1fr_80px_90px_110px] gap-3 border-b border-white/5 px-4 py-3 text-sm">
          <div className="truncate text-zinc-200">{row[labelKey] || 'unknown'}</div>
          <div className="text-zinc-500">{row.runs}</div>
          <div className="text-zinc-500">{Math.round((row.success_rate || 0) * 100)}%</div>
          <div className="text-zinc-500">{formatDuration(row.average_duration_ms || 0)}</div>
        </div>
      ))}
      {rows.length === 0 && <div className="p-4 text-sm text-zinc-500">Aucune donnée.</div>}
    </section>
  );
}

function formatDuration(value: number) {
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}
