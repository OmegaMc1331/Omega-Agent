import { FileText, Link2 } from 'lucide-react';
import type { ResearchSourceView } from '../types/research';

export function SourceCard({ source }: { source: ResearchSourceView }) {
  const untrusted = source.trust_level === 'untrusted' || source.trust_level === 'external';
  return (
    <article className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium text-stone-100"><FileText size={15} className="text-zinc-500" /><span className="truncate">{source.title}</span></div>
          <div className="mt-1 flex items-center gap-1 text-xs text-zinc-600"><Link2 size={12} /> {source.locator || source.uri || 'sans locator'}</div>
        </div>
        <span className={`rounded-full border px-2 py-1 text-[10px] ${untrusted ? 'border-amber-400/20 bg-amber-400/10 text-amber-100' : 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100'}`}>{source.trust_level}</span>
      </div>
      {source.content_excerpt && <p className="mt-3 line-clamp-4 whitespace-pre-wrap text-xs leading-5 text-zinc-500">{source.content_excerpt}</p>}
    </article>
  );
}
