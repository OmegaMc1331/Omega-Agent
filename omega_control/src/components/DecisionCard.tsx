import { Archive } from 'lucide-react';
import { ProvenanceBadge } from './ProvenanceBadge';

export type DecisionView = {
  id: string;
  project_id?: string | null;
  session_id?: string | null;
  run_id?: string | null;
  title: string;
  content: string;
  reason: string;
  alternatives: string[];
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  provenance?: Array<{ source_type?: string; source_id?: string | null; source_label?: string | null }>;
};

export function DecisionCard({ item, onArchive }: { item: DecisionView; onArchive: (item: DecisionView) => void }) {
  return (
    <article className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-white/10 bg-black/10 px-2 py-1 text-xs text-zinc-400">{item.status}</span>
            <ProvenanceBadge provenance={item.provenance} />
          </div>
          <h3 className="mt-3 text-sm font-semibold text-stone-100">{item.title}</h3>
        </div>
        {item.status === 'active' && (
          <button onClick={() => onArchive(item)} className="secondary-button h-9 px-3 text-xs"><Archive size={14} /> Archive</button>
        )}
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-300">{item.content}</p>
      {item.reason && <p className="mt-3 text-sm text-zinc-500">Reason: {item.reason}</p>}
      {item.alternatives.length > 0 && <p className="mt-2 text-xs text-zinc-600">Alternatives: {item.alternatives.join(', ')}</p>}
      <div className="mt-3 text-xs text-zinc-600">{formatDate(item.updated_at)}</div>
    </article>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
