import { Save } from 'lucide-react';
import { MemoryScopeSelector } from './MemoryScopeSelector';

export type MemoryDraft = {
  scope: string;
  type: string;
  key: string;
  content: string;
  tags: string;
  importance: number;
  confidence: number;
};

export function MemoryEditor({
  draft,
  onChange,
  onSave,
  saving,
}: {
  draft: MemoryDraft;
  onChange: (draft: MemoryDraft) => void;
  onSave: () => void;
  saving?: boolean;
}) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 text-sm font-semibold text-stone-100">Ajouter une memoire</div>
      <div className="grid gap-3 lg:grid-cols-[140px_180px_1fr]">
        <MemoryScopeSelector value={draft.scope} onChange={(scope) => onChange({ ...draft, scope })} />
        <select value={draft.type} onChange={(event) => onChange({ ...draft, type: event.target.value })} className="field">
          {['fact', 'preference', 'decision', 'procedure', 'warning', 'entity', 'project_note', 'tool_observation'].map((type) => <option key={type}>{type}</option>)}
        </select>
        <input value={draft.key} onChange={(event) => onChange({ ...draft, key: event.target.value })} className="field" placeholder="Key" />
      </div>
      <textarea value={draft.content} onChange={(event) => onChange({ ...draft, content: event.target.value })} className="field mt-3 min-h-28 resize-y" placeholder="Contenu utile, court, sans secret" />
      <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_150px_160px_auto]">
        <input value={draft.tags} onChange={(event) => onChange({ ...draft, tags: event.target.value })} className="field" placeholder="tags separes par virgules" />
        <input type="number" min={0} max={5} value={draft.importance} onChange={(event) => onChange({ ...draft, importance: Number(event.target.value) })} className="field" aria-label="Importance" />
        <input type="number" min={0} max={1} step={0.05} value={draft.confidence} onChange={(event) => onChange({ ...draft, confidence: Number(event.target.value) })} className="field" aria-label="Confidence" />
        <button onClick={onSave} disabled={saving || !draft.content.trim()} className="primary-button justify-center disabled:cursor-not-allowed disabled:opacity-50">
          <Save size={16} /> Save
        </button>
      </div>
    </section>
  );
}
