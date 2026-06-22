import { X } from 'lucide-react';
import type { OmegaEvent } from '../ws/eventTypes';

export function EventDetailDrawer({ event, onClose }: { event: OmegaEvent | null; onClose: () => void }) {
  if (!event) return null;
  return (
    <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-xl border-l border-white/10 bg-zinc-950 p-5 shadow-2xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-stone-100">{event.type}</div>
          <div className="mt-1 text-xs text-zinc-500">{event.id}</div>
        </div>
        <button className="rounded-lg border border-white/10 p-2 text-zinc-400 hover:text-stone-100" onClick={onClose} aria-label="Close event detail">
          <X size={16} />
        </button>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-zinc-400">
        <Info label="Version" value={event.version} />
        <Info label="Level" value={event.level} />
        <Info label="Source" value={event.source} />
        <Info label="Visibility" value={event.visibility} />
        <Info label="Session" value={event.session_id || '-'} />
        <Info label="Run" value={event.run_id || '-'} />
      </div>
      <pre className="mt-4 max-h-[70vh] overflow-auto rounded-lg border border-white/10 bg-black/25 p-3 text-xs text-zinc-300">{JSON.stringify({ payload: event.payload, metadata: event.metadata }, null, 2)}</pre>
    </aside>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-2">
      <div className="text-zinc-500">{label}</div>
      <div className="mt-1 truncate text-stone-100">{value}</div>
    </div>
  );
}
