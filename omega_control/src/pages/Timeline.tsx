import { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { api } from '../api/client';
import { EventDetailDrawer } from '../components/EventDetailDrawer';
import { EventTimeline, type EventView } from '../components/EventTimeline';
import type { OmegaEvent } from '../ws/eventTypes';

export function TimelinePage() {
  const [events, setEvents] = useState<EventView[]>([]);
  const [selected, setSelected] = useState<OmegaEvent | null>(null);
  useEffect(() => {
    api<EventView[]>('/api/events/v2?limit=200').then(setEvents).catch(() => {
      api<EventView[]>('/api/timeline').then(setEvents).catch(() => setEvents([]));
    });
  }, []);
  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6 max-sm:p-4">
      <div>
        <div className="flex items-center gap-2 font-semibold text-stone-100"><Activity size={18} className="text-zinc-400" /> Timeline</div>
        <p className="mt-1 text-sm text-zinc-500">Evenements AG-UI recents, toutes sessions confondues.</p>
      </div>
      <EventTimeline events={events} onSelect={(event) => setSelected(event as OmegaEvent)} />
      <EventDetailDrawer event={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
