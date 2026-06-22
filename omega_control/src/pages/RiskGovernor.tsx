import { useEffect, useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { api } from '../api/client';
import { BudgetViolationCard } from '../components/BudgetViolationCard';
import { RiskBadge } from '../components/RiskBadge';
import type { BudgetViolationView, EffectiveBudgetView } from '../types/budgets';

export function RiskGovernorPage({ onPolicy }: { onPolicy: () => void }) {
  const [effective, setEffective] = useState<EffectiveBudgetView | null>(null);
  const [violations, setViolations] = useState<BudgetViolationView[]>([]);
  const [risk, setRisk] = useState('critical');
  const [category, setCategory] = useState('system_sensitive');
  const [decision, setDecision] = useState<Record<string, unknown> | null>(null);

  async function load() {
    const [nextEffective, nextViolations] = await Promise.all([
      api<EffectiveBudgetView>('/api/budgets/effective'),
      api<BudgetViolationView[]>('/api/budgets/violations'),
    ]);
    setEffective(nextEffective);
    setViolations(nextViolations);
  }
  useEffect(() => { load().catch(() => undefined); }, []);

  async function simulate() {
    const result = await api<{ decision: Record<string, unknown> }>('/api/budgets/simulate', {
      method: 'POST',
      body: JSON.stringify({ action: { tool_name: 'simulated_action', risk_level: risk, action_category: category, arguments: {} } }),
    });
    setDecision(result.decision);
  }

  const limits = effective?.limits || {};
  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div><div className="flex items-center gap-2 font-semibold text-stone-100"><ShieldAlert size={18} className="text-amber-200" /> Risk Governor</div><p className="mt-1 text-sm text-zinc-500">Risk limits are additive to Policy Studio and never broaden an existing permission.</p></div>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Metric label="Maximum risk"><RiskBadge risk={String(limits.max_risk_level || 'high')} /></Metric>
        <Metric label="Destructive write">{String(limits.destructive_write || 'approval_required')}</Metric>
        <Metric label="External side effect">{String(limits.external_side_effect || 'approval_required')}</Metric>
        <Metric label="System sensitive">{String(limits.system_sensitive || 'deny')}</Metric>
      </section>
      <section className="rounded-3xl border border-white/10 bg-white/[0.025] p-5">
        <div className="font-medium text-stone-100">Simulate an action</div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <select value={risk} onChange={(event) => setRisk(event.target.value)} className="field">{['low', 'medium', 'high', 'critical'].map((item) => <option key={item}>{item}</option>)}</select>
          <select value={category} onChange={(event) => setCategory(event.target.value)} className="field">{['read_only', 'reversible_write', 'destructive_write', 'external_side_effect', 'system_sensitive'].map((item) => <option key={item}>{item}</option>)}</select>
          <button onClick={simulate} className="primary-button">Simulate</button>
        </div>
        {decision && <pre className="mt-4 p-4 text-xs text-zinc-400">{JSON.stringify(decision, null, 2)}</pre>}
      </section>
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_280px]">
        <div className="rounded-3xl border border-white/10 bg-white/[0.025] p-5"><div className="mb-4 font-medium text-stone-100">Blocked and high-risk actions</div><div className="space-y-3">{violations.slice(0, 10).map((item) => <BudgetViolationCard key={item.id} violation={item} />)}{violations.length === 0 && <div className="text-sm text-zinc-500">No blocked action recorded.</div>}</div></div>
        <div className="rounded-3xl border border-white/10 bg-white/[0.025] p-5"><div className="font-medium text-stone-100">Related controls</div><p className="mt-2 text-sm text-zinc-500">Policy Studio remains authoritative for permissions and approvals. Budget Governor only adds stricter limits.</p><button onClick={onPolicy} className="secondary-button mt-4 w-full">Open Policy Studio</button></div>
      </section>
    </div>
  );
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-4"><div className="text-xs text-zinc-600">{label}</div><div className="mt-2 text-sm text-stone-100">{children}</div></div>;
}
