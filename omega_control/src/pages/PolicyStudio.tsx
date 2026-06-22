import { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Search, Shield } from 'lucide-react';
import { api } from '../api/client';
import { PolicyRuleCard, type PolicyRuleView } from '../components/PolicyRuleCard';
import { PolicyRuleEditor, type PolicyProfileView, type PolicyRuleDraft } from '../components/PolicyRuleEditor';
import { RiskMatrix } from '../components/RiskMatrix';

export function PolicyStudioPage() {
  const [profiles, setProfiles] = useState<PolicyProfileView[]>([]);
  const [rules, setRules] = useState<PolicyRuleView[]>([]);
  const [query, setQuery] = useState('');
  const [effect, setEffect] = useState('all');
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [nextProfiles, nextRules] = await Promise.all([
        api<PolicyProfileView[]>('/api/policy/profiles'),
        api<PolicyRuleView[]>('/api/policy/rules'),
      ]);
      setProfiles(nextProfiles);
      setRules(nextRules);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rules.filter((rule) => {
      if (effect !== 'all' && rule.effect !== effect) return false;
      if (!needle) return true;
      return `${rule.name} ${rule.tool_name || ''} ${rule.reason}`.toLowerCase().includes(needle);
    });
  }, [rules, query, effect]);

  async function createRule(draft: PolicyRuleDraft) {
    let conditions: Record<string, unknown> = {};
    try {
      conditions = JSON.parse(draft.conditions || '{}');
    } catch {
      conditions = {};
    }
    await api('/api/policy/rules', {
      method: 'POST',
      body: JSON.stringify({
        profile_id: draft.profile_id,
        name: draft.name,
        effect: draft.effect,
        tool_name: draft.tool_name || null,
        action_type: draft.action_type || null,
        resource_pattern: draft.resource_pattern || null,
        risk_level_min: draft.risk_level_min || null,
        conditions,
        priority: Number(draft.priority),
        reason: draft.reason,
      }),
    });
    await load();
  }

  async function toggle(rule: PolicyRuleView) {
    await api(`/api/policy/rules/${encodeURIComponent(rule.id)}`, { method: 'PATCH', body: JSON.stringify({ enabled: !rule.enabled }) });
    await load();
  }

  async function remove(rule: PolicyRuleView) {
    await api(`/api/policy/rules/${encodeURIComponent(rule.id)}`, { method: 'DELETE' });
    await load();
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Shield size={18} className="text-zinc-400" /> Policy Studio</div>
          <p className="mt-1 text-sm text-zinc-500">Créer, éditer et appliquer des règles de gouvernance côté backend.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>

      <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
        <div className="space-y-4">
          <PolicyRuleEditor profiles={profiles} onCreate={createRule} />
          <RiskMatrix />
        </div>
        <div className="space-y-3">
          <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-3 md:grid-cols-[1fr_180px]">
            <label className="relative">
              <Search size={15} className="pointer-events-none absolute left-3 top-3 text-zinc-500" />
              <input value={query} onChange={(event) => setQuery(event.target.value)} className="field pl-9" placeholder="Search rules" />
            </label>
            <select value={effect} onChange={(event) => setEffect(event.target.value)} className="field">
              {['all', 'allow', 'deny', 'require_approval'].map((item) => <option key={item}>{item}</option>)}
            </select>
          </div>
          {filtered.map((rule) => <PolicyRuleCard key={rule.id} rule={rule} onToggle={toggle} onDelete={remove} />)}
        </div>
      </div>
    </div>
  );
}
