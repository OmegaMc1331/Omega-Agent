export function RiskBadge({ risk }: { risk: string }) {
  const tone = risk === 'critical'
    ? 'border-red-400/20 bg-red-500/10 text-red-100'
    : risk === 'high'
      ? 'border-amber-400/20 bg-amber-400/10 text-amber-100'
      : risk === 'medium'
        ? 'border-blue-400/20 bg-blue-500/10 text-blue-100'
        : 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100';
  return <span className={`inline-flex h-6 items-center rounded-full border px-2 text-[11px] font-medium ${tone}`}>{risk || 'low'}</span>;
}
