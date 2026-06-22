import { useEffect, useState } from 'react';
import { Shield, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { ScopeSelector } from '../components/ScopeSelector';
import type { PolicyProfileView } from '../components/PolicyRuleEditor';

export function PolicyProfilesPage() {
  const [profiles, setProfiles] = useState<PolicyProfileView[]>([]);
  const [draft, setDraft] = useState({ name: '', description: '', priority: 0, scope_type: 'global', scope_id: '', default_action: 'require_approval' });
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setProfiles(await api<PolicyProfileView[]>('/api/policy/profiles'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  async function toggle(profile: PolicyProfileView) {
    await api(`/api/policy/profiles/${encodeURIComponent(profile.id)}`, { method: 'PATCH', body: JSON.stringify({ enabled: !profile.enabled }) });
    await load();
  }

  async function createProfile() {
    if (!draft.name.trim()) return;
    await api('/api/policy/profiles', {
      method: 'POST',
      body: JSON.stringify({ ...draft, scope_id: draft.scope_id || null, priority: Number(draft.priority) }),
    });
    setDraft({ name: '', description: '', priority: 0, scope_type: 'global', scope_id: '', default_action: 'require_approval' });
    await load();
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Shield size={18} className="text-zinc-400" /> Policy Profiles</div>
          <p className="mt-1 text-sm text-zinc-500">Profils de gouvernance appliqués par priorité côté backend.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>

      <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
        <div className="mb-3 text-sm font-semibold text-stone-100">Create profile</div>
        <div className="grid gap-3">
          <input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} className="field" placeholder="Profile name" />
          <input value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} className="field" placeholder="Description" />
          <div className="grid gap-3 md:grid-cols-[1fr_140px_180px]">
            <ScopeSelector scopeType={draft.scope_type} scopeId={draft.scope_id} onScopeType={(value) => setDraft((current) => ({ ...current, scope_type: value }))} onScopeId={(value) => setDraft((current) => ({ ...current, scope_id: value }))} />
            <input type="number" value={draft.priority} onChange={(event) => setDraft((current) => ({ ...current, priority: Number(event.target.value) }))} className="field" />
            <select value={draft.default_action} onChange={(event) => setDraft((current) => ({ ...current, default_action: event.target.value }))} className="field">
              {['allow', 'deny', 'require_approval'].map((item) => <option key={item}>{item}</option>)}
            </select>
          </div>
          <button onClick={createProfile} className="primary-button">Create profile</button>
        </div>
      </section>

      <div className="grid gap-3">
        {profiles.map((profile) => (
          <article key={profile.id} className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="font-medium text-zinc-100">{profile.name}</div>
                <div className="mt-1 text-xs text-zinc-500">{profile.id} · priority {profile.priority} · {profile.scope_type}:{profile.scope_id || '*'}</div>
              </div>
              <button onClick={() => toggle(profile)} className="secondary-button">{profile.enabled ? 'Disable' : 'Enable'}</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
