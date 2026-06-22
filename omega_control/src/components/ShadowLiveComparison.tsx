import { GitCompareArrows } from 'lucide-react';
import type { ShadowRunView } from '../types/shadow';

export function ShadowLiveComparison({ comparison }: { comparison?: ShadowRunView['comparison'] }) {
  const details = comparison?.comparison;
  return (
    <section className="rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4">
      <div className="mb-3 flex items-center gap-2 font-semibold text-stone-100"><GitCompareArrows size={17} className="text-violet-300" /> Shadow vs live</div>
      {!comparison && <div className="text-sm text-zinc-500">Comparaison disponible après promotion live.</div>}
      {comparison && (
        <>
          <div className="text-sm text-zinc-300">{details?.summary || 'Comparaison créée.'}</div>
          <div className="mt-2 text-xs text-zinc-500">Match score: {Math.round(Number(comparison.diff_match_score ?? details?.diff_match_score ?? 0) * 100)}%</div>
        </>
      )}
    </section>
  );
}
