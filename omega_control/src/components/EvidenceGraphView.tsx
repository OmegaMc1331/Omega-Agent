import { ArrowRight, Database, FileText } from 'lucide-react';
import { ConfidenceBadge } from './ConfidenceBadge';
import type { EvidenceGraphViewModel } from '../types/research';

export function EvidenceGraphView({ graph }: { graph: EvidenceGraphViewModel }) {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const sources = graph.nodes.filter((node) => node.node_type === 'source');
  const claims = graph.nodes.filter((node) => node.node_type === 'claim');
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="Sources" value={sources.length} />
        <Metric label="Claims" value={claims.length} />
        <Metric label="Confiance moyenne" value={`${Math.round(graph.confidence_summary.average * 100)}%`} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="space-y-2">
          <div className="text-sm font-semibold text-stone-100">Source nodes</div>
          {sources.map((node) => (
            <div key={node.id} className="rounded-2xl border border-blue-400/15 bg-blue-500/[0.06] p-3">
              <div className="flex items-center gap-2 text-sm text-stone-200"><Database size={14} className="text-blue-200" /> {node.label}</div>
              <div className="mt-1 text-xs text-zinc-500">{node.source_type} · {node.trust_level}</div>
            </div>
          ))}
        </section>
        <section className="space-y-2">
          <div className="text-sm font-semibold text-stone-100">Claim nodes</div>
          {claims.map((node) => (
            <div key={node.id} className={`rounded-2xl border p-3 ${node.status === 'supported' ? 'border-emerald-400/15 bg-emerald-500/[0.06]' : node.status === 'weak' ? 'border-amber-400/15 bg-amber-400/[0.06]' : 'border-red-400/15 bg-red-500/[0.06]'}`}>
              <div className="flex items-start justify-between gap-3 text-sm text-stone-200"><span className="flex gap-2"><FileText size={14} className="mt-1 text-zinc-400" /> {node.label}</span><ConfidenceBadge confidence={node.confidence || 0} status={node.status} /></div>
            </div>
          ))}
        </section>
      </div>
      <section className="space-y-2">
        <div className="text-sm font-semibold text-stone-100">Edges</div>
        {graph.edges.map((edge) => (
          <div key={edge.id} className="grid gap-2 rounded-2xl border border-white/10 bg-white/[0.035] p-3 text-xs text-zinc-400 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center">
            <span>{nodes.get(edge.source)?.label || edge.source}</span>
            <span className={`flex items-center gap-1 rounded-full border px-2 py-1 ${edge.type === 'supports' ? 'border-emerald-400/20 text-emerald-100' : edge.type === 'contradicts' ? 'border-red-400/20 text-red-100' : 'border-white/10 text-zinc-400'}`}>{edge.type}<ArrowRight size={12} /></span>
            <span>{nodes.get(edge.target)?.label || edge.target}</span>
          </div>
        ))}
        {graph.edges.length === 0 && <div className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-zinc-500">Aucune liaison evidence.</div>}
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-4"><div className="text-xs text-zinc-500">{label}</div><div className="mt-1 text-2xl font-semibold text-stone-100">{value}</div></div>;
}
