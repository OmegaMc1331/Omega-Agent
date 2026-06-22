export type TestRunView = {
  id: string;
  command: string;
  status: string;
  exit_code?: number | null;
  stdout: string;
  stderr: string;
  summary: string;
  started_at: string;
  completed_at?: string | null;
  metadata?: Record<string, unknown>;
};

export function TestResultPanel({ run }: { run: TestRunView | null }) {
  if (!run) {
    return <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4 text-sm text-zinc-500">Aucun test run selectionne.</section>;
  }
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-stone-100">{run.command || 'No command'}</div>
          <div className="mt-1 text-xs text-zinc-500">{formatDate(run.started_at)} / exit {run.exit_code ?? 'n/a'}</div>
        </div>
        <span className={`rounded-full border px-2 py-1 text-xs ${run.status === 'passed' ? 'border-emerald-400/20 text-emerald-200' : 'border-red-400/20 text-red-200'}`}>{run.status}</span>
      </div>
      <p className="mt-3 text-sm text-zinc-300">{run.summary}</p>
      <pre className="mt-3 max-h-80 overflow-auto rounded-xl border border-white/10 bg-black/20 p-3 text-xs leading-5 text-zinc-400">{[run.stdout, run.stderr].filter(Boolean).join('\n') || 'No output'}</pre>
    </section>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
