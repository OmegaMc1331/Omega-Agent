import { CheckCircle2, Circle, XCircle } from 'lucide-react';
import { RunStatusBadge } from './RunStatusBadge';

export type StepView = {
  id: string;
  step_index: number;
  type: string;
  status: string;
  title: string;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
};

export function RunTimeline({ steps }: { steps: StepView[] }) {
  if (steps.length === 0) return <div className="text-sm text-zinc-500">Aucune étape.</div>;
  return (
    <div className="space-y-2">
      {steps.map((step) => {
        const Icon = step.status === 'succeeded' ? CheckCircle2 : step.status === 'failed' ? XCircle : Circle;
        return (
          <div key={step.id} className="rounded-2xl border border-white/10 bg-white/[0.035] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-stone-100">
                <Icon size={15} className="text-zinc-400" />
                <span className="text-zinc-500">#{step.step_index}</span>
                <span className="truncate">{step.title}</span>
              </div>
              <RunStatusBadge status={step.status} />
            </div>
            <div className="mt-1 text-xs text-zinc-500">{step.type}{step.error ? ` · ${step.error}` : ''}</div>
          </div>
        );
      })}
    </div>
  );
}
