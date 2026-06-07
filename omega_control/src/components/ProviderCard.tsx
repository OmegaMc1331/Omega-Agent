import { CheckCircle2, KeyRound, XCircle } from 'lucide-react';
import { ModelCapabilityBadges } from './ModelCapabilityBadges';

export type ProviderView = {
  id: string;
  name: string;
  description: string;
  auth_type: string;
  status: string;
  enabled: boolean;
  supports_streaming?: boolean;
  supports_tools?: boolean;
  supports_vision?: boolean;
  supports_json?: boolean;
  supports_reasoning?: boolean;
  supports_local?: boolean;
};

export function ProviderCard({ provider, onTest, onToggle }: { provider: ProviderView; onTest: (id: string) => void; onToggle: (id: string, enabled: boolean) => void }) {
  const configured = provider.status === 'configured' || provider.auth_type === 'none';
  const statusLabel = provider.auth_type === 'codex_oauth' && provider.status === 'configured' ? 'connecte via OAuth ChatGPT' : provider.status;
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100">
            <KeyRound size={16} className="text-zinc-500" /> {provider.name}
          </div>
          <p className="mt-1 text-sm leading-6 text-zinc-500">{provider.description}</p>
        </div>
        <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs ${configured ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100' : 'border-amber-400/20 bg-amber-400/10 text-amber-100'}`}>
          {configured ? <CheckCircle2 size={13} /> : <XCircle size={13} />} {statusLabel}
        </span>
      </div>
      <div className="mt-3">
        <ModelCapabilityBadges item={provider} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={() => onTest(provider.id)} className="secondary-button h-9">Tester auth</button>
        <button onClick={() => onToggle(provider.id, !provider.enabled)} className="secondary-button h-9">{provider.enabled ? 'Désactiver' : 'Activer'}</button>
      </div>
    </div>
  );
}
