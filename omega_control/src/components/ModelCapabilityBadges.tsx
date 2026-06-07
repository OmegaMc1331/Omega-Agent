import { BadgeCheck, Brain, Code2, Eye, Gauge, KeyRound, Laptop, Radio } from 'lucide-react';

export type ModelCapabilityInput = {
  auth_type?: string;
  supports_streaming?: boolean;
  supports_tools?: boolean;
  supports_vision?: boolean;
  supports_json?: boolean;
  supports_reasoning?: boolean;
  supports_local?: boolean;
  speed_tier?: string;
};

export function ModelCapabilityBadges({ item }: { item: ModelCapabilityInput }) {
  const badges = [
    item.auth_type === 'codex_oauth' && ['OAuth', KeyRound],
    item.auth_type === 'env_api_key' && ['API key', KeyRound],
    item.supports_local && ['Local', Laptop],
    item.supports_tools && ['Tools', Code2],
    item.supports_vision && ['Vision', Eye],
    item.supports_json && ['JSON', BadgeCheck],
    item.supports_streaming && ['Stream', Radio],
    item.supports_reasoning && ['Reasoning', Brain],
    item.speed_tier === 'fast' && ['Fast', Gauge],
    item.speed_tier === 'deep' && ['Deep', Brain],
  ].filter(Boolean) as Array<[string, typeof KeyRound]>;

  return (
    <div className="flex flex-wrap gap-1.5">
      {badges.map(([label, Icon]) => (
        <span key={label} className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.035] px-2 py-1 text-[11px] text-zinc-400">
          <Icon size={12} /> {label}
        </span>
      ))}
    </div>
  );
}
