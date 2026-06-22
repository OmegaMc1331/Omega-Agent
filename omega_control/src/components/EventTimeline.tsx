import { Activity } from 'lucide-react';

export type EventView = {
  id?: string;
  event_id?: string;
  version?: string;
  type?: string;
  session_id?: string | null;
  run_id?: string | null;
  step_id?: string | null;
  source?: string;
  level?: string;
  visibility?: string;
  payload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  timestamp?: string;
  created_at?: string;
};

export function EventTimeline({ events, onSelect }: { events: EventView[]; onSelect?: (event: EventView) => void }) {
  if (events.length === 0) return <div className="text-sm text-zinc-500">Aucun evenement.</div>;
  return (
    <div className="space-y-2">
      {events.map((event, index) => (
        <button
          key={event.id || event.event_id || `${event.type}-${index}`}
          className="relative w-full rounded-lg border border-white/10 bg-white/[0.035] p-3 text-left transition hover:border-white/20"
          onClick={() => onSelect?.(event)}
          type="button"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-medium text-stone-100"><Activity size={15} className="text-zinc-400" /> {event.type}</div>
            <div className="text-xs text-zinc-500">{formatDate(event.timestamp || event.created_at || '')}</div>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-zinc-500">
            {event.level && <span className="rounded-full border border-white/10 px-2 py-0.5">{event.level}</span>}
            {event.source && <span className="rounded-full border border-white/10 px-2 py-0.5">{event.source}</span>}
            {event.visibility && <span className="rounded-full border border-white/10 px-2 py-0.5">{event.visibility}</span>}
            {event.run_id && <span className="rounded-full border border-white/10 px-2 py-0.5">run {event.run_id}</span>}
          </div>
          <pre className="mt-2 max-h-32 overflow-auto rounded-lg border border-white/10 bg-black/20 p-2 text-[11px] text-zinc-500">{JSON.stringify(event.payload || {}, null, 2)}</pre>
        </button>
      ))}
    </div>
  );
}

function formatDate(value: string) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
