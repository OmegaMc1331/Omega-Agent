import { useEffect, useState } from 'react';
import { ArrowLeft, CheckCircle2, Play, Power, PowerOff } from 'lucide-react';
import { api } from '../api/client';
import { SkillTestResult } from '../components/SkillTestResult';
import { SkillVersionBadge } from '../components/SkillVersionBadge';
import type { SkillDetailView } from '../types/skills';

export function SkillDetailsPage({ skillId, onBack }: { skillId: string; onBack: () => void }) {
  const [detail, setDetail] = useState<SkillDetailView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    if (!skillId) return;
    setLoading(true);
    try {
      setDetail(await api<SkillDetailView>(`/api/skills/${skillId}`));
      setError('');
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load().catch(() => undefined); }, [skillId]);

  async function action(name: 'test' | 'activate' | 'disable') {
    setLoading(true);
    try {
      await api(`/api/skills/${skillId}/${name}`, { method: 'POST' });
      await load();
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
      setLoading(false);
    }
  }

  if (!skillId) return <div className="p-6 text-sm text-zinc-500">Select a skill first.</div>;
  if (!detail) return <div className="p-6 text-sm text-zinc-500">{error || (loading ? 'Loading...' : 'Skill not found.')}</div>;
  const { skill } = detail;
  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <button onClick={onBack} className="flex items-center gap-1 text-xs text-zinc-500 hover:text-stone-100"><ArrowLeft size={13} /> Skills</button>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
      <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><h2 className="text-lg font-semibold text-stone-100">{skill.name}</h2><SkillVersionBadge version={skill.version} /></div>
            <p className="mt-2 text-sm text-zinc-500">{skill.description}</p>
            <div className="mt-3 text-xs text-zinc-600">{skill.status} · {skill.skill_type} · {skill.risk_level} risk · {detail.usage.count} usage event(s)</div>
          </div>
          <div className="flex gap-2">
            <button disabled={loading} onClick={() => action('test')} className="secondary-button"><Play size={15} /> Run tests</button>
            {skill.enabled
              ? <button disabled={loading} onClick={() => action('disable')} className="secondary-button"><PowerOff size={15} /> Disable</button>
              : <button disabled={loading} onClick={() => action('activate')} className="primary-button"><Power size={15} /> Activate</button>}
          </div>
        </div>
      </section>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-3xl border border-white/10 bg-white/[0.025] p-5">
          <div className="mb-3 flex items-center gap-2 font-medium text-stone-100"><CheckCircle2 size={16} /> Definition</div>
          <pre className="max-h-[640px] overflow-auto p-4 text-xs text-zinc-400">{JSON.stringify(skill.definition || {}, null, 2)}</pre>
        </section>
        <div className="space-y-5">
          <section className="rounded-3xl border border-white/10 bg-white/[0.025] p-5">
            <div className="mb-3 font-medium text-stone-100">Test runs</div>
            <div className="space-y-2">{detail.tests.map((test) => <SkillTestResult key={test.id} test={test} />)}</div>
            {detail.tests.length === 0 && <p className="text-sm text-zinc-500">No test run. Activation is blocked until a test passes.</p>}
          </section>
          <section className="rounded-3xl border border-white/10 bg-white/[0.025] p-5">
            <div className="mb-3 font-medium text-stone-100">Versions</div>
            <div className="space-y-2 text-sm text-zinc-500">
              {detail.versions.map((version) => <div key={version.id} className="rounded-2xl border border-white/10 p-3"><div className="text-zinc-300">v{version.version}</div><div className="mt-1 text-xs">{version.changelog}</div></div>)}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
