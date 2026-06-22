import { useState } from 'react';

export type PolicyProfileView = {
  id: string;
  name: string;
  enabled: boolean;
  priority: number;
  scope_type: string;
  scope_id?: string | null;
  default_action: string;
};

export type PolicyRuleDraft = {
  profile_id: string;
  name: string;
  effect: string;
  tool_name: string;
  action_type: string;
  resource_pattern: string;
  risk_level_min: string;
  conditions: string;
  priority: number;
  reason: string;
};

export function PolicyRuleEditor({ profiles, onCreate }: { profiles: PolicyProfileView[]; onCreate: (draft: PolicyRuleDraft) => void }) {
  const [draft, setDraft] = useState<PolicyRuleDraft>({
    profile_id: profiles[0]?.id || 'developer-workspace',
    name: '',
    effect: 'require_approval',
    tool_name: '',
    action_type: '',
    resource_pattern: '',
    risk_level_min: '',
    conditions: '{}',
    priority: 100,
    reason: '',
  });

  function update<K extends keyof PolicyRuleDraft>(key: K, value: PolicyRuleDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 text-sm font-semibold text-stone-100">Create rule</div>
      <div className="grid gap-3">
        <input value={draft.name} onChange={(event) => update('name', event.target.value)} className="field" placeholder="Rule name" />
        <div className="grid gap-3 md:grid-cols-3">
          <select value={draft.profile_id} onChange={(event) => update('profile_id', event.target.value)} className="field">
            {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
          </select>
          <select value={draft.effect} onChange={(event) => update('effect', event.target.value)} className="field">
            {['allow', 'deny', 'require_approval'].map((item) => <option key={item}>{item}</option>)}
          </select>
          <input type="number" value={draft.priority} onChange={(event) => update('priority', Number(event.target.value))} className="field" />
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <input value={draft.tool_name} onChange={(event) => update('tool_name', event.target.value)} className="field" placeholder="tool name optional" />
          <input value={draft.action_type} onChange={(event) => update('action_type', event.target.value)} className="field" placeholder="action type optional" />
          <select value={draft.risk_level_min} onChange={(event) => update('risk_level_min', event.target.value)} className="field">
            {['', 'low', 'medium', 'high', 'critical'].map((item) => <option key={item} value={item}>{item || 'risk min optional'}</option>)}
          </select>
        </div>
        <input value={draft.resource_pattern} onChange={(event) => update('resource_pattern', event.target.value)} className="field" placeholder="resource pattern optional, e.g. src/*" />
        <textarea value={draft.conditions} onChange={(event) => update('conditions', event.target.value)} className="field min-h-24 font-mono text-xs" />
        <input value={draft.reason} onChange={(event) => update('reason', event.target.value)} className="field" placeholder="Reason shown to the user" />
        <button onClick={() => onCreate(draft)} className="primary-button" disabled={!draft.name.trim()}>Create rule</button>
      </div>
    </section>
  );
}
