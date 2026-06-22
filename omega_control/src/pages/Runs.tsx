import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Activity, ListRestart, Pause, Play, RotateCcw, XCircle } from 'lucide-react';
import { api } from '../api/client';
import { ActionJournalPanel, type ActionView } from '../components/ActionJournalPanel';
import { CheckpointCard, type CheckpointView } from '../components/CheckpointCard';
import { RunStatusBadge } from '../components/RunStatusBadge';
import { RunTimeline, type StepView } from '../components/RunTimeline';
import { SnapshotCard, type SnapshotView } from '../components/SnapshotCard';

type RunView = {
  id: string;
  session_id: string;
  title: string;
  status: string;
  model_ref?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
  error?: string | null;
};

export function RunsPage() {
  const [runs, setRuns] = useState<RunView[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [steps, setSteps] = useState<StepView[]>([]);
  const [actions, setActions] = useState<ActionView[]>([]);
  const [checkpoints, setCheckpoints] = useState<CheckpointView[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotView[]>([]);
  const [status, setStatus] = useState('all');

  async function refresh() {
    const query = status === 'all' ? '' : `?status=${encodeURIComponent(status)}`;
    const nextRuns = await api<RunView[]>(`/api/runs${query}`);
    setRuns(nextRuns);
    const nextSelected = selected || nextRuns[0]?.id || '';
    if (nextSelected) await loadRun(nextSelected);
  }

  async function loadRun(runId: string) {
    setSelected(runId);
    const [nextSteps, nextActions, nextCheckpoints, nextSnapshots] = await Promise.all([
      api<StepView[]>(`/api/runs/${runId}/steps`),
      api<ActionView[]>(`/api/runs/${runId}/actions`),
      api<CheckpointView[]>(`/api/runs/${runId}/checkpoints`),
      api<SnapshotView[]>(`/api/runs/${runId}/snapshots`),
    ]);
    setSteps(nextSteps);
    setActions(nextActions);
    setCheckpoints(nextCheckpoints);
    setSnapshots(nextSnapshots);
  }

  async function post(path: string) {
    await api(path, { method: 'POST', body: JSON.stringify({}) });
    await refresh();
  }

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [status]);

  const run = runs.find((item) => item.id === selected);
  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><ListRestart size={18} className="text-zinc-400" /> Runs</div>
          <p className="mt-1 text-sm text-zinc-500">Executions durables, steps, actions, checkpoints et snapshots.</p>
        </div>
        <select value={status} onChange={(event) => setStatus(event.target.value)} className="field max-w-56">
          {['all', 'pending', 'running', 'paused', 'needs_approval', 'succeeded', 'failed', 'cancelled'].map((item) => <option key={item}>{item}</option>)}
        </select>
      </div>

      <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-2">
          {runs.map((item) => (
            <button key={item.id} onClick={() => loadRun(item.id)} className={`w-full rounded-2xl border p-3 text-left transition ${selected === item.id ? 'border-blue-400/25 bg-blue-500/10' : 'border-white/10 bg-white/[0.035] hover:bg-white/[0.055]'}`}>
              <div className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium text-stone-100">{item.title}</span><RunStatusBadge status={item.status} /></div>
              <div className="mt-1 text-xs text-zinc-500">{formatDate(item.updated_at)}</div>
            </button>
          ))}
          {runs.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-6 text-sm text-zinc-500">Aucun run.</div>}
        </div>

        <div className="space-y-4">
          {run && (
            <div className="rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate font-semibold text-stone-100">{run.title}</div>
                  <div className="mt-1 text-xs text-zinc-500">{run.id}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {run.status === 'running' && <button className="secondary-button" onClick={() => post(`/api/runs/${run.id}/pause`)}><Pause size={15} /> Pause</button>}
                  {run.status === 'paused' && <button className="secondary-button" onClick={() => post(`/api/runs/${run.id}/resume`)}><Play size={15} /> Resume</button>}
                  {['running', 'paused', 'needs_approval'].includes(run.status) && <button className="danger-button" onClick={() => post(`/api/runs/${run.id}/cancel`)}><XCircle size={15} /> Cancel</button>}
                  <button className="secondary-button" onClick={() => post(`/api/runs/${run.id}/replay`)}><Activity size={15} /> Replay</button>
                  {snapshots.length > 0 && <button className="secondary-button" onClick={() => post(`/api/runs/${run.id}/rollback`)}><RotateCcw size={15} /> Rollback run</button>}
                </div>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <Panel title="Timeline"><RunTimeline steps={steps} /></Panel>
                <Panel title="Actions"><ActionJournalPanel actions={actions} /></Panel>
                <Panel title="Checkpoints"><div className="grid gap-2">{checkpoints.map((checkpoint) => <CheckpointCard key={checkpoint.id} checkpoint={checkpoint} />)}</div></Panel>
                <Panel title="Snapshots"><div className="grid gap-2">{snapshots.map((snapshot) => <SnapshotCard key={snapshot.id} snapshot={snapshot} onChanged={refresh} />)}</div></Panel>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="rounded-2xl border border-white/10 bg-black/10 p-3"><div className="mb-3 text-sm font-semibold text-stone-100">{title}</div>{children}</section>;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}
