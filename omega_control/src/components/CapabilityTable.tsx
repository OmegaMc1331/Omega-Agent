import { CapabilityView } from './CapabilityDetails';
import { RiskBadge } from './RiskBadge';

export function CapabilityTable({
  items,
  selectedId,
  onSelect,
  onToggle,
}: {
  items: CapabilityView[];
  selectedId?: string;
  onSelect: (item: CapabilityView) => void;
  onToggle: (item: CapabilityView) => void;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.035]">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-white/10 text-xs uppercase text-zinc-500">
          <tr>
            <th className="px-3 py-3">Name</th>
            <th className="px-3 py-3">Type</th>
            <th className="px-3 py-3">Risk</th>
            <th className="px-3 py-3">Auth</th>
            <th className="px-3 py-3">Status</th>
            <th className="px-3 py-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className={`border-b border-white/5 ${selectedId === item.id ? 'bg-white/[0.06]' : 'hover:bg-white/[0.035]'}`}>
              <td className="max-w-72 px-3 py-3">
                <button onClick={() => onSelect(item)} className="block w-full text-left">
                  <span className="block truncate font-medium text-stone-100">{item.name}</span>
                  <span className="block truncate text-xs text-zinc-500">{item.id}</span>
                </button>
              </td>
              <td className="px-3 py-3 text-zinc-400">{item.type}</td>
              <td className="px-3 py-3"><RiskBadge risk={item.risk_level} /></td>
              <td className="px-3 py-3 text-zinc-400">{item.auth_status || 'none'}</td>
              <td className="px-3 py-3 text-zinc-400">{item.enabled ? 'enabled' : 'disabled'} / {item.available ? 'available' : 'unavailable'}</td>
              <td className="px-3 py-3 text-right">
                <button onClick={() => onToggle(item)} className="secondary-button h-8 px-3 text-xs">{item.enabled ? 'Disable' : 'Enable'}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
