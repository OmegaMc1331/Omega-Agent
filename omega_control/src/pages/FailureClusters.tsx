import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { FailureClusterCard, type FailureClusterView } from '../components/FailureClusterCard';

export function FailureClustersPage() {
  const [clusters, setClusters] = useState<FailureClusterView[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      setClusters(await api<FailureClusterView[]>('/api/evals/failures'));
      setError('');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  async function updateStatus(id: string, status: string) {
    const updated = await api<FailureClusterView>(`/api/evals/failures/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });
    setClusters((current) => current.map((item) => item.id === updated.id ? updated : item));
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-lg font-semibold text-stone-100">Failure Clusters</div>
          <p className="mt-1 text-sm text-zinc-500">Erreurs regroupées, exemples de runs et suggestions de correction.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
      <div className="grid gap-3">
        {clusters.map((cluster) => <FailureClusterCard key={cluster.id} cluster={cluster} onStatus={updateStatus} />)}
        {clusters.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-5 text-sm text-zinc-500">Aucun cluster ouvert.</div>}
      </div>
    </div>
  );
}
