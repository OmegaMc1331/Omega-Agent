export type PolicyRuleView = {
  id: string;
  profile_id: string;
  name: string;
  description: string;
  enabled: boolean;
  priority: number;
  effect: string;
  action_type?: string | null;
  tool_name?: string | null;
  resource_pattern?: string | null;
  risk_level_min?: string | null;
  conditions: Record<string, unknown>;
  reason: string;
};

export function PolicyRuleCard({ rule, onToggle, onDelete }: { rule: PolicyRuleView; onToggle: (rule: PolicyRuleView) => void; onDelete: (rule: PolicyRuleView) => void }) {
  const tone = rule.effect === 'allow' ? 'text-emerald-200 border-emerald-400/20 bg-emerald-500/10' : rule.effect === 'deny' ? 'text-red-200 border-red-400/20 bg-red-500/10' : 'text-amber-200 border-amber-400/20 bg-amber-500/10';
  return (
    <article className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-zinc-100">{rule.name}</span>
            <span className={`rounded-full border px-2 py-1 text-xs ${tone}`}>{rule.effect}</span>
            <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-zinc-500">priority {rule.priority}</span>
          </div>
          <p className="mt-1 text-sm text-zinc-500">{rule.reason || rule.description || 'No reason set.'}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => onToggle(rule)} className="secondary-button">{rule.enabled ? 'Disable' : 'Enable'}</button>
          <button onClick={() => onDelete(rule)} className="secondary-button">Delete</button>
        </div>
      </div>
      <div className="mt-3 grid gap-2 text-xs text-zinc-500 sm:grid-cols-3">
        <span>tool {rule.tool_name || '*'}</span>
        <span>action {rule.action_type || '*'}</span>
        <span>resource {rule.resource_pattern || '*'}</span>
      </div>
      {Object.keys(rule.conditions || {}).length > 0 && <pre className="mt-3 overflow-auto rounded-xl bg-black/20 p-3 text-xs text-zinc-400">{JSON.stringify(rule.conditions, null, 2)}</pre>}
    </article>
  );
}
