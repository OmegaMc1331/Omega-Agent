import { useEffect, useState } from 'react';
import { RefreshCw, ScanSearch } from 'lucide-react';
import { api } from '../api/client';
import { SkillCandidateCard } from '../components/SkillCandidateCard';
import type { SkillCandidateView } from '../types/skills';

export function SkillFoundryPage({ onOpenSkill }: { onOpenSkill: (skillId: string) => void }) {
  const [items, setItems] = useState<SkillCandidateView[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      setItems(await api<SkillCandidateView[]>('/api/skills/candidates'));
      setError('');
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load().catch(() => undefined); }, []);

  async function detect() {
    setLoading(true);
    try {
      await api('/api/skills/candidates/detect', { method: 'POST' });
      await load();
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
      setLoading(false);
    }
  }

  async function accept(id: string) {
    setLoading(true);
    try {
      const skill = await api<{ id: string }>(`/api/skills/candidates/${id}/accept`, { method: 'POST' });
      await load();
      onOpenSkill(skill.id);
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
      setLoading(false);
    }
  }

  async function reject(id: string) {
    setLoading(true);
    try {
      await api(`/api/skills/candidates/${id}/reject`, { method: 'POST' });
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
          <div className="flex items-center gap-2 font-semibold text-stone-100"><ScanSearch size={18} className="text-blue-200" /> Omega Skill Foundry</div>
          <p className="mt-1 text-sm text-zinc-500">Review repeated successful trajectories before creating a local, versioned draft.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="secondary-button"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh</button>
          <button onClick={detect} disabled={loading} className="primary-button"><ScanSearch size={15} /> Detect candidates</button>
        </div>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
      <div className="space-y-4">
        {items.map((item) => <SkillCandidateCard key={item.id} candidate={item} busy={loading} onAccept={() => accept(item.id)} onReject={() => reject(item.id)} />)}
        {!loading && items.length === 0 && <div className="rounded-3xl border border-dashed border-white/10 p-10 text-center text-sm text-zinc-500">No candidate yet. Detection requires two similar successful runs, or an explicitly reusable trajectory.</div>}
      </div>
    </div>
  );
}
