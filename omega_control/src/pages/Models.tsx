import { useMemo, useState, type ElementType } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Filter, RefreshCw, Search, Settings, Zap } from 'lucide-react';
import type { ModelView } from '../components/ModelCard';
import { ModelSelector, type CurrentModelView, disabledReason } from '../components/ModelSelector';
import { ProviderCard, type ProviderView } from '../components/ProviderCard';

export type ModelPreferenceView = {
  id: string;
  scope: string;
  scope_id?: string | null;
  primary_model_ref: string;
  fallback_model_ref?: string | null;
  updated_at: string;
};

export type ModelUsageView = {
  id: string;
  session_id?: string | null;
  provider_id: string;
  model_ref: string;
  started_at: string;
  completed_at?: string | null;
  status: string;
  latency_ms?: number | null;
  error?: string | null;
};

export type ModelEventView = {
  id?: string;
  type?: string;
  payload?: Record<string, unknown>;
  created_at?: string;
};

export type ModelProjectOption = { id: string; name: string };
export type ModelAgentOption = { id: string; name: string };

const tabs = ['Overview', 'Providers', 'Catalog', 'Preferences', 'Usage'] as const;
type ModelsTab = typeof tabs[number];

export function ModelsPage({
  providers,
  models,
  preferences,
  usage,
  modelEvents,
  projects,
  agents,
  current,
  loading,
  onSelectSession,
  onSetDefault,
  onSetPreference,
  onRefresh,
  onTestProvider,
  onToggleProvider,
}: {
  providers: ProviderView[];
  models: ModelView[];
  preferences: ModelPreferenceView[];
  usage: ModelUsageView[];
  modelEvents: ModelEventView[];
  projects: ModelProjectOption[];
  agents: ModelAgentOption[];
  current: CurrentModelView | null;
  loading: boolean;
  onSelectSession: (modelRef: string) => void;
  onSetDefault: (modelRef: string) => void;
  onSetPreference: (scope: string, scopeId: string | null, modelRef: string, fallbackModelRef?: string | null) => void;
  onRefresh: () => void;
  onTestProvider: (providerId: string) => void;
  onToggleProvider: (providerId: string, enabled: boolean) => void;
}) {
  const [tab, setTab] = useState<ModelsTab>('Overview');
  const [query, setQuery] = useState('');
  const [providerFilter, setProviderFilter] = useState('all');
  const [capabilityFilter, setCapabilityFilter] = useState('all');
  const [localFilter, setLocalFilter] = useState('all');
  const globalPreference = preferences.find((pref) => pref.scope === 'global');
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [fallbackDraft, setFallbackDraft] = useState(globalPreference?.fallback_model_ref || '');
  const providerById = useMemo(() => new Map(providers.map((provider) => [provider.id, provider])), [providers]);
  const filteredModels = models.filter((model) => {
    const lowered = query.trim().toLowerCase();
    if (lowered && !`${model.model_ref} ${model.display_name} ${model.provider_id}`.toLowerCase().includes(lowered)) return false;
    if (providerFilter !== 'all' && model.provider_id !== providerFilter) return false;
    if (capabilityFilter !== 'all' && !hasCapability(model, capabilityFilter)) return false;
    if (localFilter === 'local' && !model.supports_local) return false;
    if (localFilter === 'cloud' && model.supports_local) return false;
    return true;
  });

  if (loading) {
    return <div className="p-6"><div className="h-32 animate-pulse rounded-3xl border border-white/10 bg-white/[0.035]" /></div>;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-stone-100">Models</h2>
          <p className="mt-1 text-sm text-zinc-500">Providers, catalogue, préférences et usage modèle.</p>
        </div>
        <button onClick={onRefresh} className="secondary-button h-9"><RefreshCw size={16} /> Refresh catalog</button>
      </div>

      <div className="flex gap-1 rounded-2xl border border-white/10 bg-white/[0.035] p-1">
        {tabs.map((item) => (
          <button key={item} onClick={() => setTab(item)} className={`h-9 rounded-xl px-3 text-sm transition ${tab === item ? 'bg-white/[0.09] text-stone-100' : 'text-zinc-500 hover:bg-white/[0.045] hover:text-zinc-300'}`}>
            {item}
          </button>
        ))}
      </div>

      {tab === 'Overview' && (
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-4 flex items-center gap-2 font-semibold text-stone-100"><Zap size={18} className="text-zinc-500" /> Modèle actuel</div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Metric label="Défaut global" value={globalPreference?.primary_model_ref || 'codex/gpt-5.5'} />
              <Metric label="Fallback" value={globalPreference?.fallback_model_ref || 'Aucun fallback'} />
              <Metric label="Session courante" value={current?.primary_model_ref || 'codex/gpt-5.5'} />
              <Metric label="Source" value={current?.source_scope || 'global'} />
            </div>
            <div className="mt-5">
              <ModelSelector current={current} models={models} providers={providers} onSelect={onSelectSession} onSetDefault={onSetDefault} />
            </div>
          </section>
          <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-4 flex items-center gap-2 font-semibold text-stone-100"><Activity size={18} className="text-zinc-500" /> Auth providers</div>
            <div className="grid gap-2">
              {providers.map((provider) => (
                <div key={provider.id} className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-black/10 px-3 py-2 text-sm">
                  <span className="text-zinc-300">{provider.name}</span>
                  <StatusBadge status={provider.auth_type === 'none' ? 'configured' : provider.status} />
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {tab === 'Providers' && (
        <section className="grid gap-3 lg:grid-cols-2">
          {providers.map((provider) => <ProviderCard key={provider.id} provider={provider} onTest={onTestProvider} onToggle={onToggleProvider} />)}
        </section>
      )}

      {tab === 'Catalog' && (
        <section className="space-y-3">
          <div className="grid gap-2 rounded-3xl border border-white/10 bg-white/[0.035] p-3 lg:grid-cols-[1fr_180px_180px_160px]">
            <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/10 px-3 py-2">
              <Search size={15} className="text-zinc-600" />
              <input value={query} onChange={(event) => setQuery(event.target.value)} className="min-w-0 flex-1 bg-transparent text-sm text-stone-100 outline-none placeholder:text-zinc-600" placeholder="Rechercher dans le catalogue" />
            </div>
            <FilterSelect value={providerFilter} onChange={setProviderFilter} options={['all', ...providers.map((provider) => provider.id)]} />
            <FilterSelect value={capabilityFilter} onChange={setCapabilityFilter} options={['all', 'tools', 'vision', 'json', 'reasoning', 'streaming']} />
            <FilterSelect value={localFilter} onChange={setLocalFilter} options={['all', 'local', 'cloud']} />
          </div>
          <div className="overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03]">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 text-xs uppercase tracking-[0.12em] text-zinc-600">
                <tr>
                  <th className="px-4 py-3">Modèle</th>
                  <th className="px-4 py-3">Provider</th>
                  <th className="px-4 py-3">Capabilities</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredModels.map((model) => {
                  const reason = disabledReason(model, providerById.get(model.provider_id));
                  return (
                    <tr key={model.model_ref} className="border-b border-white/5 last:border-b-0">
                      <td className="px-4 py-3">
                        <div className="font-medium text-stone-100">{model.display_name}</div>
                        <div className="mt-1 text-xs text-zinc-600">{model.model_ref}</div>
                      </td>
                      <td className="px-4 py-3 text-zinc-400">{model.provider_id}</td>
                      <td className="px-4 py-3 text-zinc-500">{capabilityText(model)}</td>
                      <td className="px-4 py-3">{reason ? <span className="text-amber-200/80">{reason}</span> : <StatusBadge status="available" />}</td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-2">
                          <button disabled={Boolean(reason)} onClick={() => onSelectSession(model.model_ref)} className="secondary-button h-8 text-xs disabled:opacity-40">Session</button>
                          <button disabled={Boolean(reason)} onClick={() => onSetDefault(model.model_ref)} className="secondary-button h-8 text-xs disabled:opacity-40">Default</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filteredModels.length === 0 && <EmptyLine icon={Search} title="Aucun modèle" body="Ajuste la recherche ou les filtres." />}
          </div>
        </section>
      )}

      {tab === 'Preferences' && (
        <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="space-y-4">
          <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-4 flex items-center gap-2 font-semibold text-stone-100"><Settings size={18} className="text-zinc-500" /> Global default</div>
            <ModelSelector current={current} models={models} providers={providers} onSelect={onSelectSession} onSetDefault={onSetDefault} />
            <div className="mt-4 grid gap-3">
              <Metric label="Global" value={globalPreference?.primary_model_ref || 'codex/gpt-5.5'} />
              <Metric label="Fallback" value={globalPreference?.fallback_model_ref || 'Aucun fallback'} />
            </div>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-4 font-semibold text-stone-100">Fallback global</div>
            <div className="flex gap-2">
              <select value={fallbackDraft} onChange={(event) => setFallbackDraft(event.target.value)} className="field h-10 flex-1 py-1 text-sm">
                <option value="">Aucun fallback</option>
                {models.map((model) => <option key={model.model_ref} value={model.model_ref}>{model.model_ref}</option>)}
              </select>
              <button onClick={() => onSetPreference('global', null, globalPreference?.primary_model_ref || current?.primary_model_ref || 'codex/gpt-5.5', fallbackDraft || null)} className="secondary-button h-10">Sauver</button>
            </div>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-4 font-semibold text-stone-100">Per-agent model</div>
            <PreferencePicker scope="agent_profile" selectedId={selectedAgentId} setSelectedId={setSelectedAgentId} options={agents} models={models} providers={providers} onSetPreference={onSetPreference} />
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-4 font-semibold text-stone-100">Per-project model</div>
            <PreferencePicker scope="project" selectedId={selectedProjectId} setSelectedId={setSelectedProjectId} options={projects} models={models} providers={providers} onSetPreference={onSetPreference} />
          </div>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-3 font-semibold text-stone-100">Préférences par scope</div>
            <div className="grid gap-2">
              {preferences.map((pref) => (
                <div key={pref.id} className="grid gap-2 rounded-2xl border border-white/10 bg-black/10 p-3 text-sm sm:grid-cols-[140px_1fr_1fr]">
                  <span className="text-zinc-400">{pref.scope}{pref.scope_id ? `:${pref.scope_id}` : ''}</span>
                  <span className="truncate text-stone-100">{pref.primary_model_ref}</span>
                  <span className="truncate text-zinc-600">{pref.fallback_model_ref || 'no fallback'}</span>
                </div>
              ))}
              {preferences.length === 0 && <EmptyLine icon={Settings} title="Aucune préférence" body="Les préférences globales, projet, session et agent apparaîtront ici." />}
            </div>
          </div>
        </section>
      )}

      {tab === 'Usage' && (
        <section className="grid gap-4 lg:grid-cols-[1fr_0.85fr]">
          <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-3 flex items-center gap-2 font-semibold text-stone-100"><Activity size={18} className="text-zinc-500" /> Dernières utilisations</div>
            <div className="grid gap-2">
              {usage.map((item) => (
                <div key={item.id} className="grid gap-2 rounded-2xl border border-white/10 bg-black/10 p-3 text-sm sm:grid-cols-[1fr_120px_120px]">
                  <div className="min-w-0">
                    <div className="truncate text-stone-100">{item.model_ref}</div>
                    <div className="text-xs text-zinc-600">{formatDate(item.started_at)}</div>
                  </div>
                  <StatusBadge status={item.status} />
                  <div className="text-right text-zinc-400">{item.latency_ms != null ? `${item.latency_ms} ms` : '—'}</div>
                  {item.error && <div className="sm:col-span-3 text-xs text-red-200">{item.error}</div>}
                </div>
              ))}
              {usage.length === 0 && <EmptyLine icon={Activity} title="Aucun usage" body="Les appels modèle récents apparaîtront ici après un chat." />}
            </div>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-3 flex items-center gap-2 font-semibold text-stone-100"><AlertTriangle size={18} className="text-zinc-500" /> Fallback & erreurs</div>
            <div className="grid gap-2">
              {modelEvents.map((event, index) => (
                <div key={event.id || index} className="rounded-2xl border border-white/10 bg-black/10 p-3 text-sm">
                  <div className="text-stone-100">{event.type}</div>
                  <pre className="mt-2 max-h-28 overflow-auto text-xs text-zinc-500">{JSON.stringify(event.payload || {}, null, 2)}</pre>
                </div>
              ))}
              {modelEvents.length === 0 && <EmptyLine icon={CheckCircle2} title="Aucun fallback" body="Les bascules de modèle et erreurs seront listées ici." />}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/10 p-3">
      <div className="text-xs text-zinc-600">{label}</div>
      <div className="mt-1 break-words text-sm font-medium text-stone-100">{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const good = ['configured', 'available', 'completed'].includes(status);
  const bad = ['missing', 'invalid', 'failed'].includes(status);
  return <span className={`inline-flex w-fit items-center gap-1 rounded-full border px-2 py-1 text-xs ${good ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100' : bad ? 'border-amber-400/20 bg-amber-400/10 text-amber-100' : 'border-white/10 bg-white/[0.045] text-zinc-300'}`}>{status}</span>;
}

function FilterSelect({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: string[] }) {
  return (
    <label className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/10 px-3 py-2">
      <Filter size={15} className="text-zinc-600" />
      <select value={value} onChange={(event) => onChange(event.target.value)} className="min-w-0 flex-1 bg-transparent text-sm text-stone-100 outline-none">
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

function EmptyLine({ icon: Icon, title, body }: { icon: ElementType; title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.025] p-6 text-center">
      <Icon size={18} className="mx-auto text-zinc-600" />
      <div className="mt-2 text-sm font-medium text-stone-100">{title}</div>
      <p className="mt-1 text-sm text-zinc-500">{body}</p>
    </div>
  );
}

function PreferencePicker({
  scope,
  selectedId,
  setSelectedId,
  options,
  models,
  providers,
  onSetPreference,
}: {
  scope: 'agent_profile' | 'project';
  selectedId: string;
  setSelectedId: (value: string) => void;
  options: Array<{ id: string; name: string }>;
  models: ModelView[];
  providers: ProviderView[];
  onSetPreference: (scope: string, scopeId: string | null, modelRef: string, fallbackModelRef?: string | null) => void;
}) {
  const [modelRef, setModelRef] = useState('');
  const providerById = useMemo(() => new Map(providers.map((provider) => [provider.id, provider])), [providers]);
  const selectedModel = models.find((model) => model.model_ref === modelRef);
  const reason = selectedModel ? disabledReason(selectedModel, providerById.get(selectedModel.provider_id)) : '';
  const emptyLabel = scope === 'project' ? 'Choisir un projet' : 'Choisir un agent';
  const actionLabel = scope === 'project' ? 'Sauver pour ce projet' : 'Sauver pour cet agent';

  return (
    <div className="grid gap-3">
      <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} className="field h-10 py-1 text-sm">
        <option value="">{emptyLabel}</option>
        {options.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
      </select>
      <select value={modelRef} onChange={(event) => setModelRef(event.target.value)} className="field h-10 py-1 text-sm">
        <option value="">Choisir un modele</option>
        {models.map((model) => {
          const disabled = Boolean(disabledReason(model, providerById.get(model.provider_id)));
          return <option key={model.model_ref} value={model.model_ref} disabled={disabled}>{model.model_ref}{disabled ? ' - indisponible' : ''}</option>;
        })}
      </select>
      {reason && <div className="rounded-2xl border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">{reason}</div>}
      {options.length === 0 && <div className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2 text-xs text-zinc-500">Aucun {scope === 'project' ? 'projet' : 'agent'} disponible.</div>}
      <button disabled={!selectedId || !modelRef || Boolean(reason)} onClick={() => onSetPreference(scope, selectedId, modelRef)} className="secondary-button h-10 justify-center disabled:cursor-not-allowed disabled:opacity-40">
        {actionLabel}
      </button>
    </div>
  );
}

function hasCapability(model: ModelView, capability: string) {
  if (capability === 'tools') return Boolean(model.supports_tools);
  if (capability === 'vision') return Boolean(model.supports_vision);
  if (capability === 'json') return Boolean(model.supports_json);
  if (capability === 'reasoning') return Boolean(model.supports_reasoning);
  if (capability === 'streaming') return Boolean(model.supports_streaming);
  return true;
}

function capabilityText(model: ModelView) {
  const labels = [
    model.supports_tools && 'tools',
    model.supports_vision && 'vision',
    model.supports_json && 'json',
    model.supports_reasoning && 'reasoning',
    model.supports_streaming && 'streaming',
    model.supports_local && 'local',
  ].filter(Boolean);
  return labels.join(', ') || 'standard';
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
