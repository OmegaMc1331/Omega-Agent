import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, RefreshCw, Sparkles } from 'lucide-react';
import { api } from '../api/client';
import { SkillActivationToggle } from '../components/SkillActivationToggle';
import { SkillVersionBadge } from '../components/SkillVersionBadge';
import type { SkillView } from '../types/skills';

export function SkillsPage({ onOpen }: { onOpen: (skillId: string) => void }) {
  const [skills, setSkills] = useState<SkillView[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      setSkills(await api<SkillView[]>('/api/skills'));
      setError('');
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load().catch(() => undefined); }, []);
  const visible = useMemo(
    () => skills.filter((skill) => `${skill.name} ${skill.description} ${skill.status || ''} ${skill.skill_type || ''}`.toLowerCase().includes(query.toLowerCase())),
    [skills, query],
  );

  async function toggle(skill: SkillView) {
    setLoading(true);
    try {
      const route = skill.enabled ? 'disable' : 'activate';
      if (skill.path?.startsWith('db://') || skill.definition) {
        await api(`/api/skills/${skill.id}/${route}`, { method: 'POST' });
      } else {
        await api(`/api/skills/${skill.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !skill.enabled }) });
      }
      await load();
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Sparkles size={18} className="text-blue-200" /> Skills</div>
          <p className="mt-1 text-sm text-zinc-500">Local skills remain subject to Omega capability and policy checks.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
      <input value={query} onChange={(event) => setQuery(event.target.value)} className="field max-w-lg" placeholder="Search skills..." />
      <div className="grid gap-3 xl:grid-cols-2">
        {visible.map((skill) => (
          <article key={skill.id} className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="flex items-start justify-between gap-3">
              <button onClick={() => onOpen(skill.id)} className="min-w-0 text-left">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-stone-100">{skill.name}</span>
                  <SkillVersionBadge version={skill.version || '0.1.0'} />
                  <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-zinc-500">{skill.status || (skill.enabled ? 'active' : 'disabled')}</span>
                </div>
                <p className="mt-2 text-sm text-zinc-500">{skill.description || 'No description.'}</p>
              </button>
              <SkillActivationToggle active={skill.enabled} disabled={loading || (skill.status === 'draft' && !skill.definition)} onChange={() => toggle(skill)} />
            </div>
            <div className="mt-4 flex items-center justify-between text-xs text-zinc-600">
              <span>{skill.skill_type || 'prompt'} · {skill.risk_level || 'low'}</span>
              <button onClick={() => onOpen(skill.id)} className="flex items-center gap-1 text-zinc-400 hover:text-stone-100">Details <ArrowRight size={13} /></button>
            </div>
          </article>
        ))}
        {!loading && visible.length === 0 && <div className="rounded-3xl border border-dashed border-white/10 p-10 text-sm text-zinc-500">No skill found.</div>}
      </div>
    </div>
  );
}
