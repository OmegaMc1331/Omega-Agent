import { CapabilityView } from './CapabilityDetails';
import { RiskBadge } from './RiskBadge';

export function CapabilityCard({ item, onSelect }: { item: CapabilityView; onSelect: (item: CapabilityView) => void }) {
  return (
    <button onClick={() => onSelect(item)} className="rounded-2xl border border-white/10 bg-white/[0.035] p-4 text-left transition hover:border-white/15 hover:bg-white/[0.055]">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-stone-100">{item.name}</div>
          <div className="mt-1 truncate text-xs text-zinc-500">{item.id}</div>
        </div>
        <RiskBadge risk={item.risk_level} />
      </div>
      <p className="line-clamp-3 text-sm leading-6 text-zinc-500">{item.description || item.type}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-zinc-400">
        <span>{item.type}</span>
        <span>{item.enabled ? 'enabled' : 'disabled'}</span>
        <span>{item.auth_status || 'none'}</span>
      </div>
    </button>
  );
}
