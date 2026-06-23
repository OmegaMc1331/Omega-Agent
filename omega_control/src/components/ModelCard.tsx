import { CheckCircle2, Zap } from 'lucide-react';
import { ModelCapabilityBadges } from './ModelCapabilityBadges';

export type ModelView = {
  id: string;
  provider_id: string;
  model_ref: string;
  ref?: string;
  display_name: string;
  description: string;
  speed_tier: string;
  cost_tier: string;
  enabled: boolean;
  available: boolean;
  supports_streaming?: boolean;
  supports_tools?: boolean;
  supports_vision?: boolean;
  supports_json?: boolean;
  supports_reasoning?: boolean;
  supports_local?: boolean;
  thinking?: CurrentModelThinking;
};

type CurrentModelThinking = {
  supported: boolean;
  levels: string[];
  configured_level: string;
  current_level: string;
  mode: string;
};

export function ModelCard({ model, current, onSelect, onDefault }: { model: ModelView; current?: boolean; onSelect: (modelRef: string) => void; onDefault: (modelRef: string) => void }) {
  return (
    <div className={`rounded-3xl border p-4 ${current ? 'border-blue-300/25 bg-blue-500/10' : 'border-white/10 bg-white/[0.035]'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-semibold text-stone-100">
            <Zap size={16} className="text-zinc-500" /> <span className="truncate">{model.display_name}</span>
          </div>
          <div className="mt-1 truncate text-xs text-zinc-600">{model.model_ref}</div>
          {model.description && <p className="mt-2 text-sm leading-6 text-zinc-500">{model.description}</p>}
        </div>
        <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs ${model.available ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100' : 'border-amber-400/20 bg-amber-400/10 text-amber-100'}`}>
          <CheckCircle2 size={13} /> {model.available ? 'available' : 'unavailable'}
        </span>
      </div>
      <div className="mt-3">
        <ModelCapabilityBadges item={model} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={() => onSelect(model.model_ref)} className="secondary-button h-9">Utiliser session</button>
        <button onClick={() => onDefault(model.model_ref)} className="secondary-button h-9">Défaut global</button>
      </div>
    </div>
  );
}
