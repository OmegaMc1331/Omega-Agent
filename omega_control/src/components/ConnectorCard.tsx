import { Plug } from 'lucide-react';
import { ConnectorAuthStatus } from './ConnectorAuthStatus';
import { ConnectorScopeEditor } from './ConnectorScopeEditor';
import { RiskBadge } from './RiskBadge';

export type ConnectorView = {
  id: string;
  type: string;
  name: string;
  description: string;
  enabled: boolean;
  trust_level: string;
  auth_type: string;
  auth_ref?: string | null;
  base_url?: string | null;
  scopes: string[];
  operations_count?: number;
  operations?: unknown[];
  risk_level: string;
  status: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
};

export function ConnectorCard({
  connector,
  selected,
  onSelect,
  onToggle,
}: {
  connector: ConnectorView;
  selected?: boolean;
  onSelect: (connector: ConnectorView) => void;
  onToggle: (connector: ConnectorView) => void;
}) {
  return (
    <article className={`rounded-2xl border p-4 ${selected ? 'border-blue-300/25 bg-blue-300/[0.06]' : 'border-white/10 bg-white/[0.035]'}`}>
      <div className="flex items-start justify-between gap-3">
        <button onClick={() => onSelect(connector)} className="min-w-0 flex-1 text-left">
          <div className="flex items-center gap-2">
            <Plug size={16} className="text-zinc-500" />
            <span className="truncate font-semibold text-stone-100">{connector.name}</span>
          </div>
          <div className="mt-1 truncate text-xs text-zinc-500">{connector.id}</div>
        </button>
        <button onClick={() => onToggle(connector)} className="secondary-button h-8 px-3 text-xs">
          {connector.enabled ? 'Disable' : 'Enable'}
        </button>
      </div>
      <p className="mt-3 line-clamp-2 min-h-10 text-sm text-zinc-400">{connector.description || 'No description.'}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-white/10 bg-white/[0.045] px-2 py-0.5 text-xs text-zinc-400">{connector.type}</span>
        <span className="rounded-full border border-white/10 bg-white/[0.045] px-2 py-0.5 text-xs text-zinc-400">{connector.trust_level}</span>
        <RiskBadge risk={connector.risk_level} />
        <ConnectorAuthStatus status={connector.status === 'missing_auth' ? 'missing' : connector.auth_type === 'none' ? 'none' : 'configured'} />
      </div>
      <div className="mt-3">
        <ConnectorScopeEditor scopes={connector.scopes} />
      </div>
      <div className="mt-3 flex justify-between text-xs text-zinc-500">
        <span>{connector.status}</span>
        <span>{connector.operations_count ?? connector.operations?.length ?? 0} operations</span>
      </div>
    </article>
  );
}
