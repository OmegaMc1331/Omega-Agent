import { ListChecks } from 'lucide-react';
import type { ShadowPlanStep } from '../types/shadow';

export function ShadowPlanCard({ steps = [] }: { steps?: ShadowPlanStep[] }) {
  return (
    <section className="rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4">
      <div className="mb-4 flex items-center gap-2 font-semibold text-stone-100"><ListChecks size={17} className="text-blue-300" /> Plan shadow</div>
      <div className="space-y-2">
        {steps.map((step) => (
          <div key={`${step.index}-${step.name}`} className="rounded-2xl border border-white/10 bg-black/10 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium text-stone-100">{step.index + 1}. {step.name}</div>
              <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-zinc-400">{step.risk_level}</span>
            </div>
            <div className="mt-1 text-xs text-zinc-500">{step.tool_name || step.type} · {step.action_category}{!step.simulable ? ' · non simulable' : ''}</div>
          </div>
        ))}
        {!steps.length && <div className="text-sm text-zinc-500">Aucun step compilé.</div>}
      </div>
    </section>
  );
}
