import { useEffect, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { api } from '../api/client';
import { SnapshotCard, type SnapshotView } from '../components/SnapshotCard';

export function RollbackPage() {
  const [snapshots, setSnapshots] = useState<SnapshotView[]>([]);
  async function refresh() {
    setSnapshots(await api<SnapshotView[]>('/api/snapshots'));
  }
  useEffect(() => {
    refresh().catch(() => undefined);
  }, []);
  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6 max-sm:p-4">
      <div>
        <div className="flex items-center gap-2 font-semibold text-stone-100"><RotateCcw size={18} className="text-zinc-400" /> Rollback</div>
        <p className="mt-1 text-sm text-zinc-500">Snapshots de fichiers crees avant les actions modificatrices.</p>
      </div>
      <div className="rounded-2xl border border-amber-400/20 bg-amber-400/10 p-3 text-sm text-amber-100">Rollback restaure uniquement des chemins dans le workspace Omega. Les chemins hors workspace sont refuses par le backend.</div>
      <div className="grid gap-3">
        {snapshots.map((snapshot) => <SnapshotCard key={snapshot.id} snapshot={snapshot} onChanged={refresh} />)}
        {snapshots.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-6 text-sm text-zinc-500">Aucun snapshot.</div>}
      </div>
    </div>
  );
}
