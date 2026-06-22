export function ConnectorAuthStatus({ status }: { status?: string | null }) {
  const value = status || 'none';
  const tone =
    value === 'configured' || value === 'none'
      ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200'
      : value === 'missing'
        ? 'border-amber-400/20 bg-amber-400/10 text-amber-200'
        : 'border-red-400/20 bg-red-400/10 text-red-200';
  return <span className={`rounded-full border px-2 py-0.5 text-xs ${tone}`}>{value}</span>;
}
