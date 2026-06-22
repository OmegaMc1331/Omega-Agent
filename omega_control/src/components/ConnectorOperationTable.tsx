import { RiskBadge } from './RiskBadge';

export type ConnectorOperationView = {
  id: string;
  connector_id: string;
  name: string;
  description: string;
  method?: string | null;
  path?: string | null;
  risk_level: string;
  requires_approval_default: boolean;
  action_category: string;
  enabled: boolean;
};

export function ConnectorOperationTable({ operations }: { operations: ConnectorOperationView[] }) {
  if (operations.length === 0) {
    return <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-4 text-sm text-zinc-500">No operations.</div>;
  }
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.035]">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-white/10 text-xs uppercase text-zinc-500">
          <tr>
            <th className="px-3 py-3">Operation</th>
            <th className="px-3 py-3">Route</th>
            <th className="px-3 py-3">Category</th>
            <th className="px-3 py-3">Risk</th>
            <th className="px-3 py-3">Approval</th>
          </tr>
        </thead>
        <tbody>
          {operations.map((operation) => (
            <tr key={`${operation.connector_id}:${operation.id}`} className="border-b border-white/5">
              <td className="max-w-72 px-3 py-3">
                <span className="block truncate font-medium text-stone-100">{operation.name}</span>
                <span className="block truncate text-xs text-zinc-500">{operation.id}</span>
              </td>
              <td className="px-3 py-3 text-xs text-zinc-400">{operation.method || '-'} {operation.path || ''}</td>
              <td className="px-3 py-3 text-zinc-400">{operation.action_category}</td>
              <td className="px-3 py-3"><RiskBadge risk={operation.risk_level} /></td>
              <td className="px-3 py-3 text-zinc-400">{operation.requires_approval_default ? 'required' : 'direct'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
