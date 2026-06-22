import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { EvalScoreCard } from '../components/EvalScoreCard';
import { ModelPerformanceTable, type ModelPerformanceView } from '../components/ModelPerformanceTable';
import { ToolReliabilityChart, type ToolReliabilityView } from '../components/ToolReliabilityChart';

type MetricsPayload = {
  aggregate: {
    runs: number;
    task_success_rate: number;
    average_duration_ms: number;
    tool_failure_rate: number;
    rollback_rate: number;
    approval_friction: number;
    tool_calls: number;
    failed_tool_calls: number;
    rollbacks: number;
    approvals: number;
  };
  models: ModelPerformanceView[];
  tools: ToolReliabilityView[];
  agents: ModelPerformanceView[];
  policy: Array<{ tool_name: string; denied: number; approval_required: number }>;
};

export function MetricsPage() {
  const [metrics, setMetrics] = useState<MetricsPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      setMetrics(await api<MetricsPayload>('/api/evals/metrics'));
      setError('');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  const aggregate = metrics?.aggregate;

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-lg font-semibold text-stone-100">Metrics</div>
          <p className="mt-1 text-sm text-zinc-500">Performance et fiabilité agrégées sur les runs Omega.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        <EvalScoreCard title="Success rate" value={`${Math.round((aggregate?.task_success_rate || 0) * 100)}%`} />
        <EvalScoreCard title="Avg duration" value={formatDuration(aggregate?.average_duration_ms || 0)} />
        <EvalScoreCard title="Tool failure" value={`${Math.round((aggregate?.tool_failure_rate || 0) * 100)}%`} />
        <EvalScoreCard title="Rollback rate" value={`${Math.round((aggregate?.rollback_rate || 0) * 100)}%`} />
        <EvalScoreCard title="Approval friction" value={`${Math.round((aggregate?.approval_friction || 0) * 100)}%`} />
        <EvalScoreCard title="Policy denials" value={metrics?.policy.reduce((sum, item) => sum + item.denied, 0) || 0} />
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-5">
          <ModelPerformanceTable title="Model performance" rows={metrics?.models || []} labelKey="model_ref" />
          <ModelPerformanceTable title="Agent profile performance" rows={metrics?.agents || []} labelKey="agent_profile_id" />
        </div>
        <ToolReliabilityChart tools={metrics?.tools || []} />
      </div>
    </div>
  );
}

function formatDuration(value: number) {
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} s`;
}
