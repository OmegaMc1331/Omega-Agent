import { Quote } from 'lucide-react';
import { ConfidenceBadge } from './ConfidenceBadge';
import type { ResearchClaimView, ResearchEvidenceView, ResearchSourceView } from '../types/research';

export function ClaimCard({
  claim,
  evidence,
  sources,
}: {
  claim: ResearchClaimView;
  evidence: ResearchEvidenceView[];
  sources: ResearchSourceView[];
}) {
  const sourceById = new Map(sources.map((source) => [source.id, source]));
  return (
    <article className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm leading-6 text-stone-200">{claim.claim_text}</p>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-white/10 px-2 py-1 text-[10px] uppercase tracking-wide text-zinc-400">{claim.status}</span>
          <ConfidenceBadge confidence={claim.confidence} status={claim.status} />
        </div>
      </div>
      <div className="mt-3 space-y-2">
        {evidence.map((item) => (
          <div key={item.id} className="rounded-xl border border-white/8 bg-black/10 p-3 text-xs text-zinc-500">
            <div className="mb-1 flex items-center gap-2 text-zinc-400"><Quote size={13} /> {sourceById.get(item.source_id)?.title || item.source_id} · {item.supports === true ? 'supports' : item.supports === false ? 'contradicts' : 'mentions'}</div>
            <div className="leading-5">{item.quote || 'Citation directe indisponible.'}</div>
          </div>
        ))}
        {evidence.length === 0 && <div className="text-xs text-red-200">Preuve insuffisante : aucune citation liée.</div>}
      </div>
    </article>
  );
}
