import { Archive, Pencil, Trash2 } from 'lucide-react';
import { ProvenanceBadge } from './ProvenanceBadge';

export type MemoryEntryView = {
  id: string;
  scope: string;
  scope_id?: string | null;
  project_id?: string | null;
  session_id?: string | null;
  run_id?: string | null;
  key: string;
  content: string;
  summary?: string | null;
  type: string;
  confidence: number;
  importance: number;
  status: string;
  tags: string[];
  provenance?: Array<{ source_type?: string; source_id?: string | null; source_label?: string | null; quote?: string | null }>;
  updated_at: string;
};

export function MemoryCard({
  item,
  onEdit,
  onArchive,
  onDelete,
}: {
  item: MemoryEntryView;
  onEdit: (item: MemoryEntryView) => void;
  onArchive: (item: MemoryEntryView) => void;
  onDelete: (item: MemoryEntryView) => void;
}) {
  return (
    <article className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-white/10 bg-black/10 px-2 py-1 text-xs text-zinc-400">{item.scope}</span>
            <span className="rounded-full border border-white/10 bg-black/10 px-2 py-1 text-xs text-zinc-400">{item.type}</span>
            <span className="rounded-full border border-white/10 bg-black/10 px-2 py-1 text-xs text-zinc-400">p{item.importance}</span>
            <span className="rounded-full border border-white/10 bg-black/10 px-2 py-1 text-xs text-zinc-400">c{Math.round(item.confidence * 100)}%</span>
            <ProvenanceBadge provenance={item.provenance} />
          </div>
          <h3 className="mt-3 truncate text-sm font-semibold text-stone-100">{item.key}</h3>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button onClick={() => onEdit(item)} className="secondary-button h-9 px-3 text-xs"><Pencil size={14} /> Edit</button>
          <button onClick={() => onArchive(item)} className="secondary-button h-9 px-3 text-xs"><Archive size={14} /> Archive</button>
          <button onClick={() => onDelete(item)} className="secondary-button h-9 px-3 text-xs text-red-200"><Trash2 size={14} /> Delete</button>
        </div>
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-300">{item.content}</p>
      {item.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {item.tags.map((tag) => <span key={tag} className="rounded-full bg-white/[0.05] px-2 py-1 text-xs text-zinc-500">{tag}</span>)}
        </div>
      )}
      <div className="mt-3 text-xs text-zinc-600">{formatDate(item.updated_at)}</div>
    </article>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
