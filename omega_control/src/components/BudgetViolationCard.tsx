import { AlertTriangle } from 'lucide-react';
import type { BudgetViolationView } from '../types/budgets';

export function BudgetViolationCard({ violation }: { violation: BudgetViolationView }) {
  return (
    <article className="rounded-2xl border border-red-400/15 bg-red-500/[0.06] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium text-red-100"><AlertTriangle size={15} /> {violation.metric}</div>
        <span className="rounded-full border border-red-400/20 px-2 py-1 text-[11px] text-red-200">{violation.action_taken}</span>
      </div>
      <p className="mt-2 text-sm text-zinc-400">{violation.reason}</p>
      <div className="mt-3 text-xs text-zinc-600">{violation.used_value} / {violation.limit_value} · {new Date(violation.created_at).toLocaleString('fr-FR')}</div>
    </article>
  );
}
