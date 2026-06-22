type ClassifiedError = {
  error_type: string;
  title: string;
  summary: string;
  confidence: number;
};

type Suggestion = {
  kind: string;
  message: string;
  safe_to_auto_apply?: boolean;
};

export function SelfHealingPanel({ classified, suggestion }: { classified?: ClassifiedError | null; suggestion?: Suggestion | null }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 text-sm font-semibold text-stone-100">Self-healing</div>
      {!classified && <div className="text-sm text-zinc-500">Aucune erreur classifiee.</div>}
      {classified && (
        <div className="space-y-3">
          <div className="rounded-xl border border-white/10 bg-black/10 p-3">
            <div className="text-xs uppercase text-zinc-600">{classified.error_type} / {Math.round(classified.confidence * 100)}%</div>
            <div className="mt-1 text-sm font-medium text-stone-100">{classified.title}</div>
            <div className="mt-1 text-sm text-zinc-400">{classified.summary}</div>
          </div>
          {suggestion && (
            <div className="rounded-xl border border-white/10 bg-black/10 p-3 text-sm text-zinc-300">
              {suggestion.message}
              <div className="mt-2 text-xs text-zinc-600">{suggestion.safe_to_auto_apply ? 'safe auto recovery available' : 'manual review required'}</div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
