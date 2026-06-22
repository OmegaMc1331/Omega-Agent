export type PolicySimulationView = {
  final_decision: string;
  risk_level: string;
  reason: string;
  would_create_approval: boolean;
  would_create_snapshot: boolean;
  warnings: string[];
  action_category: string;
  matched_rules: Array<{ id: string; name: string; profile_name?: string; effect: string; reason?: string; priority?: number }>;
};

export function PolicySimulationResult({ result }: { result: PolicySimulationView | null }) {
  if (!result) {
    return (
      <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4 text-sm text-zinc-500">
        Run a simulation to inspect the effective backend decision.
      </section>
    );
  }
  return (
    <section className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-stone-100">Decision: {result.final_decision}</div>
          <div className="text-xs text-zinc-500">{result.action_category} · {result.risk_level}</div>
        </div>
        <div className="flex gap-2 text-xs">
          {result.would_create_approval && <Badge tone="amber">approval</Badge>}
          {result.would_create_snapshot && <Badge tone="blue">snapshot</Badge>}
        </div>
      </div>
      <p className="text-sm text-zinc-300">{result.reason}</p>
      {result.warnings.length > 0 && <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-3 text-xs text-amber-100">{result.warnings.join(', ')}</div>}
      <div>
        <div className="mb-2 text-xs font-semibold uppercase text-zinc-500">Matched rules</div>
        {result.matched_rules.length === 0 && <div className="text-sm text-zinc-500">No custom rule matched.</div>}
        <div className="space-y-2">
          {result.matched_rules.map((rule) => (
            <div key={rule.id} className="rounded-xl border border-white/10 bg-black/10 px-3 py-2 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-zinc-200">{rule.name}</span>
                <Badge tone={rule.effect === 'allow' ? 'green' : rule.effect === 'deny' ? 'red' : 'amber'}>{rule.effect}</Badge>
              </div>
              <div className="mt-1 text-xs text-zinc-500">{rule.profile_name || rule.id} · priority {rule.priority || 0}</div>
              {rule.reason && <div className="mt-1 text-xs text-zinc-400">{rule.reason}</div>}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Badge({ tone, children }: { tone: 'green' | 'red' | 'amber' | 'blue'; children: string }) {
  const tones = {
    green: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-200',
    red: 'border-red-400/20 bg-red-500/10 text-red-200',
    amber: 'border-amber-400/20 bg-amber-500/10 text-amber-200',
    blue: 'border-blue-400/20 bg-blue-500/10 text-blue-200',
  };
  return <span className={`inline-flex rounded-full border px-2 py-1 ${tones[tone]}`}>{children}</span>;
}
