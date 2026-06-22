import { Circle } from 'lucide-react';
import type { EventConnectionStatus } from '../ws/eventTypes';

export function ConnectionStatus({ status }: { status: EventConnectionStatus }) {
  const tone = status === 'connected' ? 'text-emerald-300' : status === 'closed' ? 'text-zinc-500' : 'text-amber-300';
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.035] px-3 py-1 text-xs text-zinc-400">
      <Circle size={9} className={tone} fill="currentColor" />
      {status}
    </div>
  );
}
