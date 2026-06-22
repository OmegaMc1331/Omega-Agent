export type RunMetricsView = {
  total_duration_ms?: number;
  tool_calls_count?: number;
  failed_tool_calls_count?: number;
  approvals_count?: number;
  rollbacks_count?: number;
  files_changed_count?: number;
  shell_commands_count?: number;
  risk_max?: string | null;
};

export function RunMetricsPanel({ metrics }: { metrics?: RunMetricsView | null }) {
  if (!metrics) {
    return <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4 text-sm text-zinc-500">Aucune métrique disponible.</section>;
  }
  const rows = [
    ['Duration', formatDuration(metrics.total_duration_ms || 0)],
    ['Tool calls', String(metrics.tool_calls_count || 0)],
    ['Tool failures', String(metrics.failed_tool_calls_count || 0)],
    ['Approvals', String(metrics.approvals_count || 0)],
    ['Rollbacks', String(metrics.rollbacks_count || 0)],
    ['Files changed', String(metrics.files_changed_count || 0)],
    ['Shell commands', String(metrics.shell_commands_count || 0)],
    ['Max risk', metrics.risk_max || 'none'],
  ];
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 text-sm font-semibold text-stone-100">Run metrics</div>
      <div className="grid gap-2 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3 rounded-xl bg-black/10 px-3 py-2 text-sm">
            <span className="text-zinc-500">{label}</span>
            <span className="text-zinc-200">{value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatDuration(value: number) {
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} s`;
}
