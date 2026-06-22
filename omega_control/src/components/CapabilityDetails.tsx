import { ScopeBadge } from './ScopeBadge';
import { RiskBadge } from './RiskBadge';

export type CapabilityView = {
  id: string;
  type: string;
  name: string;
  description: string;
  enabled: boolean;
  available: boolean;
  risk_level: string;
  scopes: string[];
  requires_auth: boolean;
  auth_status: string;
  requires_approval_default: boolean;
  owner: string;
  source: string;
  version: string;
  tags: string[];
  metadata?: Record<string, unknown>;
  updated_at: string;
};

export function CapabilityDetails({ item }: { item: CapabilityView | null }) {
  if (!item) {
    return (
      <aside className="rounded-2xl border border-white/10 bg-white/[0.035] p-4 text-sm text-zinc-500">
        Sélectionne une capability pour voir ses scopes, son statut d’auth et ses métadonnées redacted.
      </aside>
    );
  }
  return (
    <aside className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-semibold text-stone-100">{item.name}</div>
          <div className="mt-1 truncate text-xs text-zinc-500">{item.id}</div>
        </div>
        <RiskBadge risk={item.risk_level} />
      </div>
      <p className="text-sm leading-6 text-zinc-400">{item.description || item.type}</p>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <Detail label="Enabled" value={String(item.enabled)} />
        <Detail label="Available" value={String(item.available)} />
        <Detail label="Auth" value={item.auth_status || 'none'} />
        <Detail label="Owner" value={item.owner || 'builtin'} />
        <Detail label="Approval" value={String(item.requires_approval_default)} />
        <Detail label="Version" value={item.version || 'builtin'} />
      </div>
      <div className="flex flex-wrap gap-2">
        {item.scopes.map((scope) => <ScopeBadge key={scope} scope={scope} />)}
      </div>
      {item.tags.length > 0 && <div className="text-xs text-zinc-500">Tags: {item.tags.join(', ')}</div>}
      <pre className="max-h-56 overflow-auto rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-400">{JSON.stringify(item.metadata || {}, null, 2)}</pre>
    </aside>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/10 px-3 py-2">
      <div className="text-[11px] text-zinc-600">{label}</div>
      <div className="truncate text-zinc-300">{value}</div>
    </div>
  );
}
