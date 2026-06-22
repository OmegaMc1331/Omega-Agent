import { CheckCircle2, Clock3, PauseCircle, XCircle } from 'lucide-react';
import { RunStatusBadge } from './RunStatusBadge';

export type WorkflowStepRunView = {
  id: string;
  step_id: string;
  step_index: number;
  name: string;
  type: string;
  status: string;
  output?: Record<string, unknown> | null;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export type WorkflowRunView = {
  id: string;
  workflow_id: string;
  run_id?: string | null;
  status: string;
  current_step_index: number;
  created_at: string;
  updated_at: string;
  error?: string | null;
};

export function WorkflowRunTimeline({ run, steps, onRetry }: { run: WorkflowRunView | null; steps: WorkflowStepRunView[]; onRetry?: (step: WorkflowStepRunView) => void }) {
  if (!run) {
    return <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-6 text-sm text-zinc-500">No workflow run selected.</div>;
  }
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-stone-100">{run.id}</div>
          <div className="mt-1 text-xs text-zinc-500">Durable run: {run.run_id || '-'}</div>
        </div>
        <RunStatusBadge status={run.status} />
      </div>
      <div className="space-y-3">
        {steps.map((step) => (
          <div key={step.id} className="grid grid-cols-[26px_minmax(0,1fr)] gap-3">
            <div className="mt-1 text-zinc-500">{iconFor(step.status)}</div>
            <div className="rounded-xl border border-white/10 bg-black/10 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-stone-100">{step.step_index + 1}. {step.name}</div>
                  <div className="mt-1 text-xs text-zinc-500">{step.step_id} · {step.type}</div>
                </div>
                <RunStatusBadge status={step.status} />
              </div>
              {step.error && <div className="mt-2 rounded-lg border border-red-400/20 bg-red-500/10 px-2 py-1 text-xs text-red-100">{step.error}</div>}
              {step.output && <pre className="mt-2 max-h-32 overflow-auto rounded-lg bg-black/20 p-2 text-[11px] text-zinc-400">{JSON.stringify(step.output, null, 2)}</pre>}
              {step.status === 'failed' && onRetry && (
                <button onClick={() => onRetry(step)} className="secondary-button mt-2">Retry step</button>
              )}
            </div>
          </div>
        ))}
        {steps.length === 0 && <div className="text-sm text-zinc-500">No step run yet.</div>}
      </div>
    </div>
  );
}

function iconFor(status: string) {
  if (status === 'succeeded') return <CheckCircle2 size={18} className="text-emerald-300" />;
  if (status === 'failed') return <XCircle size={18} className="text-red-300" />;
  if (status === 'waiting_approval' || status === 'paused') return <PauseCircle size={18} className="text-amber-300" />;
  return <Clock3 size={18} />;
}
