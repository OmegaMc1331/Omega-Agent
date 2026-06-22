import { Play } from 'lucide-react';

export type WorkflowView = {
  id: string;
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  updated_at: string;
  definition: { steps?: Array<{ id: string; type: string; name?: string }> };
};

export function WorkflowCard({ workflow, selected, onSelect, onRun }: { workflow: WorkflowView; selected: boolean; onSelect: (workflow: WorkflowView) => void; onRun: (workflow: WorkflowView) => void }) {
  const stepCount = workflow.definition.steps?.length || 0;
  return (
    <button onClick={() => onSelect(workflow)} className={`w-full rounded-2xl border p-4 text-left transition ${selected ? 'border-blue-400/25 bg-blue-500/10' : 'border-white/10 bg-white/[0.035] hover:bg-white/[0.055]'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-stone-100">{workflow.name}</div>
          <div className="mt-1 line-clamp-2 text-xs text-zinc-500">{workflow.description || 'No description'}</div>
        </div>
        <span className={`rounded-full border px-2 py-1 text-[11px] ${workflow.enabled ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100' : 'border-white/10 bg-white/[0.045] text-zinc-400'}`}>
          {workflow.enabled ? 'enabled' : 'disabled'}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-zinc-500">
        <span>v{workflow.version} · {stepCount} steps</span>
        <span>{formatDate(workflow.updated_at)}</span>
      </div>
      <div className="mt-3">
        <span onClick={(event) => { event.stopPropagation(); onRun(workflow); }} className="secondary-button inline-flex">
          <Play size={14} /> Run
        </span>
      </div>
    </button>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
