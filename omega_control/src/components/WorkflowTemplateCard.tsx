import { CopyPlus } from 'lucide-react';

export type WorkflowTemplateView = {
  id: string;
  name: string;
  description: string;
  category: string;
  definition: Record<string, unknown>;
};

export function WorkflowTemplateCard({ template, onCreate }: { template: WorkflowTemplateView; onCreate: (template: WorkflowTemplateView) => void }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-stone-100">{template.name}</div>
          <div className="mt-1 text-xs uppercase tracking-wide text-zinc-600">{template.category}</div>
        </div>
      </div>
      <p className="mt-2 line-clamp-3 text-sm text-zinc-500">{template.description}</p>
      <button onClick={() => onCreate(template)} className="secondary-button mt-3">
        <CopyPlus size={15} /> Create workflow
      </button>
    </div>
  );
}
