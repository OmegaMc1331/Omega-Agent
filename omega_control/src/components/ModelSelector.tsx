import { useMemo, useState } from 'react';
import { Brain, Check, ChevronDown, Search, Star } from 'lucide-react';
import type { ModelView } from './ModelCard';
import type { ProviderView } from './ProviderCard';
import { ModelCapabilityBadges } from './ModelCapabilityBadges';

export type CurrentModelView = {
  primary_model_ref: string;
  fallback_model_ref?: string | null;
  provider_id: string;
  model_name: string;
  source_scope: string;
  source_scope_id?: string | null;
  thinking?: {
    supported: boolean;
    levels: string[];
    configured_level: string;
    current_level: string;
    source: string;
    mode: string;
    reason?: string;
    limitations?: string[];
    valid?: boolean;
    error?: string;
  };
};

export function ModelSelector({
  current,
  models,
  providers = [],
  recentModelRefs = [],
  onSelect,
  onSetDefault,
}: {
  current: CurrentModelView | null;
  models: ModelView[];
  providers?: ProviderView[];
  recentModelRefs?: string[];
  onSelect: (modelRef: string) => void;
  onSetDefault?: (modelRef: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const value = current?.primary_model_ref || 'codex/gpt-5.5';
  const currentModel = models.find((model) => model.model_ref === value);
  const providerById = useMemo(() => new Map(providers.map((provider) => [provider.id, provider])), [providers]);
  const filteredModels = useMemo(() => {
    const lowered = query.trim().toLowerCase();
    return models.filter((model) => !lowered || `${model.model_ref} ${model.display_name} ${model.provider_id}`.toLowerCase().includes(lowered));
  }, [models, query]);
  const recentModels = recentModelRefs.map((ref) => models.find((model) => model.model_ref === ref)).filter(Boolean) as ModelView[];

  function applySession(modelRef: string) {
    onSelect(modelRef);
    setOpen(false);
  }

  function applyDefault(modelRef: string) {
    onSetDefault?.(modelRef);
    setOpen(false);
  }

  return (
    <div className="relative">
      <button onClick={() => setOpen((currentOpen) => !currentOpen)} className="inline-flex h-9 items-center gap-2 rounded-full border border-white/10 bg-white/[0.045] px-3 text-xs text-zinc-200 transition hover:bg-white/[0.07] focus:outline-none focus:ring-2 focus:ring-blue-300/30">
        <Brain size={15} className="text-zinc-500" />
        <span className="max-w-[220px] truncate">{formatModelButton(value)}</span>
        <ChevronDown size={14} className={`text-zinc-600 transition ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-[420px] max-w-[calc(100vw-2rem)] rounded-[24px] border border-white/10 bg-[#16171b]/98 p-3 shadow-2xl shadow-black/30 ring-1 ring-white/[0.03] backdrop-blur-xl">
          <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-3">
            <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-600">Modèle actuel</div>
            <div className="mt-1 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-stone-100">{currentModel?.display_name || value}</div>
                <div className="truncate text-xs text-zinc-500">{value} · {current?.source_scope || 'global'}</div>
              </div>
              <Check size={16} className="text-emerald-200" />
            </div>
          </div>

          <div className="mt-3 flex items-center gap-2 rounded-2xl border border-white/10 bg-black/15 px-3 py-2">
            <Search size={15} className="text-zinc-600" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} className="min-w-0 flex-1 bg-transparent text-sm text-stone-100 outline-none placeholder:text-zinc-600" placeholder="Rechercher un modèle" />
          </div>

          {recentModels.length > 0 && (
            <div className="mt-3">
              <div className="mb-2 flex items-center gap-2 text-xs text-zinc-500"><Star size={13} /> Récents</div>
              <div className="grid gap-1.5">
                {recentModels.slice(0, 3).map((model) => (
                  <ModelRow key={`recent-${model.model_ref}`} model={model} currentRef={value} provider={providerById.get(model.provider_id)} onSelect={applySession} onDefault={applyDefault} />
                ))}
              </div>
            </div>
          )}

          <div className="mt-3">
            <div className="mb-2 text-xs text-zinc-500">Providers disponibles</div>
            <div className="flex flex-wrap gap-1.5">
              {providers.map((provider) => (
                <span key={provider.id} className={`rounded-full border px-2 py-1 text-[11px] ${provider.enabled ? 'border-white/10 bg-white/[0.035] text-zinc-400' : 'border-zinc-700 bg-black/10 text-zinc-600'}`}>
                  {provider.id} · {provider.status}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-3 max-h-80 overflow-auto pr-1">
            <div className="grid gap-1.5">
              {filteredModels.map((model) => (
                <ModelRow key={model.model_ref} model={model} currentRef={value} provider={providerById.get(model.provider_id)} onSelect={applySession} onDefault={applyDefault} />
              ))}
              {filteredModels.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-center text-sm text-zinc-500">Aucun modèle trouvé.</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ModelRow({ model, currentRef, provider, onSelect, onDefault }: { model: ModelView; currentRef: string; provider?: ProviderView; onSelect: (modelRef: string) => void; onDefault: (modelRef: string) => void }) {
  const reason = disabledReason(model, provider);
  const disabled = Boolean(reason);
  return (
    <div className={`rounded-2xl border p-3 ${model.model_ref === currentRef ? 'border-blue-300/20 bg-blue-500/10' : 'border-white/10 bg-white/[0.025]'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className={`truncate text-sm font-medium ${disabled ? 'text-zinc-500' : 'text-stone-100'}`}>{model.display_name}</div>
          <div className="truncate text-xs text-zinc-600">{model.model_ref}</div>
        </div>
        {model.model_ref === currentRef && <Check size={15} className="shrink-0 text-blue-200" />}
      </div>
      <div className="mt-2">
        <ModelCapabilityBadges item={model} />
      </div>
      {reason && <div className="mt-2 text-xs text-amber-200/80">{reason}</div>}
      <div className="mt-3 flex flex-wrap gap-2">
        <button disabled={disabled} onClick={() => onSelect(model.model_ref)} className="secondary-button h-8 text-xs disabled:cursor-not-allowed disabled:opacity-40">Appliquer à cette session</button>
        <button disabled={disabled} onClick={() => onDefault(model.model_ref)} className="secondary-button h-8 text-xs disabled:cursor-not-allowed disabled:opacity-40">Définir par défaut</button>
      </div>
    </div>
  );
}

export function disabledReason(model: ModelView, provider?: ProviderView) {
  if (provider && !provider.enabled) return 'Provider désactivé';
  if (provider?.auth_type === 'env_api_key' && provider.status === 'missing') return 'cle API manquante';
  if (provider?.supports_local && provider.status === 'missing') return 'Service local inaccessible';
  if (!model.available) return 'Modèle indisponible';
  return '';
}

function formatModelButton(modelRef: string) {
  const [provider, ...rest] = modelRef.split('/');
  return `${provider || 'codex'} / ${rest.join('/') || 'gpt-5.5'}`;
}
