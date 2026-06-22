import { Save } from 'lucide-react';

export type CheckpointView = {
  id: string;
  label: string;
  created_at: string;
};

export function CheckpointCard({ checkpoint }: { checkpoint: CheckpointView }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-3">
      <div className="flex items-center gap-2 text-sm font-medium text-stone-100"><Save size={15} className="text-zinc-400" /> {checkpoint.label}</div>
      <div className="mt-1 text-xs text-zinc-500">{formatDate(checkpoint.created_at)}</div>
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
