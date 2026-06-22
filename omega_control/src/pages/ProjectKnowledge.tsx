import { useEffect, useMemo, useState } from 'react';
import { Boxes, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { DecisionCard, type DecisionView } from '../components/DecisionCard';
import { MemoryCard, type MemoryEntryView } from '../components/MemoryCard';

type ProjectView = { id: string; name: string };
type ConflictView = { id: string; conflict_type: string; memory_a_id: string; memory_b_id: string; status: string };
type KnowledgeView = {
  project_id: string;
  important_memories: MemoryEntryView[];
  procedures: MemoryEntryView[];
  warnings: MemoryEntryView[];
  resolved_errors: MemoryEntryView[];
  decisions: DecisionView[];
  conflicts: ConflictView[];
};

export function ProjectKnowledgePage() {
  const [projects, setProjects] = useState<ProjectView[]>([]);
  const [projectId, setProjectId] = useState('default');
  const [knowledge, setKnowledge] = useState<KnowledgeView | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadProjects() {
    const nextProjects = await api<ProjectView[]>('/api/projects');
    setProjects(nextProjects);
    setProjectId((current) => nextProjects.find((project) => project.id === current)?.id || nextProjects[0]?.id || 'default');
  }

  async function loadKnowledge(targetProjectId = projectId) {
    setLoading(true);
    try {
      setKnowledge(await api<KnowledgeView>(`/api/projects/${encodeURIComponent(targetProjectId)}/knowledge`));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProjects().catch(() => undefined);
  }, []);

  useEffect(() => {
    loadKnowledge(projectId).catch(() => undefined);
  }, [projectId]);

  const sections = useMemo(() => [
    ['Important memories', knowledge?.important_memories || []],
    ['Procedures', knowledge?.procedures || []],
    ['Warnings', knowledge?.warnings || []],
    ['Resolved errors', knowledge?.resolved_errors || []],
  ] as const, [knowledge]);

  async function archiveMemory(item: MemoryEntryView) {
    await api<MemoryEntryView>(`/api/memory/${item.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'archived' }) });
    await loadKnowledge(projectId);
  }

  async function deleteMemory(item: MemoryEntryView) {
    await api<{ ok: boolean }>(`/api/memory/${item.id}`, { method: 'DELETE' });
    await loadKnowledge(projectId);
  }

  async function editMemory(item: MemoryEntryView) {
    const nextContent = window.prompt('Modifier la memoire', item.content);
    if (nextContent === null) return;
    await api<MemoryEntryView>(`/api/memory/${item.id}`, { method: 'PATCH', body: JSON.stringify({ content: nextContent }) });
    await loadKnowledge(projectId);
  }

  async function archiveDecision(item: DecisionView) {
    await api<{ ok: boolean }>(`/api/decisions/${item.id}`, { method: 'DELETE' });
    await loadKnowledge(projectId);
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Boxes size={18} className="text-zinc-400" /> Project Knowledge</div>
          <p className="mt-1 text-sm text-zinc-500">Synthese durable du projet: decisions, procedures, warnings et conflits memoire.</p>
        </div>
        <div className="flex gap-2">
          <select value={projectId} onChange={(event) => setProjectId(event.target.value)} className="field h-10 w-56">
            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
          <button onClick={() => loadKnowledge(projectId)} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
        </div>
      </div>

      {knowledge?.conflicts && knowledge.conflicts.length > 0 && (
        <section className="rounded-2xl border border-amber-300/20 bg-amber-500/10 p-4">
          <div className="mb-2 text-sm font-semibold text-amber-100">Conflits ouverts</div>
          <div className="space-y-2">
            {knowledge.conflicts.map((conflict) => (
              <div key={conflict.id} className="text-sm text-amber-100">{conflict.conflict_type}: {conflict.memory_a_id} vs {conflict.memory_b_id}</div>
            ))}
          </div>
        </section>
      )}

      {sections.map(([title, memories]) => (
        <section key={title} className="space-y-3">
          <div className="text-sm font-semibold text-stone-100">{title}</div>
          <div className="grid gap-3 xl:grid-cols-2">
            {memories.map((item) => <MemoryCard key={item.id} item={item} onEdit={editMemory} onArchive={archiveMemory} onDelete={deleteMemory} />)}
          </div>
          {memories.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-5 text-sm text-zinc-500">Aucun element.</div>}
        </section>
      ))}

      <section className="space-y-3">
        <div className="text-sm font-semibold text-stone-100">Decisions actives</div>
        {knowledge?.decisions.map((item) => <DecisionCard key={item.id} item={item} onArchive={archiveDecision} />)}
        {(!knowledge || knowledge.decisions.length === 0) && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-5 text-sm text-zinc-500">Aucune decision active.</div>}
      </section>
    </div>
  );
}
