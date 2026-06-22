import { useEffect, useState } from 'react';
import { Boxes, RefreshCw, Search } from 'lucide-react';
import { api } from '../api/client';
import { RepoSummaryCard, type RepoSummaryView } from '../components/RepoSummaryCard';

export function RepoInsightsPage() {
  const [repo, setRepo] = useState<RepoSummaryView | null>(null);
  const [loading, setLoading] = useState(false);

  async function load(scan = false) {
    setLoading(true);
    try {
      setRepo(await api<RepoSummaryView>(scan ? '/api/code/scan' : '/api/code/repo', scan ? { method: 'POST', body: '{}' } : undefined));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Boxes size={18} className="text-zinc-400" /> Repo Insights</div>
          <p className="mt-1 text-sm text-zinc-500">Detection stack, scripts, entrypoints et fichiers de configuration.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => load(true)} className="secondary-button"><Search size={16} /> Scan</button>
          <button onClick={() => load(false)} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
        </div>
      </div>
      <RepoSummaryCard repo={repo} />
    </div>
  );
}
