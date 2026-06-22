import { useEffect, useState } from 'react';
import { Pause, Play, RefreshCw, XCircle } from 'lucide-react';
import { api } from '../api/client';
import { WorkflowRunTimeline, type WorkflowRunView, type WorkflowStepRunView } from '../components/WorkflowRunTimeline';
import { RunStatusBadge } from '../components/RunStatusBadge';

type WorkflowRunDetail = {
  workflow_run: WorkflowRunView;
  steps: WorkflowStepRunView[];
};

export function WorkflowRunsPage() {
  const [runs, setRuns] = useState<WorkflowRunView[]>([]);
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<WorkflowRunDetail | null>(null);
  const [status, setStatus] = useState('all');
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const query = status === 'all' ? '' : `?status=${encodeURIComponent(status)}`;
      const nextRuns = await api<WorkflowRunView[]>(`/api/workflows/runs${query}`);
      setRuns(nextRuns);
      const nextSelected = selected || nextRuns[0]?.id || '';
      if (nextSelected) await loadRun(nextSelected);
    } finally {
      setLoading(false);
    }
  }

  async function loadRun(id: string) {
    setSelected(id);
    setDetail(await api<WorkflowRunDetail>(`/api/workflows/runs/${id}`));
  }

  async function action(path: string) {
    await api(path, { method: 'POST', body: JSON.stringify({}) });
    await load();
  }

  async function retry(step: WorkflowStepRunView) {
    if (!detail) return;
    await api(`/api/workflows/runs/${detail.workflow_run.id}/retry-step`, { method: 'POST', body: JSON.stringify({ step_id: step.step_id }) });
    await loadRun(detail.workflow_run.id);
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [status]);

  const current = detail?.workflow_run || null;

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-semibold text-stone-100">Workflow Runs</div>
          <p className="mt-1 text-sm text-zinc-500">Timeline durable des executions workflow.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select value={status} onChange={(event) => setStatus(event.target.value)} className="field max-w-48">
            {['all', 'pending', 'running', 'paused', 'succeeded', 'failed', 'cancelled'].map((item) => <option key={item}>{item}</option>)}
          </select>
          <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-2">
          {runs.map((run) => (
            <button key={run.id} onClick={() => loadRun(run.id)} className={`w-full rounded-2xl border p-3 text-left transition ${selected === run.id ? 'border-blue-400/25 bg-blue-500/10' : 'border-white/10 bg-white/[0.035] hover:bg-white/[0.055]'}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-stone-100">{run.id}</span>
                <RunStatusBadge status={run.status} />
              </div>
              <div className="mt-1 text-xs text-zinc-500">workflow={run.workflow_id}</div>
            </button>
          ))}
          {runs.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-6 text-sm text-zinc-500">No workflow runs.</div>}
        </div>
        <div className="space-y-3">
          {current && (
            <div className="flex flex-wrap gap-2">
              {current.status === 'running' && <button className="secondary-button" onClick={() => action(`/api/workflows/runs/${current.id}/pause`)}><Pause size={15} /> Pause</button>}
              {current.status === 'paused' && <button className="secondary-button" onClick={() => action(`/api/workflows/runs/${current.id}/resume`)}><Play size={15} /> Resume</button>}
              {['running', 'paused'].includes(current.status) && <button className="danger-button" onClick={() => action(`/api/workflows/runs/${current.id}/cancel`)}><XCircle size={15} /> Cancel</button>}
            </div>
          )}
          <WorkflowRunTimeline run={current} steps={detail?.steps || []} onRetry={retry} />
        </div>
      </div>
    </div>
  );
}
