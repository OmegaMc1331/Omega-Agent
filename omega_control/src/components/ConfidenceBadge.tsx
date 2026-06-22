export function ConfidenceBadge({ confidence, status }: { confidence: number; status?: string }) {
  const tone = status === 'contradicted' || status === 'unsupported'
    ? 'border-red-400/20 bg-red-500/10 text-red-100'
    : status === 'weak' || confidence < 0.7
      ? 'border-amber-400/20 bg-amber-400/10 text-amber-100'
      : 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100';
  return <span className={`inline-flex h-6 items-center rounded-full border px-2 text-[11px] font-medium ${tone}`}>{Math.round(confidence * 100)}%</span>;
}
