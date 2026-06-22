import type { BudgetUsageView } from '../types/budgets';

export function BudgetUsageBar({ usage }: { usage: BudgetUsageView }) {
  const limit = usage.limit_value;
  const ratio = limit && limit > 0 ? Math.min(1, usage.used_value / limit) : 0;
  const tone = usage.status === 'exceeded' ? 'bg-red-400' : usage.status === 'warning' ? 'bg-amber-400' : 'bg-blue-400';
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="text-zinc-400">{usage.metric.replace(/^max_/, '').replace(/_/g, ' ')}</span>
        <span className="text-zinc-600">{format(usage.used_value)} / {limit == null ? 'unlimited' : format(limit)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
        <div className={`h-full rounded-full transition-all ${tone}`} style={{ width: `${Math.max(2, ratio * 100)}%` }} />
      </div>
    </div>
  );
}

function format(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}
