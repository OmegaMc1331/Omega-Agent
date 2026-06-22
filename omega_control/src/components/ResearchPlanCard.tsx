import { ListChecks } from 'lucide-react';

export function ResearchPlanCard({ plan }: { plan: Record<string, unknown> }) {
  const steps = Array.isArray(plan.steps) ? plan.steps.map(String) : [];
  const sources = Array.isArray(plan.needed_sources) ? plan.needed_sources as Array<Record<string, unknown>> : [];
  const scope = typeof plan.scope === 'object' && plan.scope ? plan.scope as Record<string, unknown> : {};
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-stone-100"><ListChecks size={16} className="text-blue-200" /> Plan de recherche</div>
      <div className="mb-3 flex flex-wrap gap-2 text-xs text-zinc-500">
        <span className="rounded-full border border-white/10 px-2 py-1">scope: {String(scope.level || 'unknown')}</span>
        <span className="rounded-full border border-white/10 px-2 py-1">target: {String(scope.target_sources || 0)} sources</span>
      </div>
      <ol className="space-y-2 text-sm text-zinc-300">
        {steps.map((step, index) => <li key={`${step}-${index}`} className="flex gap-3"><span className="text-zinc-600">{index + 1}.</span><span>{step}</span></li>)}
      </ol>
      {sources.length > 0 && (
        <div className="mt-4 border-t border-white/10 pt-3 text-xs text-zinc-500">
          {sources.map((source, index) => <div key={index}>{String(source.type || 'source')} — {String(source.reason || '')}</div>)}
        </div>
      )}
    </section>
  );
}
