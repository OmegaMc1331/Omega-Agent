import { useEffect, useMemo, useState } from 'react';
import { Gauge, Plus, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { BudgetCard } from '../components/BudgetCard';
import { BudgetUsageBar } from '../components/BudgetUsageBar';
import { BudgetViolationCard } from '../components/BudgetViolationCard';
import type { BudgetProfileView, BudgetUsageView, BudgetViolationView, EffectiveBudgetView } from '../types/budgets';

export function BudgetsPage() {
  const [profiles, setProfiles] = useState<BudgetProfileView[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [draft, setDraft] = useState<BudgetProfileView | null>(null);
  const [usage, setUsage] = useState<BudgetUsageView[]>([]);
  const [violations, setViolations] = useState<BudgetViolationView[]>([]);
  const [effective, setEffective] = useState<EffectiveBudgetView | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [nextProfiles, nextUsage, nextViolations, nextEffective] = await Promise.all([
        api<BudgetProfileView[]>('/api/budgets/profiles'),
        api<BudgetUsageView[]>('/api/budgets/usage'),
        api<BudgetViolationView[]>('/api/budgets/violations'),
        api<EffectiveBudgetView>('/api/budgets/effective'),
      ]);
      setProfiles(nextProfiles);
      setUsage(nextUsage);
      setViolations(nextViolations);
      setEffective(nextEffective);
      const selected = nextProfiles.find((item) => item.id === selectedId) || nextProfiles[0] || null;
      setSelectedId(selected?.id || '');
      setDraft(selected ? structuredClone(selected) : null);
      setError('');
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load().catch(() => undefined); }, []);
  const selected = useMemo(() => profiles.find((item) => item.id === selectedId) || null, [profiles, selectedId]);

  async function save() {
    if (!draft) return;
    await api(`/api/budgets/profiles/${draft.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled: draft.enabled, scope_type: draft.scope_type, scope_id: draft.scope_id, limits: draft.limits }),
    });
    await load();
  }

  async function createProfile() {
    const profile = await api<BudgetProfileView>('/api/budgets/profiles', {
      method: 'POST',
      body: JSON.stringify({ name: `Budget ${profiles.length + 1}`, description: 'Custom scoped budget.', enabled: false, scope_type: 'global', limits: { max_risk_level: 'medium' } }),
    });
    await load();
    setSelectedId(profile.id);
    setDraft(profile);
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><div className="flex items-center gap-2 font-semibold text-stone-100"><Gauge size={18} className="text-blue-200" /> Budget Governor</div><p className="mt-1 text-sm text-zinc-500">Backend-enforced limits for runs, workflows, tools, files, retries, providers and risk.</p></div>
        <div className="flex gap-2"><button onClick={createProfile} className="secondary-button"><Plus size={15} /> New profile</button><button onClick={load} className="secondary-button"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh</button></div>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
      <div className="grid gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-2">
          {profiles.map((profile) => <button key={profile.id} onClick={() => { setSelectedId(profile.id); setDraft(structuredClone(profile)); }} className={`w-full rounded-2xl border p-3 text-left ${selectedId === profile.id ? 'border-blue-400/30 bg-blue-500/10' : 'border-white/10 bg-white/[0.025]'}`}><div className="text-sm font-medium text-stone-100">{profile.name}</div><div className="mt-1 text-xs text-zinc-600">{profile.scope_type}{profile.scope_id ? `:${profile.scope_id}` : ''} · {profile.enabled ? 'enabled' : 'disabled'}</div></button>)}
        </aside>
        {selected && draft && <BudgetCard profile={selected} draft={draft} onDraft={setDraft} onSave={save} />}
      </div>
      <section className="grid gap-5 xl:grid-cols-2">
        <div className="rounded-3xl border border-white/10 bg-white/[0.025] p-5"><div className="mb-4 font-medium text-stone-100">Current usage</div><div className="space-y-4">{usage.slice(0, 12).map((item) => <BudgetUsageBar key={item.id} usage={item} />)}{usage.length === 0 && <div className="text-sm text-zinc-500">No usage recorded yet.</div>}</div></div>
        <div className="rounded-3xl border border-white/10 bg-white/[0.025] p-5"><div className="mb-4 font-medium text-stone-100">Recent violations</div><div className="space-y-3">{violations.slice(0, 8).map((item) => <BudgetViolationCard key={item.id} violation={item} />)}{violations.length === 0 && <div className="text-sm text-zinc-500">No budget violation.</div>}</div></div>
      </section>
      <section className="rounded-3xl border border-white/10 bg-white/[0.025] p-5"><div className="font-medium text-stone-100">Effective budget preview</div><div className="mt-2 text-xs text-zinc-600">{effective?.profile_names.join(' + ') || 'No profile'}</div><pre className="mt-4 max-h-80 overflow-auto p-4 text-xs text-zinc-400">{JSON.stringify(effective?.limits || {}, null, 2)}</pre></section>
    </div>
  );
}
