import { Save } from 'lucide-react';
import type { BudgetProfileView } from '../types/budgets';
import { RiskLimitEditor } from './RiskLimitEditor';

const numericMetrics = [
  'max_run_seconds',
  'max_tool_calls',
  'max_actions',
  'max_shell_commands',
  'max_files_changed',
  'max_files_deleted',
  'max_rollbacks',
  'max_retries',
  'max_external_calls',
  'max_connector_calls',
  'max_estimated_cost',
  'max_estimated_tokens',
];

export function BudgetCard({
  profile,
  draft,
  onDraft,
  onSave,
}: {
  profile: BudgetProfileView;
  draft: BudgetProfileView;
  onDraft: (value: BudgetProfileView) => void;
  onSave: () => void;
}) {
  function setLimit(key: string, raw: string) {
    const limits = { ...draft.limits };
    if (raw.trim() === '') delete limits[key];
    else limits[key] = Number(raw);
    onDraft({ ...draft, limits });
  }
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-stone-100">{profile.name}</div>
          <p className="mt-1 text-sm text-zinc-500">{profile.description}</p>
        </div>
        <label className="flex items-center gap-2 text-xs text-zinc-500">
          <input type="checkbox" checked={draft.enabled} onChange={(event) => onDraft({ ...draft, enabled: event.target.checked })} />
          enabled
        </label>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-zinc-500">Scope
          <select className="field mt-2" value={draft.scope_type} onChange={(event) => onDraft({ ...draft, scope_type: event.target.value })}>
            {['global', 'project', 'session', 'agent_profile', 'workflow'].map((scope) => <option key={scope}>{scope}</option>)}
          </select>
        </label>
        <label className="text-xs text-zinc-500">Scope ID
          <input className="field mt-2" value={draft.scope_id || ''} onChange={(event) => onDraft({ ...draft, scope_id: event.target.value || null })} placeholder="optional" />
        </label>
        {numericMetrics.map((metric) => (
          <label key={metric} className="text-xs text-zinc-500">{metric.replace(/^max_/, '').replace(/_/g, ' ')}
            <input type="number" min="0" step={metric === 'max_estimated_cost' ? '0.01' : '1'} className="field mt-2" value={String(draft.limits[metric] ?? '')} onChange={(event) => setLimit(metric, event.target.value)} />
          </label>
        ))}
        <RiskLimitEditor value={String(draft.limits.max_risk_level || 'high')} onChange={(value) => onDraft({ ...draft, limits: { ...draft.limits, max_risk_level: value } })} />
      </div>
      <div className="mt-4 flex justify-end"><button onClick={onSave} className="primary-button"><Save size={15} /> Save profile</button></div>
    </section>
  );
}
