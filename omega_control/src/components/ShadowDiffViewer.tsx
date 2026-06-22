import { FileDiff } from 'lucide-react';
import type { ShadowRunView } from '../types/shadow';

export function ShadowDiffViewer({ diff }: { diff?: ShadowRunView['predicted_diff'] }) {
  const groups = [
    ['Créés', diff?.created || []],
    ['Modifiés', diff?.modified || []],
    ['Supprimés', diff?.deleted || []],
  ] as const;
  return (
    <section className="rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4">
      <div className="mb-2 flex items-center gap-2 font-semibold text-stone-100"><FileDiff size={17} className="text-emerald-300" /> Diff prévu</div>
      <div className="mb-4 text-sm text-zinc-500">{diff?.summary || 'Diff non calculé.'}</div>
      <div className="space-y-4">
        {groups.map(([label, items]) => items.length > 0 && (
          <div key={label}>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">{label}</div>
            <div className="space-y-2">
              {items.map((item) => (
                <details key={`${label}-${item.path}`} className="rounded-2xl border border-white/10 bg-black/10 p-3">
                  <summary className="cursor-pointer text-sm text-stone-200">{item.path} <span className="text-xs text-zinc-500">· {item.risk}</span></summary>
                  {item.diff && <pre className="mt-3 max-h-72 overflow-auto rounded-xl bg-black/20 p-3 text-[11px] leading-5 text-zinc-400">{item.diff}</pre>}
                </details>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
