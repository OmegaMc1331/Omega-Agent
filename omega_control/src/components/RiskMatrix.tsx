const rows = [
  ['read_only', 'allow', 'allow', 'allow', 'deny'],
  ['reversible_write', 'allow', 'allow', 'approval', 'deny'],
  ['destructive_write', 'approval', 'approval', 'approval', 'deny'],
  ['external_side_effect', 'approval', 'approval', 'deny', 'deny'],
  ['system_sensitive', 'deny', 'deny', 'deny', 'deny'],
];

const levels = ['low', 'medium', 'high', 'critical'];

export function RiskMatrix() {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 text-sm font-semibold text-stone-100">Risk matrix</div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="text-xs uppercase text-zinc-500">
            <tr>
              <th className="px-3 py-2">Category</th>
              {levels.map((level) => <th key={level} className="px-3 py-2">{level}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map(([category, ...decisions]) => (
              <tr key={category} className="border-t border-white/10">
                <td className="px-3 py-2 font-medium text-zinc-200">{category}</td>
                {decisions.map((decision, index) => (
                  <td key={`${category}-${levels[index]}`} className="px-3 py-2"><DecisionBadge value={decision} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DecisionBadge({ value }: { value: string }) {
  const tone = value === 'allow' ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-200' : value === 'approval' ? 'border-amber-400/20 bg-amber-500/10 text-amber-200' : 'border-red-400/20 bg-red-500/10 text-red-200';
  return <span className={`inline-flex rounded-full border px-2 py-1 text-xs ${tone}`}>{value}</span>;
}
