import { FileClock } from 'lucide-react';
import { RollbackButton } from './RollbackButton';

export type SnapshotView = {
  id: string;
  run_id: string;
  action_id?: string | null;
  workspace_path: string;
  existed_before: boolean;
  created_at: string;
  restored_at?: string | null;
  metadata?: Record<string, unknown>;
};

export function SnapshotCard({ snapshot, onChanged }: { snapshot: SnapshotView; onChanged?: () => void }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium text-stone-100"><FileClock size={15} className="text-zinc-400" /> <span className="truncate">{snapshot.workspace_path}</span></div>
          <div className="mt-1 text-xs text-zinc-500">{formatDate(snapshot.created_at)} · existed_before={String(snapshot.existed_before)}</div>
        </div>
        <RollbackButton snapshotId={snapshot.id} disabled={Boolean(snapshot.restored_at)} onDone={onChanged} />
      </div>
      {snapshot.restored_at && <div className="mt-2 text-xs text-emerald-200">Restored {formatDate(snapshot.restored_at)}</div>}
      {Boolean(snapshot.metadata?.too_large) && <div className="mt-2 text-xs text-amber-100">Snapshot trop volumineux, rollback partiel indisponible.</div>}
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
