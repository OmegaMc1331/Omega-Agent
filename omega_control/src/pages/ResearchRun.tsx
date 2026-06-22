import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Download, Network, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { ClaimCard } from '../components/ClaimCard';
import { ConfidenceBadge } from '../components/ConfidenceBadge';
import { ResearchPlanCard } from '../components/ResearchPlanCard';
import { ResearchReportViewer } from '../components/ResearchReportViewer';
import { RunStatusBadge } from '../components/RunStatusBadge';
import { SourceCard } from '../components/SourceCard';
import type { ResearchRunDetail } from '../types/research';

export function ResearchRunPage({
  researchRunId,
  onBack,
  onGraph,
}: {
  researchRunId: string;
  onBack: () => void;
  onGraph: () => void;
}) {
  const [detail, setDetail] = useState<ResearchRunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  async function load() {
    if (!researchRunId) return;
    setLoading(true);
    try {
      setDetail(await api<ResearchRunDetail>(`/api/research/${researchRunId}`));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [researchRunId]);

  const evidenceByClaim = useMemo(() => {
    const map = new Map<string, NonNullable<ResearchRunDetail['evidence']>>();
    for (const item of detail?.evidence || []) map.set(item.claim_id, [...(map.get(item.claim_id) || []), item]);
    return map;
  }, [detail]);

  async function exportRun(format: 'markdown' | 'json') {
    const result = await api<{ path: string }>(`/api/research/${researchRunId}/export`, { method: 'POST', body: JSON.stringify({ format }) });
    setMessage(`Export créé: ${result.path}`);
  }

  if (!researchRunId) return <div className="p-6 text-sm text-zinc-500">Sélectionne un research run depuis la page Research.</div>;
  if (!detail) return <div className="p-6 text-sm text-zinc-500">{loading ? 'Chargement…' : 'Research run introuvable.'}</div>;

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-200"><ArrowLeft size={13} /> Research</button>
          <div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-semibold text-stone-100">{detail.title}</h2><RunStatusBadge status={detail.status} /><ConfidenceBadge confidence={detail.graph.confidence_summary.average} /></div>
          <p className="mt-2 max-w-3xl text-sm text-zinc-500">{detail.question}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={load} className="secondary-button"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh</button>
          <button onClick={onGraph} className="secondary-button"><Network size={15} /> Evidence graph</button>
          <button onClick={() => exportRun('markdown')} className="secondary-button"><Download size={15} /> Markdown</button>
          <button onClick={() => exportRun('json')} className="secondary-button"><Download size={15} /> JSON</button>
        </div>
      </div>
      {message && <div className="rounded-2xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">{message}</div>}
      <ResearchPlanCard plan={detail.plan} />
      <section>
        <div className="mb-3 text-sm font-semibold text-stone-100">Sources ({detail.sources.length})</div>
        <div className="grid gap-3 md:grid-cols-2">{detail.sources.map((source) => <SourceCard key={source.id} source={source} />)}</div>
      </section>
      <section>
        <div className="mb-3 text-sm font-semibold text-stone-100">Claims ({detail.claims.length})</div>
        <div className="space-y-3">{detail.claims.map((claim) => <ClaimCard key={claim.id} claim={claim} evidence={evidenceByClaim.get(claim.id) || []} sources={detail.sources} />)}</div>
      </section>
      <ResearchReportViewer report={detail.report_markdown} />
    </div>
  );
}
