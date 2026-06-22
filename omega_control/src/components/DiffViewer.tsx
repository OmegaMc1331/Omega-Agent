export type DiffSummaryView = {
  diff: string;
  files: string[];
  added: number;
  removed: number;
};

export function DiffViewer({ diff }: { diff: DiffSummaryView | null }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-semibold text-stone-100">Git diff</div>
        {diff && <div className="text-xs text-zinc-500">{diff.files.length} files / +{diff.added} -{diff.removed}</div>}
      </div>
      {diff?.files.length ? (
        <div className="mb-3 flex flex-wrap gap-2">
          {diff.files.map((file) => <span key={file} className="rounded-full bg-white/[0.05] px-2 py-1 text-xs text-zinc-400">{file}</span>)}
        </div>
      ) : null}
      <pre className="max-h-96 overflow-auto rounded-xl border border-white/10 bg-black/20 p-3 text-xs leading-5 text-zinc-400">{diff?.diff?.trim() || 'No diff'}</pre>
    </section>
  );
}
