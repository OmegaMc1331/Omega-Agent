export function EvalScoreCard({ title, value, subtitle }: { title: string; value: string | number; subtitle?: string }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="text-xs uppercase tracking-wide text-zinc-600">{title}</div>
      <div className="mt-2 text-2xl font-semibold text-stone-100">{value}</div>
      {subtitle && <div className="mt-1 text-sm text-zinc-500">{subtitle}</div>}
    </section>
  );
}
