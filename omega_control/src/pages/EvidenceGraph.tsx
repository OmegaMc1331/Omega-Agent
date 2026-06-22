import { useEffect, useState } from 'react';
import { ArrowLeft, Network, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { EvidenceGraphView } from '../components/EvidenceGraphView';
import type { EvidenceGraphViewModel } from '../types/research';

export function EvidenceGraphPage({ researchRunId, onBack }: { researchRunId: string; onBack: () => void }) {
  const [graph, setGraph] = useState<EvidenceGraphViewModel | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!researchRunId) return;
    setLoading(true);
    try {
      setGraph(await api<EvidenceGraphViewModel>(`/api/research/${researchRunId}/graph`));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [researchRunId]);

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-200"><ArrowLeft size={13} /> Research run</button>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Network size={18} className="text-blue-200" /> Evidence Graph</div>
          <p className="mt-1 text-sm text-zinc-500">Sources, claims et relations supports / contradicts / mentions.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>
      {graph ? <EvidenceGraphView graph={graph} /> : <div className="rounded-2xl border border-dashed border-white/10 p-8 text-sm text-zinc-500">{researchRunId ? 'Chargement du graphe…' : 'Aucun research run sélectionné.'}</div>}
    </div>
  );
}
