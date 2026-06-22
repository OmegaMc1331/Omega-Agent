import { RotateCcw } from 'lucide-react';
import { api } from '../api/client';

export function RollbackButton({ snapshotId, disabled, onDone }: { snapshotId: string; disabled?: boolean; onDone?: () => void }) {
  async function rollback() {
    const ok = window.confirm('Restaurer ce snapshot ?');
    if (!ok) return;
    await api(`/api/snapshots/${encodeURIComponent(snapshotId)}/rollback`, { method: 'POST', body: JSON.stringify({}) });
    onDone?.();
  }
  return (
    <button onClick={rollback} disabled={disabled} className="inline-flex h-9 items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.045] px-3 text-xs font-medium text-zinc-200 transition hover:border-white/15 hover:bg-white/[0.075] disabled:cursor-not-allowed disabled:opacity-50">
      <RotateCcw size={14} /> Rollback
    </button>
  );
}
