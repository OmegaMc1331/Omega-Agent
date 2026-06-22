import { Check, ExternalLink, X } from 'lucide-react';
import { ConfidenceBadge } from './ConfidenceBadge';
import { SkillPreview } from './SkillPreview';
import type { SkillCandidateView } from '../types/skills';

export function SkillCandidateCard({
  candidate,
  busy,
  onAccept,
  onReject,
}: {
  candidate: SkillCandidateView;
  busy: boolean;
  onAccept: () => void;
  onReject: () => void;
}) {
  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-stone-100">{candidate.title}</div>
          <p className="mt-1 text-sm text-zinc-500">{candidate.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <ConfidenceBadge confidence={candidate.confidence} status={candidate.confidence < 0.7 ? 'weak' : 'supported'} />
          <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-zinc-500">{candidate.status}</span>
        </div>
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
        <SkillPreview proposed={candidate.proposed_skill} />
        <div className="space-y-3 rounded-2xl border border-white/10 p-4 text-xs text-zinc-500">
          <div className="font-medium text-zinc-300">Provenance</div>
          {candidate.source_run_ids.map((id) => <div key={id} className="flex items-center gap-1"><ExternalLink size={12} /> run {id.slice(0, 12)}</div>)}
          {candidate.source_workflow_ids.map((id) => <div key={id} className="flex items-center gap-1"><ExternalLink size={12} /> workflow {id.slice(0, 12)}</div>)}
          <div className="rounded-xl border border-amber-400/20 bg-amber-400/10 p-3 text-amber-100">
            Secrets are redacted. External/imported content remains untrusted and disabled by default.
          </div>
        </div>
      </div>
      {candidate.status === 'pending' && (
        <div className="mt-4 flex justify-end gap-2">
          <button disabled={busy} onClick={onReject} className="secondary-button"><X size={15} /> Reject</button>
          <button disabled={busy} onClick={onAccept} className="primary-button"><Check size={15} /> Create draft</button>
        </div>
      )}
    </article>
  );
}
