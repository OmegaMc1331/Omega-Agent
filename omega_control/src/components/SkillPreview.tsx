export function SkillPreview({ proposed }: { proposed: Record<string, unknown> }) {
  const definition = (proposed.definition || {}) as Record<string, unknown>;
  const steps = Array.isArray(definition.steps) ? definition.steps : [];
  return (
    <div className="rounded-2xl border border-white/10 bg-black/15 p-4">
      <div className="text-sm font-medium text-stone-100">{String(proposed.name || definition.name || 'Draft skill')}</div>
      <p className="mt-1 text-sm text-zinc-500">{String(proposed.description || definition.description || '')}</p>
      <div className="mt-3 text-xs uppercase tracking-[0.14em] text-zinc-600">Proposed steps</div>
      <ol className="mt-2 space-y-2 text-sm text-zinc-400">
        {steps.slice(0, 6).map((step, index) => {
          const item = step as Record<string, unknown>;
          return <li key={index}>{index + 1}. {String(item.instruction || item.action || 'Review step')}</li>;
        })}
      </ol>
    </div>
  );
}
