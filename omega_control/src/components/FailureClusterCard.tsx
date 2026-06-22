import { StatusBadge } from './TraceTable';

export type FailureClusterView = {
  id: string;
  title: string;
  description: string;
  failure_type: string;
  count: number;
  last_seen_at: string;
  suggested_fix?: string | null;
  status: string;
  examples?: Array<{ run_id?: string; summary?: string; tool_name?: string }>;
};

export function FailureClusterCard({ cluster, onStatus }: { cluster: FailureClusterView; onStatus?: (id: string, status: string) => void }) {
  return (
    <article className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-stone-100">{cluster.title}</div>
          <div className="mt-1 text-sm text-zinc-500">{cluster.failure_type} · {cluster.count} occurrences</div>
        </div>
        <StatusBadge status={cluster.status} />
      </div>
      {cluster.description && <p className="mt-3 text-sm leading-6 text-zinc-400">{cluster.description}</p>}
      {cluster.suggested_fix && <div className="mt-3 rounded-xl border border-blue-400/15 bg-blue-500/10 p-3 text-sm text-blue-100">{cluster.suggested_fix}</div>}
      {cluster.examples && cluster.examples.length > 0 && (
        <div className="mt-3 space-y-2">
          {cluster.examples.slice(0, 3).map((example) => (
            <div key={example.run_id} className="rounded-xl bg-black/10 px-3 py-2 text-xs text-zinc-500">
              <span className="text-zinc-300">{example.run_id}</span> {example.tool_name ? `· ${example.tool_name}` : ''} {example.summary ? `· ${example.summary}` : ''}
            </div>
          ))}
        </div>
      )}
      {onStatus && (
        <div className="mt-3 flex flex-wrap gap-2">
          {['investigating', 'fixed', 'ignored'].map((status) => (
            <button key={status} onClick={() => onStatus(cluster.id, status)} className="secondary-button h-8 px-3 text-xs">{status}</button>
          ))}
        </div>
      )}
    </article>
  );
}
